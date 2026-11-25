from dataclasses import replace
from unittest.mock import MagicMock, patch
import pytest
from app.camera import CameraWorker
from app.config import Settings
from app.face_service import FaceConfirmationTracker, FaceDependencyError, FaceService

FACE = (0.1,) * 128

def test_confirmation_and_expiry():
    tracker = FaceConfirmationTracker(Settings())
    assert tracker.observe(FACE, 10) is None
    assert tracker.observe(FACE, 10.2) == FACE
    assert tracker.observe(FACE, 10.3) is None
    assert tracker.observe(FACE, 10.4) is None
    assert tracker.observe(FACE, 20) is None
    assert tracker.observe((1.0,) * 128, 20.2) is None
    assert tracker.observe(FACE, 20.4) == FACE

def test_camera_open_failure():
    worker = CameraWorker(Settings(), lambda encoding: None)
    cv = MagicMock()
    cv.VideoCapture.return_value.isOpened.return_value = False
    assert worker._open_camera(cv) is None
    cv.VideoCapture.return_value.release.assert_called()

def test_camera_configures_low_latency_capture():
    worker = CameraWorker(Settings(camera_fps=15), lambda encoding: None)
    cv = MagicMock()
    cv.VideoCapture.return_value.isOpened.return_value = True
    capture = worker._open_camera(cv)
    assert capture is cv.VideoCapture.return_value
    capture.set.assert_any_call(cv.CAP_PROP_FPS, 15)
    capture.set.assert_any_call(cv.CAP_PROP_BUFFERSIZE, 1)

def test_missing_dependency():
    worker = CameraWorker(Settings(), lambda encoding: None)
    with patch("app.camera.FaceService", side_effect=FaceDependencyError("missing")):
        worker._run()
    assert worker.status()["status"] == "error"

def test_frame_skipping():
    worker = CameraWorker(Settings(face_frame_skip=5), lambda encoding: None)
    capture, face = MagicMock(), MagicMock()
    count = 0
    def read():
        nonlocal count
        count += 1
        if count == 10:
            worker._stop.set()
        return True, object()
    capture.read.side_effect = read
    face.extract_encodings.return_value = []
    worker._capture_loop(capture, face, FaceConfirmationTracker(Settings()))
    assert face.extract_encodings.call_count == 2

def test_face_processing_pauses_while_reception_is_busy():
    worker = CameraWorker(
        Settings(face_frame_skip=1),
        lambda encoding: None,
        should_process=lambda: False,
    )
    capture, face = MagicMock(), MagicMock()
    count = 0
    def read():
        nonlocal count
        count += 1
        if count == 5:
            worker._stop.set()
        return True, object()
    capture.read.side_effect = read
    worker._capture_loop(capture, face, FaceConfirmationTracker(Settings()))
    face.extract_encodings.assert_not_called()

def test_no_face_or_encoding_failure():
    service = FaceService.__new__(FaceService)
    service.settings = Settings()
    service.cv2 = MagicMock()
    service.face_recognition = MagicMock()
    service.face_recognition.face_locations.return_value = []
    assert service.extract_encodings(object()) == []
    service.face_recognition.face_locations.side_effect = ValueError("bad image")
    assert service.extract_encodings(object()) == []

@pytest.mark.parametrize("field,value", [
    ("face_image_scale", 0), ("face_frame_skip", 0), ("person_cooldown_seconds", -1),
    ("face_match_threshold", 2), ("camera_backend", "wrong"),
    ("camera_fps", 0),
])
def test_invalid_config(field, value):
    with pytest.raises(ValueError):
        replace(Settings(), **{field: value})
