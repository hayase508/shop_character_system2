from __future__ import annotations

from collections import OrderedDict
import json
import logging
import threading
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .config import Settings


logger = logging.getLogger(__name__)


class VoicevoxError(RuntimeError):
    pass


class VoicevoxService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._cache: OrderedDict[str, bytes] = OrderedDict()
        self._cache_lock = threading.Lock()
        self._synthesis_lock = threading.Lock()
        self._last_error: str | None = None
        self._ready = False

    def synthesize(self, text: str) -> bytes:
        if not self.settings.voicevox_enabled:
            raise VoicevoxError("VOICEVOX is disabled")
        cache_key = text.strip()
        if not cache_key:
            raise VoicevoxError("VOICEVOX text is empty")
        with self._cache_lock:
            cached = self._cache.get(cache_key)
            if cached is not None:
                self._cache.move_to_end(cache_key)
                logger.info("[PERFORMANCE] VOICEVOX: memory cache hit")
                return cached
        started_at = time.perf_counter()
        try:
            with self._synthesis_lock:
                query_url = f"{self.settings.voicevox_engine_url}/audio_query?{urlencode({'text': text, 'speaker': self.settings.voicevox_speaker_id})}"
                query = self._request(query_url)
                query = self._configure_query(query)
                synthesis_url = f"{self.settings.voicevox_engine_url}/synthesis?{urlencode({'speaker': self.settings.voicevox_speaker_id})}"
                audio = self._request(
                    synthesis_url,
                    query,
                    "application/json; charset=utf-8",
                )
            if not self.is_wav(audio):
                raise VoicevoxError("VOICEVOX returned invalid WAV")
            self._ready = True
            self._last_error = None
        except Exception as exc:
            self._ready = False
            self._last_error = str(exc)
            raise
        logger.info(
            "[PERFORMANCE] VOICEVOX: %.3fs chars=%s",
            time.perf_counter() - started_at,
            len(cache_key),
        )
        if self.is_wav(audio) and self.settings.voicevox_cache_entries:
            with self._cache_lock:
                self._cache[cache_key] = audio
                self._cache.move_to_end(cache_key)
                while len(self._cache) > self.settings.voicevox_cache_entries:
                    self._cache.popitem(last=False)
        return audio

    def prepare(self) -> None:
        """Load the configured speaker into the local engine before it is needed."""
        self.synthesize("準備完了です。")

    def status(self) -> dict[str, str | None]:
        if not self.settings.voicevox_enabled:
            state = "disabled"
        elif self._ready:
            state = "ready"
        elif self._last_error:
            state = "unavailable"
        else:
            state = "not_checked"
        return {"status": state, "last_error": self._last_error}

    def _configure_query(self, query: bytes) -> bytes:
        try:
            payload = json.loads(query)
        except (UnicodeDecodeError, json.JSONDecodeError, TypeError) as exc:
            raise VoicevoxError("VOICEVOX returned an invalid audio query") from exc
        if not isinstance(payload, dict):
            raise VoicevoxError("VOICEVOX returned an invalid audio query")
        payload["speedScale"] = self.settings.voicevox_speed_scale
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")

    def _request(
        self,
        url: str,
        body: bytes | None = None,
        content_type: str | None = None,
    ) -> bytes:
        request = Request(url, data=body if body is not None else b"", method="POST")
        if content_type:
            request.add_header("Content-Type", content_type)
        try:
            with urlopen(request, timeout=self.settings.voicevox_timeout_seconds) as response:
                return response.read()
        except HTTPError as exc:
            raise VoicevoxError(f"VOICEVOX HTTP {exc.code}") from exc
        except (URLError, TimeoutError, OSError) as exc:
            raise VoicevoxError("VOICEVOX is unavailable") from exc

    @staticmethod
    def is_wav(data: bytes) -> bool:
        return len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WAVE"
