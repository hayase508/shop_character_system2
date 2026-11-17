"""Download and validate the configured faster-whisper model for offline use."""

from app.config import load_settings
from app.speech_service import SpeechRecognizer


def main() -> None:
    settings = load_settings()
    recognizer = SpeechRecognizer(settings)
    print(
        "Whisperモデルを準備します: "
        f"model={settings.whisper_model} device={settings.whisper_device} "
        f"compute_type={settings.whisper_compute_type}"
    )
    recognizer.prepare()
    print("Whisperモデルの準備が完了しました。")


if __name__ == "__main__":
    main()
