from __future__ import annotations

import os
import math
from dataclasses import dataclass
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent


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
    host: str = "127.0.0.1"
    port: int = 8000
    idle_video_url: str = "/static/videos/idle.mp4"
    welcome_video_url: str = "/static/videos/yobidashi_mobile.mp4"
    returning_video_url: str = "/static/videos/yobidashi_mobile.mp4"
    welcome_audio_url: str = "/static/audio/first-visit.wav"
    returning_audio_url: str = "/static/audio/returning.wav"
    returning_discount_audio_url: str = "/static/audio/returning-discount.wav"
    browser_greeting_timeout_seconds: int = 180

    def __post_init__(self) -> None:
        positive = ("camera_width", "camera_height", "camera_retry_seconds",
                    "face_frame_skip", "face_confirmation_count",
                    "face_confirmation_window_seconds", "camera_event_cooldown_seconds",
                    "greeting_timeout_seconds", "browser_greeting_timeout_seconds")
        for name in positive:
            if not math.isfinite(getattr(self, name)) or getattr(self, name) <= 0:
                raise ValueError(f"{name.upper()} must be positive")
        for name in ("person_cooldown_seconds", "global_cooldown_seconds",
                     "visit_cooldown_minutes", "discount_valid_days", "camera_index"):
            if not math.isfinite(getattr(self, name)) or getattr(self, name) < 0:
                raise ValueError(f"{name.upper()} must not be negative")
        if not 0 < self.face_match_threshold <= 1 or not 0 < self.face_image_scale <= 1:
            raise ValueError("Face threshold and scale must be in (0, 1]")
        if self.camera_backend not in {"auto", "dshow", "msmf"}:
            raise ValueError("CAMERA_BACKEND must be auto, dshow or msmf")
        if self.face_detection_model not in {"hog", "cnn"}:
            raise ValueError("FACE_DETECTION_MODEL must be hog or cnn")
        if not 1 <= self.port <= 65535:
            raise ValueError("PORT must be in 1..65535")
        for url in (self.idle_video_url, self.welcome_video_url, self.returning_video_url):
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
        host=os.getenv("HOST", "127.0.0.1"),
        port=int(os.getenv("PORT", "8000")),
        idle_video_url=os.getenv(
            "CHARACTER_VIDEO_IDLE", "/static/videos/idle.mp4"
        ),
        welcome_video_url=os.getenv(
            "CHARACTER_VIDEO_WELCOME", "/static/videos/yobidashi_mobile.mp4"
        ),
        returning_video_url=os.getenv(
            "CHARACTER_VIDEO_RETURNING", "/static/videos/yobidashi_mobile.mp4"
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
    )
