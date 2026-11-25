from __future__ import annotations

import logging
import os
import threading
from collections.abc import Callable
from typing import Any

from .config import Settings
from .face_service import FaceConfirmationTracker, FaceDependencyError, FaceService


logger = logging.getLogger(__name__)


class CameraWorker:
    def __init__(
        self,
        settings: Settings,
        on_confirmed_face: Callable[[tuple[float, ...]], None],
        should_process: Callable[[], bool] | None = None,
    ) -> None:
        self.settings = settings
        self.on_confirmed_face = on_confirmed_face
        self.should_process = should_process or (lambda: True)
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._status_lock = threading.Lock()
        self._status = "stopped"
        self._last_error: str | None = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run,
            name="camera-worker",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5.0)
        self._set_status("stopped")

    def status(self) -> dict[str, str | None]:
        with self._status_lock:
            return {"status": self._status, "last_error": self._last_error}

    def _run(self) -> None:
        try:
            face_service = FaceService(self.settings)
        except (FaceDependencyError, ValueError) as exc:
            logger.error("[CAMERA] Camera processing disabled: %s", exc)
            self._set_status("error", str(exc))
            return

        tracker = FaceConfirmationTracker(self.settings)
        while not self._stop.is_set():
            capture = self._open_camera(face_service.cv2)
            if capture is None:
                self._set_status(
                    "retrying",
                    f"camera index {self.settings.camera_index} could not be opened",
                )
                self._stop.wait(self.settings.camera_retry_seconds)
                continue

            try:
                self._capture_loop(capture, face_service, tracker)
            except Exception:
                logger.exception("[CAMERA] Capture failed; reopening camera")
            finally:
                capture.release()

            if not self._stop.is_set():
                self._set_status("retrying", "capture ended; reopening camera")
                self._stop.wait(self.settings.camera_retry_seconds)

    def _open_camera(self, cv2: Any) -> Any | None:
        index = self.settings.camera_index
        capture = None
        try:
            use_dshow = self.settings.camera_backend == "dshow" or (
                self.settings.camera_backend == "auto" and os.name == "nt"
            )
            if use_dshow and hasattr(cv2, "CAP_DSHOW"):
                capture = cv2.VideoCapture(index, cv2.CAP_DSHOW)
                if not capture.isOpened():
                    capture.release()
                    capture = cv2.VideoCapture(index)
            else:
                if self.settings.camera_backend == "msmf":
                    capture = cv2.VideoCapture(index, cv2.CAP_MSMF)
                else:
                    capture = cv2.VideoCapture(index)

            if not capture.isOpened():
                logger.error("[CAMERA] Could not open camera: index=%s", index)
                capture.release()
                return None

            capture.set(cv2.CAP_PROP_FRAME_WIDTH, self.settings.camera_width)
            capture.set(cv2.CAP_PROP_FRAME_HEIGHT, self.settings.camera_height)
            if hasattr(cv2, "CAP_PROP_FPS"):
                capture.set(cv2.CAP_PROP_FPS, self.settings.camera_fps)
            if hasattr(cv2, "CAP_PROP_BUFFERSIZE"):
                capture.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            self._set_status("running")
            logger.info(
                "[CAMERA] Camera started: index=%s target_fps=%s",
                index,
                self.settings.camera_fps,
            )
            return capture
        except Exception as exc:
            if capture is not None:
                capture.release()
            logger.exception("[CAMERA] Failed while opening camera: index=%s", index)
            self._set_status("error", str(exc))
            return None

    def _capture_loop(
        self,
        capture: Any,
        face_service: FaceService,
        tracker: FaceConfirmationTracker,
    ) -> None:
        frame_number = 0
        consecutive_read_errors = 0
        while not self._stop.is_set():
            ok, frame = capture.read()
            if not ok or frame is None:
                consecutive_read_errors += 1
                if consecutive_read_errors == 1:
                    logger.warning("[CAMERA] Failed to read a frame")
                if consecutive_read_errors >= 30:
                    logger.error("[CAMERA] Too many frame read errors; reopening camera")
                    return
                self._stop.wait(0.05)
                continue

            consecutive_read_errors = 0
            frame_number += 1
            if not self.should_process():
                continue
            if frame_number % self.settings.face_frame_skip:
                continue

            for encoding in face_service.extract_encodings(frame):
                confirmed = tracker.observe(encoding)
                if confirmed is None:
                    continue
                logger.info(
                    "[FACE] Face confirmed: observations=%s",
                    self.settings.face_confirmation_count,
                )
                try:
                    self.on_confirmed_face(confirmed)
                except Exception:
                    logger.exception("[CAMERA] Confirmed-face callback failed")

    def _set_status(self, status: str, error: str | None = None) -> None:
        with self._status_lock:
            self._status = status
            self._last_error = error
