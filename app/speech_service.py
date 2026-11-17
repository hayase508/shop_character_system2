from __future__ import annotations

import io
import logging
import re
import threading
import time
from typing import Any

from .config import Settings


logger = logging.getLogger(__name__)


_DOMAIN_CORRECTIONS: tuple[tuple[str, str], ...] = (
    (r"お兄さん", "鬼さん"),
    (r"(?:トン|とん)ジル", "豚汁"),
    (r"(?:トン|とん)汁", "豚汁"),
    (r"(?:ポン|ぽん|本|盆)(?:ジル|じる|汁)", "豚汁"),
    (r"(?:玉|卵)ご", "たまご"),
    (r"コーヒ(?!ー)", "コーヒー"),
    (r"イクラ", "いくら"),
    (r"QR\s*コード", "QRコード"),
    (r"かさせば", "かざせば"),
    (r"一号カフェ", "いちごうカフェ"),
)

_SILENCE_HALLUCINATIONS = {
    "ご視聴ありがとうございました",
    "ご清聴ありがとうございました",
    "チャンネル登録をお願いします",
    "ありがとうございました",
}


def correct_domain_transcription(text: str) -> str:
    """Repair conservative, repeatable Whisper errors for this shop vocabulary."""
    corrected = text
    for pattern, replacement in _DOMAIN_CORRECTIONS:
        corrected = re.sub(pattern, replacement, corrected, flags=re.IGNORECASE)
    return corrected


def is_likely_silence_hallucination(text: str) -> bool:
    compact = re.sub(r"[\s、。,.!?！？]", "", text)
    return compact in _SILENCE_HALLUCINATIONS


class SpeechRecognitionError(RuntimeError):
    pass


class SpeechRecognizer:
    """Lazily loads one faster-whisper model and reuses it for all questions."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._model: Any | None = None
        self._lock = threading.Lock()
        self._last_error: str | None = None
        self._loading = False

    def status(self) -> dict[str, str | None]:
        if self._model is not None:
            status = "ready"
        elif self._loading:
            status = "loading"
        elif self._last_error:
            status = "error"
        else:
            status = "lazy"
        return {"status": status, "last_error": self._last_error}

    def prepare(self) -> None:
        """Download/load the configured model once during initial setup."""
        with self._lock:
            self._loading = True
            try:
                self._load_model()
            finally:
                self._loading = False

    def transcribe(self, audio: bytes) -> str:
        if not audio:
            raise SpeechRecognitionError("audio is empty")
        with self._lock:
            started_at = time.perf_counter()
            try:
                self._loading = True
                model = self._load_model()
                vad_parameters = None
                if self.settings.whisper_vad_filter:
                    vad_parameters = {
                        "min_speech_duration_ms": self.settings.whisper_vad_min_speech_ms,
                        "min_silence_duration_ms": self.settings.whisper_vad_min_silence_ms,
                        "speech_pad_ms": self.settings.whisper_vad_speech_pad_ms,
                    }
                segments, _ = model.transcribe(
                    io.BytesIO(audio),
                    language="ja",
                    beam_size=self.settings.whisper_beam_size,
                    best_of=1,
                    temperature=0.0,
                    condition_on_previous_text=False,
                    # Browser VAD reacts quickly for the UI. Silero VAD is a
                    # second, server-side guard against fans, dishes and echo.
                    vad_filter=self.settings.whisper_vad_filter,
                    vad_parameters=vad_parameters,
                    without_timestamps=True,
                    initial_prompt=self.settings.whisper_initial_prompt or None,
                    hotwords=self.settings.whisper_hotwords or None,
                    max_new_tokens=self.settings.whisper_max_new_tokens,
                    no_speech_threshold=self.settings.whisper_no_speech_threshold,
                    log_prob_threshold=self.settings.whisper_min_avg_logprob,
                )
                accepted_segments: list[str] = []
                rejected_segments = 0
                total_segments = 0
                for segment in segments:
                    total_segments += 1
                    no_speech_probability = float(
                        getattr(segment, "no_speech_prob", 0.0) or 0.0
                    )
                    average_log_probability = float(
                        getattr(segment, "avg_logprob", 0.0) or 0.0
                    )
                    if (
                        no_speech_probability >= self.settings.whisper_no_speech_threshold
                        or average_log_probability < self.settings.whisper_min_avg_logprob
                    ):
                        rejected_segments += 1
                        continue
                    accepted_segments.append(str(segment.text))
                logger.info(
                    "[WHISPER] Confidence filter: accepted=%s rejected=%s",
                    total_segments - rejected_segments,
                    rejected_segments,
                )
                text = "".join(accepted_segments)
                text = re.sub(r"\s+", " ", text).strip()
                if is_likely_silence_hallucination(text):
                    logger.info("[WHISPER] Common silence hallucination discarded")
                    return ""
                if self.settings.whisper_domain_corrections:
                    text = correct_domain_transcription(text)
                return text
            except SpeechRecognitionError:
                raise
            except Exception as exc:
                self._last_error = type(exc).__name__
                raise SpeechRecognitionError("local transcription failed") from exc
            finally:
                self._loading = False
                logger.info(
                    "[PERFORMANCE] Whisper: %.3fs bytes=%s",
                    time.perf_counter() - started_at,
                    len(audio),
                )

    def _load_model(self) -> Any:
        if self._model is not None:
            return self._model
        try:
            from faster_whisper import WhisperModel
        except ImportError as exc:
            self._last_error = "dependency_missing"
            raise SpeechRecognitionError("faster-whisper is not installed") from exc
        logger.info(
            "[WHISPER] Loading model=%s device=%s compute_type=%s",
            self.settings.whisper_model,
            self.settings.whisper_device,
            self.settings.whisper_compute_type,
        )
        self._model = WhisperModel(
            self.settings.whisper_model,
            device=self.settings.whisper_device,
            compute_type=self.settings.whisper_compute_type,
        )
        self._last_error = None
        logger.info("[WHISPER] Model ready")
        return self._model
