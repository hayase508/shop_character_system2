from __future__ import annotations

import asyncio
import base64
import json
import logging
import threading
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .camera import CameraWorker
from .config import Settings, load_settings
from .customer_service import CustomerService, build_greeting_message
from .database import Database
from .question_service import (
    GeminiService,
    QuestionAnswerService,
    QuestionContext,
    get_touch_question,
    touch_question_catalog,
)
from .reception import QuestionConflictError, ReceptionController
from .speech_service import SpeechRecognizer
from .voicevox_service import VoicevoxService
from .websocket_manager import WebSocketManager


logger = logging.getLogger(__name__)


def create_app(settings: Settings | None = None) -> FastAPI:
    app_settings = settings or load_settings()
    logging.basicConfig(
        level=getattr(logging, app_settings.log_level, logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    database = Database(app_settings.database_path)
    customer_service = CustomerService(database, app_settings)
    websocket_manager = WebSocketManager()
    speech_recognizer = SpeechRecognizer(app_settings)
    gemini = GeminiService(app_settings)
    question_answers = QuestionAnswerService(app_settings, gemini)
    voicevox = VoicevoxService(app_settings)
    reception = ReceptionController(
        customer_service,
        websocket_manager,
        app_settings,
        speech_recognizer,
        question_answers,
        voicevox,
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.db_ready = False
        try:
            database.initialize()
            app.state.db_ready = True
            logger.info("[DB] Database ready: %s", app_settings.database_path)
        except Exception:
            logger.exception("[DB] Server will continue without customer persistence")

        camera: CameraWorker | None = None
        if app_settings.camera_enabled:
            loop = asyncio.get_running_loop()
            pending = threading.Semaphore(1)

            def on_confirmed_face(encoding: tuple[float, ...]) -> None:
                if not pending.acquire(blocking=False):
                    return
                future = asyncio.run_coroutine_threadsafe(
                    reception.process_face_encoding(encoding),
                    loop,
                )

                def log_failure(completed: Any) -> None:
                    try:
                        completed.result()
                    except Exception:
                        logger.exception("[FACE] Failed to process confirmed face")
                    finally:
                        pending.release()

                future.add_done_callback(log_failure)

            camera = CameraWorker(app_settings, on_confirmed_face)
            camera.start()
        app.state.camera = camera
        logger.info("[STATE] IDLE")
        for url in {
            app_settings.idle_video_url,
            app_settings.welcome_video_url,
            app_settings.returning_video_url,
            app_settings.speaking_intro_video_url,
            app_settings.speaking_loop_video_url,
        }:
            if not (app_settings.static_dir / url.removeprefix("/static/")).is_file():
                logger.error("[VIDEO] File not found: %s; display will use fallback", url)
        for url in {
            app_settings.welcome_audio_url,
            app_settings.returning_audio_url,
            app_settings.returning_discount_audio_url,
        }:
            if not (app_settings.static_dir / url.removeprefix("/static/")).is_file():
                logger.warning(
                    "[AUDIO] File not found: %s; display will use SpeechSynthesis",
                    url,
                )

        async def recover_database() -> None:
            while True:
                await asyncio.sleep(5)
                if not app.state.db_ready:
                    try:
                        await asyncio.to_thread(database.initialize)
                        app.state.db_ready = True
                        logger.info("[DB] Database recovered")
                    except Exception:
                        logger.error("[DB] Still unavailable; retrying")

        recovery = asyncio.create_task(recover_database())
        whisper_preload: asyncio.Task[None] | None = None
        gemini_preload: asyncio.Task[None] | None = None
        voicevox_preload: asyncio.Task[None] | None = None
        if app_settings.question_enabled and app_settings.camera_enabled:
            async def preload_whisper() -> None:
                logger.info("[WHISPER] Preloading model in background")
                try:
                    await asyncio.to_thread(speech_recognizer.prepare)
                except Exception as exc:
                    logger.warning(
                        "[WHISPER] Background preload failed: %s",
                        type(exc).__name__,
                    )

            whisper_preload = asyncio.create_task(preload_whisper())
        if (
            app_settings.question_enabled
            and app_settings.camera_enabled
            and app_settings.question_unknown_policy == "gemini"
            and gemini.available
            and app_settings.gemini_preload
        ):
            async def preload_gemini() -> None:
                try:
                    await asyncio.to_thread(gemini.prepare)
                    if app_settings.gemini_warmup:
                        await gemini.warm_connection()
                except Exception as exc:
                    logger.warning(
                        "[GEMINI] Background preparation failed: %s",
                        type(exc).__name__,
                    )

            gemini_preload = asyncio.create_task(preload_gemini())
        if (
            app_settings.question_enabled
            and app_settings.camera_enabled
            and app_settings.voicevox_enabled
            and app_settings.voicevox_preload
        ):
            async def preload_voicevox() -> None:
                try:
                    await asyncio.to_thread(voicevox.prepare)
                    logger.info("[VOICEVOX] Shikoku Metan voice preloaded")
                except Exception as exc:
                    # Questions continue with browser SpeechSynthesis when the
                    # separately installed local engine is unavailable.
                    logger.warning(
                        "[VOICEVOX] Background preload failed: %s",
                        type(exc).__name__,
                    )

            voicevox_preload = asyncio.create_task(preload_voicevox())
        try:
            yield
        finally:
            recovery.cancel()
            try:
                await recovery
            except asyncio.CancelledError:
                pass
            if whisper_preload and not whisper_preload.done():
                whisper_preload.cancel()
            if whisper_preload:
                try:
                    await whisper_preload
                except asyncio.CancelledError:
                    pass
            for preload in (gemini_preload, voicevox_preload):
                if preload and not preload.done():
                    preload.cancel()
                if preload:
                    try:
                        await preload
                    except asyncio.CancelledError:
                        pass
            if camera:
                await asyncio.to_thread(camera.stop)
            await reception.close()

    app = FastAPI(
        title="鬼キャラクター顔認証接客システム",
        version="1.0.0",
        lifespan=lifespan,
        docs_url="/docs" if app_settings.debug_mode else None,
        redoc_url=None,
        openapi_url="/openapi.json" if app_settings.debug_mode else None,
    )
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["localhost", "127.0.0.1", "[::1]"])
    app.state.settings = app_settings
    app.state.database = database
    app.state.reception = reception
    app.state.websocket_manager = websocket_manager
    app.state.speech_recognizer = speech_recognizer
    app.state.question_answers = question_answers
    app.state.voicevox = voicevox

    if not app_settings.static_dir.exists():
        app_settings.static_dir.mkdir(parents=True, exist_ok=True)
    app.mount("/static", StaticFiles(directory=app_settings.static_dir), name="static")

    @app.get("/", include_in_schema=False)
    async def index() -> FileResponse:
        index_path = app_settings.static_dir / "index.html"
        if not index_path.exists():
            raise HTTPException(status_code=503, detail="Display page is not installed")
        return FileResponse(index_path)

    @app.get("/touch", include_in_schema=False)
    async def touch_panel() -> FileResponse:
        touch_path = app_settings.static_dir / "touch.html"
        if not touch_path.exists():
            raise HTTPException(status_code=503, detail="Touch panel is not installed")
        return FileResponse(touch_path)

    @app.get("/health")
    async def health() -> dict[str, Any]:
        camera = app.state.camera
        camera_status = (
            camera.status()
            if camera is not None
            else {"status": "disabled", "last_error": None}
        )
        db_ok = await asyncio.to_thread(database.ping)
        app.state.db_ready = db_ok
        videos_ok = all(
            (app_settings.static_dir / url.removeprefix("/static/")).is_file()
            for url in {
                app_settings.idle_video_url,
                app_settings.welcome_video_url,
                app_settings.returning_video_url,
                app_settings.speaking_intro_video_url,
                app_settings.speaking_loop_video_url,
            }
        )
        audio_ok = all(
            (app_settings.static_dir / url.removeprefix("/static/")).is_file()
            for url in {
                app_settings.welcome_audio_url,
                app_settings.returning_audio_url,
                app_settings.returning_discount_audio_url,
            }
        )
        return {
            "status": "ok" if db_ok and videos_ok and camera_status["status"] in {"running", "disabled"} else "degraded",
            "database": "ok" if db_ok else "error",
            "videos": "ok" if videos_ok else "missing",
            "greeting_audio": "ok" if audio_ok else "speech_synthesis_fallback",
            "camera": camera_status,
            "websocket_clients": await websocket_manager.connection_count(),
            "display_ready": websocket_manager.display_ready(),
            "reception": await reception.snapshot(),
            "questions": {
                "enabled": app_settings.question_enabled,
                "microphone_available": websocket_manager.questions_available(),
                "whisper": speech_recognizer.status(),
                "gemini": (
                    "configured" if gemini.available
                    else "disabled_or_api_key_missing"
                ),
                "voicevox": voicevox.status(),
            },
        }

    @app.get("/api/config")
    async def public_config() -> dict[str, Any]:
        audio_urls = {
            "new": app_settings.welcome_audio_url,
            "returning": app_settings.returning_audio_url,
            "returning_discount": app_settings.returning_discount_audio_url,
        }
        subtitle_cues = {
            name: f"{url.rsplit('.', 1)[0]}.cues.json"
            for name, url in audio_urls.items()
        }
        audio_asset_timestamps: list[int] = []
        for url in (*audio_urls.values(), *subtitle_cues.values()):
            asset_path = app_settings.static_dir / url.removeprefix("/static/")
            try:
                audio_asset_timestamps.append(asset_path.stat().st_mtime_ns)
            except OSError:
                continue
        return {
            "videos": {
                "idle": app_settings.idle_video_url,
                "new": app_settings.welcome_video_url,
                "returning": app_settings.returning_video_url,
                "speaking_intro": app_settings.speaking_intro_video_url,
                "speaking_loop": app_settings.speaking_loop_video_url,
            },
            "audio": audio_urls,
            "subtitle_cues": subtitle_cues,
            "audio_asset_version": (
                str(max(audio_asset_timestamps)) if audio_asset_timestamps else None
            ),
            "idle_title": "いらっしゃいませ",
            "idle_message": "カメラの前で少しお待ちください",
            "greeting_timeout_seconds": app_settings.browser_greeting_timeout_seconds,
            "debug_mode": app_settings.debug_mode,
            "questions": {
                "enabled": app_settings.question_enabled,
                "input_mode": app_settings.question_input_mode,
                "ready_timeout_seconds": app_settings.question_ready_timeout_seconds,
                "recording_max_seconds": app_settings.question_recording_max_seconds,
                "audio_bitrate": app_settings.question_audio_bitrate,
                "microphone_device_label": app_settings.microphone_device_label,
                "session_timeout_seconds": app_settings.question_session_timeout_seconds,
                "speaking_timeout_seconds": app_settings.question_speaking_timeout_seconds,
                "vad_enabled": app_settings.vad_enabled,
                "vad_start_threshold": app_settings.vad_start_threshold,
                "vad_start_duration_ms": app_settings.vad_start_duration_ms,
                "vad_end_silence_ms": app_settings.vad_end_silence_ms,
                "vad_min_speech_ms": app_settings.vad_min_speech_ms,
                "vad_resume_delay_ms": app_settings.vad_resume_delay_ms,
                "vad_preroll_ms": app_settings.vad_preroll_ms,
                "vad_calibration_ms": app_settings.vad_calibration_ms,
                "vad_noise_multiplier": app_settings.vad_noise_multiplier,
                "vad_noise_margin": app_settings.vad_noise_margin,
            },
        }

    @app.get("/api/state")
    async def state() -> dict[str, Any]:
        return await reception.snapshot()

    @app.get("/api/touch/questions")
    async def touch_questions() -> dict[str, Any]:
        enabled = bool(
            app_settings.question_enabled
            and app_settings.question_input_mode in {"touch", "both"}
        )
        return {
            "enabled": enabled,
            "questions": touch_question_catalog() if enabled else [],
        }

    @app.post("/api/touch/questions/{question_id}")
    async def submit_touch_question(question_id: str) -> dict[str, Any]:
        if not (
            app_settings.question_enabled
            and app_settings.question_input_mode in {"touch", "both"}
        ):
            raise HTTPException(status_code=404, detail="Touch questions are disabled")
        question = get_touch_question(question_id)
        if question is None:
            raise HTTPException(status_code=404, detail="Unknown touch question")
        if not websocket_manager.display_ready():
            raise HTTPException(status_code=409, detail="The main display is not ready")
        try:
            result = await reception.answer_touch_question(question)
        except QuestionConflictError as exc:
            raise HTTPException(status_code=409, detail="The receptionist is busy") from exc
        return {
            "accepted": True,
            "question_id": result["question_id"],
            "question": result["question"],
            "answer": result["answer"],
        }

    @app.websocket("/ws")
    async def websocket_endpoint(websocket: WebSocket) -> None:
        origin = websocket.headers.get("origin")
        if origin and origin not in {
            f"http://{websocket.headers.get('host')}",
            f"https://{websocket.headers.get('host')}",
        }:
            await websocket.close(code=1008)
            return
        await websocket_manager.connect(websocket)
        try:
            await websocket.send_json(await reception.snapshot())
            while True:
                raw_payload = await websocket.receive_text()
                if not raw_payload.strip():
                    logger.debug("[WEBSOCKET] Ignoring empty client message")
                    continue
                try:
                    payload = json.loads(raw_payload)
                except json.JSONDecodeError:
                    logger.warning("[WEBSOCKET] Ignoring invalid JSON from client")
                    continue
                if not isinstance(payload, dict):
                    continue
                message_type = payload.get("type")
                if message_type == "display_ready":
                    owner = await websocket_manager.claim_display(websocket)
                    await websocket.send_json({"type": "display_role", "active": owner})
                elif message_type == "question_capability":
                    available = payload.get("available") is True
                    microphone_label = payload.get("microphone_label")
                    if isinstance(microphone_label, str):
                        microphone_label = " ".join(microphone_label.split())[:120]
                    else:
                        microphone_label = ""
                    updated = await websocket_manager.set_question_capability(
                        websocket, available
                    )
                    if updated:
                        logger.info(
                            "[MICROPHONE] Browser input: %s",
                            microphone_label or "default",
                        )
                        await reception.question_capability_changed(available)
                    await websocket.send_json(
                        {"type": "question_capability", "available": available and updated}
                    )
                elif message_type == "greeting_finished":
                    greeting_id = payload.get("greeting_id")
                    if websocket_manager.is_display(websocket) and isinstance(greeting_id, str) and greeting_id:
                        await reception.finish(greeting_id)
                elif message_type == "speech_started":
                    session_id = payload.get("question_session_id")
                    question_id = payload.get("question_id")
                    vad_metrics = (
                        payload.get("vad_level"),
                        payload.get("vad_threshold"),
                        payload.get("vad_noise_floor"),
                    )
                    if all(isinstance(value, (int, float)) for value in vad_metrics):
                        logger.info(
                            "[VAD] Speech candidate: level=%.4f threshold=%.4f noise_floor=%.4f",
                            *vad_metrics,
                        )
                    if (
                        websocket_manager.is_display(websocket)
                        and isinstance(session_id, str)
                        and isinstance(question_id, str)
                    ):
                        try:
                            await reception.start_question(session_id, question_id)
                        except QuestionConflictError:
                            logger.warning("[QUESTION] Ignoring stale speech_started")
                elif message_type == "speech_discarded":
                    session_id = payload.get("question_session_id")
                    question_id = payload.get("question_id")
                    if (
                        websocket_manager.is_display(websocket)
                        and isinstance(session_id, str)
                        and isinstance(question_id, str)
                    ):
                        await reception.discard_question(session_id, question_id)
                elif message_type == "answer_finished":
                    session_id = payload.get("question_session_id")
                    question_id = payload.get("question_id")
                    if (
                        websocket_manager.is_display(websocket)
                        and isinstance(session_id, str)
                        and isinstance(question_id, str)
                    ):
                        await reception.finish_answer(session_id, question_id)
                elif message_type == "question_error":
                    session_id = payload.get("question_session_id")
                    question_id = payload.get("question_id")
                    if (
                        websocket_manager.is_display(websocket)
                        and isinstance(session_id, str)
                        and isinstance(question_id, str)
                    ):
                        await reception.fail_question(session_id, question_id)
                elif message_type == "ping":
                    await websocket.send_json({"type": "pong"})
        except WebSocketDisconnect:
            pass
        except Exception:
            logger.exception("[WEBSOCKET] Connection handler failed")
        finally:
            was_display = websocket_manager.is_display(websocket)
            await websocket_manager.disconnect(websocket)
            if was_display:
                await reception.abort_active()

    @app.post("/api/questions/{session_id}/{question_id}")
    async def submit_question(
        session_id: str,
        question_id: str,
        request: Request,
        duration_ms: int = Query(ge=0),
    ) -> dict[str, Any]:
        if not app_settings.question_enabled:
            raise HTTPException(status_code=404, detail="Not found")
        if not _valid_question_token(session_id) or not _valid_question_token(question_id):
            raise HTTPException(status_code=400, detail="Invalid question identifier")
        if duration_ms < app_settings.vad_min_speech_ms:
            await reception.discard_question(session_id, question_id)
            raise HTTPException(status_code=422, detail="Speech was too short")
        if duration_ms > int(app_settings.question_recording_max_seconds * 1000) + 1000:
            raise HTTPException(status_code=413, detail="Recording was too long")
        content_type = request.headers.get("content-type", "").split(";", 1)[0].lower()
        if not content_type.startswith("audio/"):
            raise HTTPException(status_code=415, detail="An audio content type is required")
        declared_length = request.headers.get("content-length")
        if declared_length:
            try:
                if int(declared_length) > app_settings.question_audio_max_bytes:
                    raise HTTPException(status_code=413, detail="Audio is too large")
            except ValueError as exc:
                raise HTTPException(status_code=400, detail="Invalid content length") from exc
        audio = await request.body()
        if not audio or len(audio) > app_settings.question_audio_max_bytes:
            raise HTTPException(status_code=413, detail="Audio is empty or too large")
        try:
            result = await reception.process_question_audio(session_id, question_id, audio)
        except QuestionConflictError as exc:
            raise HTTPException(status_code=409, detail="Question is no longer active") from exc
        audio_data = result.pop("audio")
        result["audio_base64"] = (
            base64.b64encode(audio_data).decode("ascii") if audio_data else None
        )
        return result

    def require_debug_mode() -> None:
        if not app_settings.debug_mode:
            raise HTTPException(status_code=404, detail="Not found")

    async def dispatch_debug_event(event: dict[str, Any]) -> dict[str, Any]:
        started = await reception.start_debug_event(event)
        if started is None:
            raise HTTPException(status_code=409, detail="接客中、または接客画面の「接客を開始」が押されていません")
        return {"accepted": True, "event": started}

    @app.post("/api/debug/new-customer")
    async def debug_new_customer() -> dict[str, Any]:
        require_debug_mode()
        return await dispatch_debug_event(
            {
                "type": "customer_detected",
                "customer_type": "new",
                "customer_id": "debug_customer_000001",
                "visit_count": 1,
                "days_since_last_visit": None,
                "discount_eligible": False,
                "message": build_greeting_message("new", None, False, app_settings.discount_valid_days),
            }
        )

    @app.post("/api/debug/returning-customer")
    async def debug_returning_customer(
        days_since_last_visit: int = Query(default=10, ge=0, le=36500),
        visit_count: int = Query(default=2, ge=2),
    ) -> dict[str, Any]:
        require_debug_mode()
        discount_eligible = days_since_last_visit <= app_settings.discount_valid_days
        return await dispatch_debug_event(
            {
                "type": "customer_detected",
                "customer_type": "returning",
                "customer_id": "debug_customer_000001",
                "visit_count": visit_count,
                "days_since_last_visit": days_since_last_visit,
                "discount_eligible": discount_eligible,
                "message": build_greeting_message(
                    "returning",
                    days_since_last_visit,
                    discount_eligible,
                    app_settings.discount_valid_days,
                ),
            }
        )

    @app.post("/api/debug/finish-greeting")
    async def debug_finish_greeting() -> dict[str, Any]:
        require_debug_mode()
        finished = await reception.finish()
        return {"finished": finished, "state": (await reception.snapshot())["state"]}

    @app.post("/api/debug/question-answer")
    async def debug_question_answer(
        text: str = Query(min_length=1, max_length=200),
        discount_eligible: bool = Query(default=False),
        allow_gemini: bool = Query(default=False),
    ) -> dict[str, Any]:
        require_debug_mode()
        result = await question_answers.answer(
            text,
            QuestionContext(discount_eligible, 10 if discount_eligible else 61),
            gemini_requests_used=(
                0 if allow_gemini else app_settings.gemini_max_requests_per_session
            ),
            force_gemini=allow_gemini,
        )
        return {
            "answer": result.text,
            "answer_source": result.source,
            "gemini_requested": result.gemini_attempted,
        }

    @app.get("/debug", include_in_schema=False)
    async def debug_page() -> FileResponse:
        require_debug_mode()
        return FileResponse(Path(__file__).parent / "debug.html")

    @app.middleware("http")
    async def same_origin_mutations(request: Request, call_next):
        origin = request.headers.get("origin")
        if request.method == "POST" and origin and origin.rstrip("/") != str(request.base_url).rstrip("/"):
            from fastapi.responses import JSONResponse
            return JSONResponse({"detail": "Origin not allowed"}, status_code=403)
        return await call_next(request)

    return app


def _valid_question_token(value: str) -> bool:
    return 1 <= len(value) <= 64 and all(
        character.isalnum() or character in {"-", "_"} for character in value
    )


app = create_app()
