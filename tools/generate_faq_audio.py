"""Generate prerecorded local FAQ responses with the configured VOICEVOX voice."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.config import load_settings
from app.question_service import LOCAL_VOICE_LINES
from app.voicevox_service import VoicevoxService


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate fast FAQ response WAV files")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("static/audio/faq"),
    )
    parser.add_argument(
        "--keys",
        nargs="+",
        help="Generate only the listed LOCAL_VOICE_LINES keys",
    )
    args = parser.parse_args()

    settings = load_settings()
    voicevox = VoicevoxService(settings)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    generated: list[dict[str, object]] = []

    selected_keys = args.keys or list(LOCAL_VOICE_LINES)
    unknown_keys = [key for key in selected_keys if key not in LOCAL_VOICE_LINES]
    if unknown_keys:
        parser.error(f"unknown audio keys: {', '.join(unknown_keys)}")

    for audio_key in selected_keys:
        text = LOCAL_VOICE_LINES[audio_key]
        audio = voicevox.synthesize(text)
        if not voicevox.is_wav(audio):
            raise RuntimeError(f"VOICEVOX returned invalid WAV for {audio_key}")
        destination = args.output_dir / f"{audio_key}.wav"
        temporary = destination.with_suffix(".wav.tmp")
        temporary.write_bytes(audio)
        temporary.replace(destination)
        generated.append(
            {"audio_key": audio_key, "bytes": len(audio), "output": str(destination)}
        )

    print(json.dumps({"generated": generated}, ensure_ascii=False))


if __name__ == "__main__":
    main()
