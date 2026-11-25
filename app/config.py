from __future__ import annotations

import os
import math
from dataclasses import dataclass
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_WHISPER_INITIAL_PROMPT = (
    "いちごうカフェの店内で、お客様が鬼店員へ日本語で短い質問をしています。"
)
DEFAULT_WHISPER_HOTWORDS = (
    "いちごうカフェ 鬼 鬼さん 鬼店員 豚汁 たまご定食 お代わり コーヒー お茶 飲み物 "
    "QRコード 精算機 セルフサービス"
)


def _as_bool(value: str | None, default: bool) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _as_path(value: str | None, default: Path, base_dir: Path) -> Path:
    path = Path(value) if value else default
    return path if path.is_absolute() else (base_dir / path).resolve()


@dataclass(frozen=True, slots=True)
class Settings:
    base_dir: Path = BASE_DIR
    database_path: Path = BASE_DIR / "data" / "shop.db"
    static_dir: Path = BASE_DIR / "static"
    camera_enabled: bool = True
    camera_index: int = 0
    camera_backend: str = "auto"
    camera_width: int = 1280
    camera_height: int = 720
    camera_fps: float = 15.0
    camera_retry_seconds: float = 5.0
    face_match_threshold: float = 0.5
    face_frame_skip: int = 5
    face_image_scale: float = 0.25
    face_detection_model: str = "hog"
    face_confirmation_count: int = 2
    face_confirmation_window_seconds: float = 4.0
    camera_event_cooldown_seconds: float = 2.0
    person_cooldown_seconds: float = 20.0
    global_cooldown_seconds: float = 5.0
    visit_cooldown_minutes: float = 60.0
    discount_valid_days: int = 60
    greeting_timeout_seconds: float = 190.0
    debug_mode: bool = False
    log_level: str = "INFO"
    access_log: bool = False
    host: str = "127.0.0.1"
    port: int = 8000
    idle_video_url: str = "/static/videos/idle_optimized.mp4"
    welcome_video_url: str = "/static/videos/yobidashi_mobile.mp4"
    returning_video_url: str = "/static/videos/yobidashi_mobile.mp4"
    speaking_intro_video_url: str = "/static/videos/shinfurimuki_optimized.mp4"
    speaking_loop_video_url: str = "/static/videos/yobidashi_mobile.mp4"
    welcome_audio_url: str = "/static/audio/first-visit.wav"
    returning_audio_url: str = "/static/audio/returning.wav"
    returning_discount_audio_url: str = "/static/audio/returning-discount.wav"
    browser_greeting_timeout_seconds: int = 180
    question_enabled: bool = True
    question_ready_timeout_seconds: float = 40.0
    question_recording_max_seconds: float = 15.0
    question_session_timeout_seconds: float = 60.0
    question_speaking_timeout_seconds: float = 45.0
    question_audio_max_bytes: int = 10 * 1024 * 1024
    question_audio_bitrate: int = 128000
    question_unknown_policy: str = "staff"
    question_input_mode: str = "touch"
    microphone_device_label: str = ""
    assistance_voice_enabled: bool = True
    assistance_voice_cooldown_seconds: float = 20.0
    assistance_voice_start_threshold: float = 0.010
    assistance_voice_start_duration_ms: float = 200.0
    assistance_voice_calibration_ms: float = 500.0
    assistance_voice_noise_multiplier: float = 1.4
    assistance_voice_noise_margin: float = 0.0025
    assistance_voice_speech_band_ratio: float = 0.20
    assistance_voice_zcr_min: float = 0.001
    assistance_voice_zcr_max: float = 0.45
    whisper_model: str = "base"
    whisper_device: str = "cpu"
    whisper_compute_type: str = "int8"
    whisper_timeout_seconds: float = 30.0
    whisper_beam_size: int = 3
    whisper_max_new_tokens: int = 80
    whisper_initial_prompt: str = DEFAULT_WHISPER_INITIAL_PROMPT
    whisper_hotwords: str = DEFAULT_WHISPER_HOTWORDS
    whisper_domain_corrections: bool = True
    whisper_no_speech_threshold: float = 0.45
    whisper_min_avg_logprob: float = -0.8
    whisper_vad_filter: bool = True
    whisper_vad_min_speech_ms: int = 400
    whisper_vad_min_silence_ms: int = 350
    whisper_vad_speech_pad_ms: int = 200
    vad_enabled: bool = True
    vad_start_threshold: float = 0.025
    vad_start_duration_ms: int = 350
    vad_end_silence_ms: int = 450
    vad_min_speech_ms: int = 500
    vad_resume_delay_ms: int = 800
    vad_preroll_ms: int = 450
    vad_calibration_ms: int = 1200
    vad_noise_multiplier: float = 1.8
    vad_noise_margin: float = 0.006
    gemini_enabled: bool = True
    gemini_api_key: str = ""
    gemini_model: str = "gemini-3.5-flash-lite"
    gemini_timeout_seconds: float = 10.0
    gemini_max_output_tokens: int = 100
    gemini_max_requests_per_session: int = 3
    gemini_cache_ttl_seconds: int = 3600
    gemini_max_question_chars: int = 200
    gemini_thinking_level: str = "minimal"
    gemini_preload: bool = True
    gemini_warmup: bool = True
    voicevox_enabled: bool = True
    voicevox_engine_url: str = "http://127.0.0.1:50021"
    voicevox_speaker_id: int = 2
    voicevox_timeout_seconds: float = 15.0
    voicevox_cache_entries: int = 64
    voicevox_speed_scale: float = 1.08
    voicevox_preload: bool = True

    def __post_init__(self) -> None:
        positive = ("camera_width", "camera_height", "camera_fps", "camera_retry_seconds",
                    "face_frame_skip", "face_confirmation_count",
                    "face_confirmation_window_seconds", "camera_event_cooldown_seconds",
                    "greeting_timeout_seconds", "browser_greeting_timeout_seconds",
                    "question_ready_timeout_seconds", "question_recording_max_seconds",
                    "question_session_timeout_seconds", "question_speaking_timeout_seconds",
                    "question_audio_max_bytes", "question_audio_bitrate",
                    "assistance_voice_cooldown_seconds",
                    "assistance_voice_start_duration_ms",
                    "assistance_voice_calibration_ms",
                    "assistance_voice_noise_multiplier",
                    "assistance_voice_noise_margin",
                    "whisper_timeout_seconds", "whisper_beam_size",
                    "whisper_max_new_tokens", "whisper_vad_min_speech_ms",
                    "whisper_vad_min_silence_ms", "whisper_vad_speech_pad_ms",
                    "vad_start_duration_ms", "vad_end_silence_ms", "vad_min_speech_ms",
                    "vad_preroll_ms", "vad_calibration_ms", "vad_noise_multiplier",
                    "vad_noise_margin", "gemini_timeout_seconds",
                    "gemini_max_output_tokens", "gemini_cache_ttl_seconds",
                    "gemini_max_question_chars", "voicevox_timeout_seconds")
        for name in positive:
            if not math.isfinite(getattr(self, name)) or getattr(self, name) <= 0:
                raise ValueError(f"{name.upper()} must be positive")
        for name in ("person_cooldown_seconds", "global_cooldown_seconds",
                     "visit_cooldown_minutes", "discount_valid_days", "camera_index"):
            if not math.isfinite(getattr(self, name)) or getattr(self, name) < 0:
                raise ValueError(f"{name.upper()} must not be negative")
        if not 0 < self.face_match_threshold <= 1 or not 0 < self.face_image_scale <= 1:
            raise ValueError("Face threshold and scale must be in (0, 1]")
        if not 0 < self.vad_start_threshold <= 1:
            raise ValueError("VAD_START_THRESHOLD must be in (0, 1]")
        if not 0 < self.assistance_voice_start_threshold <= 1:
            raise ValueError("ASSISTANCE_VOICE_START_THRESHOLD must be in (0, 1]")
        if not 0 < self.assistance_voice_speech_band_ratio <= 1:
            raise ValueError("ASSISTANCE_VOICE_SPEECH_BAND_RATIO must be in (0, 1]")
        if not 0 <= self.assistance_voice_zcr_min < self.assistance_voice_zcr_max <= 1:
            raise ValueError("Assistance voice ZCR range must satisfy 0 <= min < max <= 1")
        if not 1 <= self.assistance_voice_noise_multiplier <= 10:
            raise ValueError("ASSISTANCE_VOICE_NOISE_MULTIPLIER must be in [1, 10]")
        if not 0 < self.assistance_voice_noise_margin <= 1:
            raise ValueError("ASSISTANCE_VOICE_NOISE_MARGIN must be in (0, 1]")
        if not 0 <= self.whisper_no_speech_threshold <= 1:
            raise ValueError("WHISPER_NO_SPEECH_THRESHOLD must be in [0, 1]")
        if not -10 <= self.whisper_min_avg_logprob <= 0:
            raise ValueError("WHISPER_MIN_AVG_LOGPROB must be in [-10, 0]")
        if not 1 <= self.vad_noise_multiplier <= 10:
            raise ValueError("VAD_NOISE_MULTIPLIER must be in [1, 10]")
        if not 0 < self.vad_noise_margin <= 1:
            raise ValueError("VAD_NOISE_MARGIN must be in (0, 1]")
        if (
            self.vad_resume_delay_ms < 0
            or self.gemini_max_requests_per_session < 0
            or self.voicevox_speaker_id < 0
            or self.voicevox_cache_entries < 0
        ):
            raise ValueError(
                "VAD delay, Gemini limit and VOICEVOX cache size must not be negative"
            )
        if self.vad_min_speech_ms > self.question_recording_max_seconds * 1000:
            raise ValueError("VAD_MIN_SPEECH_MS must not exceed recording maximum")
        if self.camera_backend not in {"auto", "dshow", "msmf"}:
            raise ValueError("CAMERA_BACKEND must be auto, dshow or msmf")
        if self.face_detection_model not in {"hog", "cnn"}:
            raise ValueError("FACE_DETECTION_MODEL must be hog or cnn")
        if not 1 <= self.port <= 65535:
            raise ValueError("PORT must be in 1..65535")
        if not self.whisper_model.strip() or not self.whisper_device.strip() or not self.whisper_compute_type.strip():
            raise ValueError("Whisper model, device and compute type must not be empty")
        if not 0.5 <= self.voicevox_speed_scale <= 2.0:
            raise ValueError("VOICEVOX_SPEED_SCALE must be in [0.5, 2.0]")
        if self.gemini_thinking_level not in {"minimal", "low", "medium", "high"}:
            raise ValueError("GEMINI_THINKING_LEVEL must be minimal, low, medium or high")
        if self.question_unknown_policy not in {"staff", "gemini"}:
            raise ValueError("QUESTION_UNKNOWN_POLICY must be staff or gemini")
        if self.question_input_mode not in {"microphone", "touch", "both"}:
            raise ValueError("QUESTION_INPUT_MODE must be microphone, touch or both")
        if self.gemini_enabled and not self.gemini_model.strip():
            raise ValueError("GEMINI_MODEL must not be empty when Gemini is enabled")
        if not self.voicevox_engine_url.startswith(("http://127.0.0.1:", "http://localhost:")):
            raise ValueError("VOICEVOX_ENGINE_URL must use local HTTP")
        for url in (
            self.idle_video_url,
            self.welcome_video_url,
            self.returning_video_url,
            self.speaking_intro_video_url,
            self.speaking_loop_video_url,
        ):
            if not url.startswith("/static/videos/") or ".." in url or "\\" in url:
                raise ValueError("Character videos must be paths below /static/videos/")
        for url in (
            self.welcome_audio_url,
            self.returning_audio_url,
            self.returning_discount_audio_url,
        ):
            if not url.startswith("/static/audio/") or ".." in url or "\\" in url:
                raise ValueError("Character audio must be a path below /static/audio/")


def load_settings(env_file: Path | None = None) -> Settings:
    base_dir = BASE_DIR
    dotenv_path = env_file or base_dir / ".env"
    try:
        from dotenv import load_dotenv

        load_dotenv(dotenv_path=dotenv_path, override=False)
    except ImportError:
        # .env読み込みだけが使えない場合も、OS環境変数でサーバーを起動できる。
        pass

    return Settings(
        base_dir=base_dir,
        database_path=_as_path(os.getenv("DATABASE_PATH"), Path("data/shop.db"), base_dir),
        static_dir=_as_path(os.getenv("STATIC_DIR"), Path("static"), base_dir),
        camera_enabled=_as_bool(os.getenv("CAMERA_ENABLED"), True),
        camera_index=int(os.getenv("CAMERA_INDEX", "0")),
        camera_backend=os.getenv("CAMERA_BACKEND", "auto").strip().lower(),
        camera_width=int(os.getenv("CAMERA_WIDTH", "1280")),
        camera_height=int(os.getenv("CAMERA_HEIGHT", "720")),
        camera_fps=float(os.getenv("CAMERA_FPS", "15")),
        camera_retry_seconds=float(os.getenv("CAMERA_RETRY_SECONDS", "5")),
        face_match_threshold=float(os.getenv("FACE_MATCH_THRESHOLD", "0.5")),
        face_frame_skip=int(os.getenv("FACE_FRAME_SKIP", "5")),
        face_image_scale=float(os.getenv("FACE_IMAGE_SCALE", "0.25")),
        face_detection_model=os.getenv("FACE_DETECTION_MODEL", "hog").strip().lower(),
        face_confirmation_count=int(os.getenv("FACE_CONFIRMATION_COUNT", "2")),
        face_confirmation_window_seconds=float(
            os.getenv("FACE_CONFIRMATION_WINDOW_SECONDS", "4")
        ),
        camera_event_cooldown_seconds=float(
            os.getenv("CAMERA_EVENT_COOLDOWN_SECONDS", "2")
        ),
        person_cooldown_seconds=float(os.getenv("PERSON_COOLDOWN_SECONDS", "20")),
        global_cooldown_seconds=float(os.getenv("GLOBAL_COOLDOWN_SECONDS", "5")),
        visit_cooldown_minutes=float(os.getenv("VISIT_COOLDOWN_MINUTES", "60")),
        discount_valid_days=int(os.getenv("DISCOUNT_VALID_DAYS", "60")),
        greeting_timeout_seconds=float(os.getenv("GREETING_TIMEOUT_SECONDS", "190")),
        debug_mode=_as_bool(os.getenv("DEBUG_MODE"), False),
        log_level=os.getenv("LOG_LEVEL", "INFO").upper(),
        access_log=_as_bool(os.getenv("ACCESS_LOG"), False),
        host=os.getenv("HOST", "127.0.0.1"),
        port=int(os.getenv("PORT", "8000")),
        idle_video_url=os.getenv(
            "CHARACTER_VIDEO_IDLE", "/static/videos/idle_optimized.mp4"
        ),
        welcome_video_url=os.getenv(
            "CHARACTER_VIDEO_WELCOME", "/static/videos/yobidashi_mobile.mp4"
        ),
        returning_video_url=os.getenv(
            "CHARACTER_VIDEO_RETURNING", "/static/videos/yobidashi_mobile.mp4"
        ),
        speaking_intro_video_url=os.getenv(
            "CHARACTER_VIDEO_SPEAKING_INTRO", "/static/videos/shinfurimuki_optimized.mp4"
        ),
        speaking_loop_video_url=os.getenv(
            "CHARACTER_VIDEO_SPEAKING_LOOP", "/static/videos/yobidashi_mobile.mp4"
        ),
        welcome_audio_url=os.getenv(
            "CHARACTER_AUDIO_WELCOME", "/static/audio/first-visit.wav"
        ),
        returning_audio_url=os.getenv(
            "CHARACTER_AUDIO_RETURNING", "/static/audio/returning.wav"
        ),
        returning_discount_audio_url=os.getenv(
            "CHARACTER_AUDIO_RETURNING_DISCOUNT",
            "/static/audio/returning-discount.wav",
        ),
        browser_greeting_timeout_seconds=int(
            os.getenv("BROWSER_GREETING_TIMEOUT_SECONDS", "180")
        ),
        question_enabled=_as_bool(os.getenv("QUESTION_ENABLED"), True),
        question_ready_timeout_seconds=float(
            os.getenv("QUESTION_READY_TIMEOUT_SECONDS", "40")
        ),
        question_recording_max_seconds=float(
            os.getenv("QUESTION_RECORDING_MAX_SECONDS", "15")
        ),
        question_session_timeout_seconds=float(
            os.getenv("QUESTION_SESSION_TIMEOUT_SECONDS", "60")
        ),
        question_speaking_timeout_seconds=float(
            os.getenv("QUESTION_SPEAKING_TIMEOUT_SECONDS", "45")
        ),
        question_audio_max_bytes=int(os.getenv("QUESTION_AUDIO_MAX_BYTES", str(10 * 1024 * 1024))),
        question_audio_bitrate=int(os.getenv("QUESTION_AUDIO_BITRATE", "128000")),
        question_unknown_policy=os.getenv(
            "QUESTION_UNKNOWN_POLICY", "staff"
        ).strip().lower(),
        question_input_mode=os.getenv(
            "QUESTION_INPUT_MODE", "touch"
        ).strip().lower(),
        microphone_device_label=os.getenv("MICROPHONE_DEVICE_LABEL", "").strip(),
        assistance_voice_enabled=_as_bool(
            os.getenv("ASSISTANCE_VOICE_ENABLED"), True
        ),
        assistance_voice_cooldown_seconds=float(
            os.getenv("ASSISTANCE_VOICE_COOLDOWN_SECONDS", "20")
        ),
        assistance_voice_start_threshold=float(
            os.getenv("ASSISTANCE_VOICE_START_THRESHOLD", "0.010")
        ),
        assistance_voice_start_duration_ms=float(
            os.getenv("ASSISTANCE_VOICE_START_DURATION_MS", "200")
        ),
        assistance_voice_calibration_ms=float(
            os.getenv("ASSISTANCE_VOICE_CALIBRATION_MS", "500")
        ),
        assistance_voice_noise_multiplier=float(
            os.getenv("ASSISTANCE_VOICE_NOISE_MULTIPLIER", "1.4")
        ),
        assistance_voice_noise_margin=float(
            os.getenv("ASSISTANCE_VOICE_NOISE_MARGIN", "0.0025")
        ),
        assistance_voice_speech_band_ratio=float(
            os.getenv("ASSISTANCE_VOICE_SPEECH_BAND_RATIO", "0.20")
        ),
        assistance_voice_zcr_min=float(
            os.getenv("ASSISTANCE_VOICE_ZCR_MIN", "0.001")
        ),
        assistance_voice_zcr_max=float(
            os.getenv("ASSISTANCE_VOICE_ZCR_MAX", "0.45")
        ),
        whisper_model=os.getenv("WHISPER_MODEL", "base").strip(),
        whisper_device=os.getenv("WHISPER_DEVICE", "cpu").strip(),
        whisper_compute_type=os.getenv("WHISPER_COMPUTE_TYPE", "int8").strip(),
        whisper_timeout_seconds=float(os.getenv("WHISPER_TIMEOUT_SECONDS", "30")),
        whisper_beam_size=int(os.getenv("WHISPER_BEAM_SIZE", "3")),
        whisper_max_new_tokens=int(os.getenv("WHISPER_MAX_NEW_TOKENS", "80")),
        whisper_initial_prompt=os.getenv(
            "WHISPER_INITIAL_PROMPT",
            DEFAULT_WHISPER_INITIAL_PROMPT,
        ).strip(),
        whisper_hotwords=os.getenv(
            "WHISPER_HOTWORDS",
            DEFAULT_WHISPER_HOTWORDS,
        ).strip(),
        whisper_domain_corrections=_as_bool(
            os.getenv("WHISPER_DOMAIN_CORRECTIONS"), True
        ),
        whisper_no_speech_threshold=float(
            os.getenv("WHISPER_NO_SPEECH_THRESHOLD", "0.45")
        ),
        whisper_min_avg_logprob=float(
            os.getenv("WHISPER_MIN_AVG_LOGPROB", "-0.8")
        ),
        whisper_vad_filter=_as_bool(os.getenv("WHISPER_VAD_FILTER"), True),
        whisper_vad_min_speech_ms=int(
            os.getenv("WHISPER_VAD_MIN_SPEECH_MS", "400")
        ),
        whisper_vad_min_silence_ms=int(
            os.getenv("WHISPER_VAD_MIN_SILENCE_MS", "350")
        ),
        whisper_vad_speech_pad_ms=int(
            os.getenv("WHISPER_VAD_SPEECH_PAD_MS", "200")
        ),
        vad_enabled=_as_bool(os.getenv("VAD_ENABLED"), True),
        vad_start_threshold=float(os.getenv("VAD_START_THRESHOLD", "0.025")),
        vad_start_duration_ms=int(os.getenv("VAD_START_DURATION_MS", "350")),
        vad_end_silence_ms=int(os.getenv("VAD_END_SILENCE_MS", "450")),
        vad_min_speech_ms=int(os.getenv("VAD_MIN_SPEECH_MS", "500")),
        vad_resume_delay_ms=int(os.getenv("VAD_RESUME_DELAY_MS", "800")),
        vad_preroll_ms=int(os.getenv("VAD_PREROLL_MS", "450")),
        vad_calibration_ms=int(os.getenv("VAD_CALIBRATION_MS", "1200")),
        vad_noise_multiplier=float(os.getenv("VAD_NOISE_MULTIPLIER", "1.8")),
        vad_noise_margin=float(os.getenv("VAD_NOISE_MARGIN", "0.006")),
        gemini_enabled=_as_bool(os.getenv("GEMINI_ENABLED"), True),
        gemini_api_key=os.getenv("GEMINI_API_KEY", "").strip(),
        gemini_model=os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite").strip(),
        gemini_timeout_seconds=float(os.getenv("GEMINI_TIMEOUT_SECONDS", "10")),
        gemini_max_output_tokens=int(os.getenv("GEMINI_MAX_OUTPUT_TOKENS", "100")),
        gemini_max_requests_per_session=int(
            os.getenv("GEMINI_MAX_REQUESTS_PER_SESSION", "3")
        ),
        gemini_cache_ttl_seconds=int(os.getenv("GEMINI_CACHE_TTL_SECONDS", "3600")),
        gemini_max_question_chars=int(os.getenv("GEMINI_MAX_QUESTION_CHARS", "200")),
        gemini_thinking_level=os.getenv("GEMINI_THINKING_LEVEL", "minimal").strip().lower(),
        gemini_preload=_as_bool(os.getenv("GEMINI_PRELOAD"), True),
        gemini_warmup=_as_bool(os.getenv("GEMINI_WARMUP"), True),
        voicevox_enabled=_as_bool(os.getenv("VOICEVOX_ENABLED"), True),
        voicevox_engine_url=os.getenv(
            "VOICEVOX_ENGINE_URL", "http://127.0.0.1:50021"
        ).rstrip("/"),
        voicevox_speaker_id=int(os.getenv("VOICEVOX_SPEAKER_ID", "2")),
        voicevox_timeout_seconds=float(os.getenv("VOICEVOX_TIMEOUT_SECONDS", "15")),
        voicevox_cache_entries=int(os.getenv("VOICEVOX_CACHE_ENTRIES", "64")),
        voicevox_speed_scale=float(os.getenv("VOICEVOX_SPEED_SCALE", "1.08")),
        voicevox_preload=_as_bool(os.getenv("VOICEVOX_PRELOAD"), True),
    )
