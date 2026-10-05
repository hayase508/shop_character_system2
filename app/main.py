from __future__ import annotations

import asyncio
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
from .reception import ReceptionController
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
    reception = ReceptionController(customer_service, websocket_manager, app_settings)

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
        for url in {app_settings.idle_video_url, app_settings.welcome_video_url,
                    app_settings.returning_video_url}:
            if not (app_settings.static_dir / url.removeprefix("/static/")).is_file():
                logger.error("[VIDEO] File not found: %s; display will use fallback", url)

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
        try:
            yield
        finally:
            recovery.cancel()
            try:
                await recovery
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

    if not app_settings.static_dir.exists():
        app_settings.static_dir.mkdir(parents=True, exist_ok=True)
    app.mount("/static", StaticFiles(directory=app_settings.static_dir), name="static")

    @app.get("/", include_in_schema=False)
    async def index() -> FileResponse:
        index_path = app_settings.static_dir / "index.html"
        if not index_path.exists():
            raise HTTPException(status_code=503, detail="Display page is not installed")
        return FileResponse(index_path)

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
        videos_ok = all((app_settings.static_dir / url.removeprefix("/static/")).is_file()
                        for url in {app_settings.idle_video_url, app_settings.welcome_video_url,
                                    app_settings.returning_video_url})
        return {
            "status": "ok" if db_ok and videos_ok and camera_status["status"] in {"running", "disabled"} else "degraded",
            "database": "ok" if db_ok else "error",
            "videos": "ok" if videos_ok else "missing",
            "camera": camera_status,
            "websocket_clients": await websocket_manager.connection_count(),
            "display_ready": websocket_manager.display_ready(),
            "reception": await reception.snapshot(),
        }

    @app.get("/api/config")
    async def public_config() -> dict[str, Any]:
        return {
            "videos": {
                "idle": app_settings.idle_video_url,
                "new": app_settings.welcome_video_url,
                "returning": app_settings.returning_video_url,
            },
            "idle_title": "いらっしゃいませ",
            "idle_message": "カメラの前で少しお待ちください",
            "greeting_timeout_seconds": app_settings.browser_greeting_timeout_seconds,
            "debug_mode": app_settings.debug_mode,
        }

    @app.get("/api/state")
    async def state() -> dict[str, Any]:
        return await reception.snapshot()

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
                elif message_type == "greeting_finished":
                    greeting_id = payload.get("greeting_id")
                    if websocket_manager.is_display(websocket) and isinstance(greeting_id, str) and greeting_id:
                        await reception.finish(greeting_id)
                elif message_type == "ping":
                    await websocket.send_json({"type": "pong"})
        except WebSocketDisconnect:
            pass
        except Exception:
            logger.exception("[WEBSOCKET] Connection handler failed")
        finally:
            was_display = websocket_manager.is_display(websocket)
            active_id = (await reception.snapshot())["greeting_id"] if was_display else None
            await websocket_manager.disconnect(websocket)
            if active_id:
                await reception.finish(active_id)

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


app = create_app()
