"""Export the talk items in a VOICEVOX project to one WAV file.

The script regenerates pronunciation from each item's text, then applies the
saved speed, pitch, intonation, volume, pause, and output settings.  This also
repairs projects whose visible text and cached pronunciation no longer match.
"""

from __future__ import annotations

import argparse
import io
import json
import wave
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


VOICE_SETTINGS = (
    "speedScale",
    "pitchScale",
    "intonationScale",
    "volumeScale",
    "prePhonemeLength",
    "postPhonemeLength",
    "pauseLengthScale",
    "outputSamplingRate",
    "outputStereo",
)


def request_bytes(url: str, body: bytes | None = None) -> bytes:
    request = Request(url, data=body if body is not None else b"", method="POST")
    if body is not None:
        request.add_header("Content-Type", "application/json; charset=utf-8")
    try:
        with urlopen(request, timeout=120) as response:
            return response.read()
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"VOICEVOX returned HTTP {exc.code}: {detail}") from exc
    except URLError as exc:
        raise RuntimeError(f"Could not connect to VOICEVOX: {exc.reason}") from exc


def request_json(url: str) -> dict[str, Any]:
    return json.loads(request_bytes(url).decode("utf-8"))


def synthesize_item(
    engine_url: str,
    text: str,
    style_id: int,
    saved_query: dict[str, Any],
) -> bytes:
    query_url = f"{engine_url}/audio_query?{urlencode({'text': text, 'speaker': style_id})}"
    query = request_json(query_url)
    for setting in VOICE_SETTINGS:
        if setting in saved_query and saved_query[setting] is not None:
            query[setting] = saved_query[setting]
    synthesis_url = f"{engine_url}/synthesis?{urlencode({'speaker': style_id})}"
    return request_bytes(
        synthesis_url,
        json.dumps(query, ensure_ascii=False).encode("utf-8"),
    )


def concatenate_wavs(
    chunks: list[bytes], destination: Path
) -> tuple[float, int, list[float]]:
    if not chunks:
        raise ValueError("The project contains no talk items")

    parameters: tuple[int, int, int, str, str] | None = None
    frames: list[bytes] = []
    frame_count = 0
    chunk_durations: list[float] = []
    for chunk in chunks:
        with wave.open(io.BytesIO(chunk), "rb") as source:
            current = (
                source.getnchannels(),
                source.getsampwidth(),
                source.getframerate(),
                source.getcomptype(),
                source.getcompname(),
            )
            if parameters is None:
                parameters = current
            elif current != parameters:
                raise ValueError("VOICEVOX returned incompatible WAV formats")
            chunk_frame_count = source.getnframes()
            frame_count += chunk_frame_count
            chunk_durations.append(chunk_frame_count / source.getframerate())
            frames.append(source.readframes(chunk_frame_count))

    assert parameters is not None
    destination.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(destination), "wb") as output:
        output.setnchannels(parameters[0])
        output.setsampwidth(parameters[1])
        output.setframerate(parameters[2])
        output.setcomptype(parameters[3], parameters[4])
        for frame_data in frames:
            output.writeframes(frame_data)

    return frame_count / parameters[2], parameters[2], chunk_durations


def main() -> None:
    parser = argparse.ArgumentParser(description="VOICEVOX .vvproj talk exporter")
    parser.add_argument("project", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--engine-url", default="http://127.0.0.1:50021")
    parser.add_argument(
        "--cues-output",
        type=Path,
        help="Write subtitle timing metadata as JSON",
    )
    parser.add_argument(
        "--append-text",
        action="append",
        default=[],
        help="Append text using the final talk item's voice and settings",
    )
    parser.add_argument(
        "--replace-text",
        action="append",
        default=[],
        metavar="OLD=NEW",
        help="Replace text before synthesis without changing the source project",
    )
    args = parser.parse_args()

    replacements: list[tuple[str, str]] = []
    for replacement in args.replace_text:
        old, separator, new = replacement.partition("=")
        if not separator or not old:
            parser.error("--replace-text must use the format OLD=NEW")
        replacements.append((old, new))

    project = json.loads(args.project.read_text(encoding="utf-8"))
    talk = project.get("talk", {})
    audio_items = talk.get("audioItems", {})
    chunks: list[bytes] = []
    exported_text: list[str] = []
    final_style_id: int | None = None
    final_saved_query: dict[str, Any] = {}
    for audio_key in talk.get("audioKeys", []):
        item = audio_items.get(audio_key)
        if not isinstance(item, dict):
            continue
        text = str(item.get("text", "")).strip()
        if not text:
            continue
        for old, new in replacements:
            text = text.replace(old, new)
        voice = item.get("voice", {})
        style_id = int(voice["styleId"])
        saved_query = item.get("query") or {}
        chunks.append(
            synthesize_item(
                args.engine_url.rstrip("/"),
                text,
                style_id,
                saved_query,
            )
        )
        exported_text.append(text)
        final_style_id = style_id
        final_saved_query = saved_query

    for text in args.append_text:
        text = text.strip()
        if not text:
            continue
        if final_style_id is None:
            raise ValueError("Cannot append text because the project has no talk items")
        chunks.append(
            synthesize_item(
                args.engine_url.rstrip("/"),
                text,
                final_style_id,
                final_saved_query,
            )
        )
        exported_text.append(text)

    duration, sample_rate, chunk_durations = concatenate_wavs(chunks, args.output)
    if args.cues_output:
        cue_start = 0.0
        cues: list[dict[str, Any]] = []
        for text, chunk_duration in zip(exported_text, chunk_durations, strict=True):
            cue_end = cue_start + chunk_duration
            cues.append(
                {
                    "start": round(cue_start, 3),
                    "end": round(cue_end, 3),
                    "text": text,
                }
            )
            cue_start = cue_end
        args.cues_output.parent.mkdir(parents=True, exist_ok=True)
        args.cues_output.write_text(
            json.dumps(cues, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    print(
        json.dumps(
            {
                "output": str(args.output.resolve()),
                "items": len(chunks),
                "duration_seconds": round(duration, 3),
                "sample_rate": sample_rate,
                "cues_output": str(args.cues_output.resolve()) if args.cues_output else None,
                "text": exported_text,
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
