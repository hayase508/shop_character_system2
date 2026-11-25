"""Generate greeting WAV files and matching subtitle cue JSON with VOICEVOX."""

from __future__ import annotations

import argparse
from io import BytesIO
import json
from pathlib import Path
import wave

from app.config import load_settings
from app.customer_service import (
    FIRST_VISIT_GREETING_LINES,
    RETURNING_DISCOUNT_GREETING_LINES,
)
from app.voicevox_service import VoicevoxService


PROFILES = {
    "first-visit": FIRST_VISIT_GREETING_LINES,
    "returning-discount": RETURNING_DISCOUNT_GREETING_LINES,
}


def generate_profile(
    profile: str,
    lines: tuple[str, ...],
    output_dir: Path,
    voicevox: VoicevoxService,
) -> dict[str, object]:
    chunks: list[tuple[wave._wave_params, bytes, int]] = []
    cues: list[dict[str, object]] = []
    elapsed = 0.0
    expected_params: tuple[int, int, int, str] | None = None

    for line in lines:
        audio = voicevox.synthesize(line)
        with wave.open(BytesIO(audio), "rb") as reader:
            params = reader.getparams()
            signature = (
                params.nchannels,
                params.sampwidth,
                params.framerate,
                params.comptype,
            )
            if expected_params is None:
                expected_params = signature
            elif signature != expected_params:
                raise RuntimeError(f"VOICEVOX WAV format changed during {profile}")
            frames = reader.readframes(params.nframes)
            duration = params.nframes / params.framerate
            chunks.append((params, frames, params.nframes))
        cues.append(
            {
                "start": round(elapsed, 3),
                "end": round(elapsed + duration, 3),
                "text": line,
            }
        )
        elapsed += duration

    output_dir.mkdir(parents=True, exist_ok=True)
    wav_path = output_dir / f"{profile}.wav"
    wav_temporary = output_dir / f"{profile}.wav.tmp"
    first_params = chunks[0][0]
    with wave.open(str(wav_temporary), "wb") as writer:
        writer.setnchannels(first_params.nchannels)
        writer.setsampwidth(first_params.sampwidth)
        writer.setframerate(first_params.framerate)
        writer.setcomptype(first_params.comptype, first_params.compname)
        for _, frames, _ in chunks:
            writer.writeframes(frames)
    wav_temporary.replace(wav_path)

    cues_path = output_dir / f"{profile}.cues.json"
    cues_temporary = output_dir / f"{profile}.cues.json.tmp"
    cues_temporary.write_text(
        json.dumps(cues, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    cues_temporary.replace(cues_path)
    return {
        "profile": profile,
        "duration_seconds": round(elapsed, 3),
        "wav": str(wav_path),
        "cues": str(cues_path),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "profiles",
        nargs="*",
        choices=tuple(PROFILES),
        default=list(PROFILES),
    )
    parser.add_argument("--output-dir", type=Path, default=Path("static/audio"))
    args = parser.parse_args()

    voicevox = VoicevoxService(load_settings())
    generated = [
        generate_profile(profile, PROFILES[profile], args.output_dir, voicevox)
        for profile in args.profiles
    ]
    print(json.dumps({"generated": generated}, ensure_ascii=False))


if __name__ == "__main__":
    main()
