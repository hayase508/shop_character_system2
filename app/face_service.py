from __future__ import annotations

import logging
from collections import deque
from dataclasses import dataclass
from time import monotonic
from typing import Any, Sequence

from .config import Settings


logger = logging.getLogger(__name__)


class FaceDependencyError(RuntimeError):
    pass


class FaceService:
    def __init__(self, settings: Settings) -> None:
        if not 0 < settings.face_image_scale <= 1:
            raise ValueError("FACE_IMAGE_SCALE must be greater than 0 and at most 1")
        if settings.face_detection_model not in {"hog", "cnn"}:
            raise ValueError("FACE_DETECTION_MODEL must be 'hog' or 'cnn'")
        try:
            import cv2
            import face_recognition
        except (ImportError, OSError, SystemExit) as exc:
            raise FaceDependencyError(
                "OpenCVまたはface_recognitionを読み込めません。requirements.txtを確認してください。"
            ) from exc

        self.settings = settings
        self.cv2 = cv2
        self.face_recognition = face_recognition

    def extract_encodings(self, frame: Any) -> list[tuple[float, ...]]:
        try:
            resized = self.cv2.resize(
                frame,
                (0, 0),
                fx=self.settings.face_image_scale,
                fy=self.settings.face_image_scale,
            )
            rgb_frame = self.cv2.cvtColor(resized, self.cv2.COLOR_BGR2RGB)
            locations = self.face_recognition.face_locations(
                rgb_frame,
                model=self.settings.face_detection_model,
            )
            if not locations:
                return []
            # Largest face only: two people in one image cannot count as
            # the required two-frame confirmation of a single customer.
            locations = [max(locations, key=lambda box: (box[2] - box[0]) * (box[1] - box[3]))]
            logger.info("[FACE] Face detected: count=%s", len(locations))
            encodings = self.face_recognition.face_encodings(rgb_frame, locations)
            if not encodings:
                logger.warning("[FACE] Face found but encoding could not be generated")
            return [tuple(float(value) for value in encoding) for encoding in encodings]
        except Exception:
            logger.exception("[FACE] Failed to detect or encode face")
            return []


@dataclass(slots=True)
class _Observation:
    encoding: tuple[float, ...]
    seen_at: float


class FaceConfirmationTracker:
    """直近の観測から、同じ顔が複数回確認されたときだけ通知する。"""

    def __init__(self, settings: Settings) -> None:
        self.required = settings.face_confirmation_count
        self.window_seconds = settings.face_confirmation_window_seconds
        self.match_threshold = settings.face_match_threshold
        self.emit_cooldown = settings.camera_event_cooldown_seconds
        self._observations: deque[_Observation] = deque(maxlen=max(3, self.required * 3))
        self._last_emitted_at = float("-inf")

    def observe(
        self,
        encoding: Sequence[float],
        now: float | None = None,
    ) -> tuple[float, ...] | None:
        observed_at = now if now is not None else monotonic()
        normalized = tuple(float(value) for value in encoding)
        self._discard_expired(observed_at)
        self._observations.append(_Observation(normalized, observed_at))

        matching = [
            observation.encoding
            for observation in self._observations
            if self._distance(observation.encoding, normalized) <= self.match_threshold
        ]
        if len(matching) < self.required:
            return None
        if observed_at - self._last_emitted_at < self.emit_cooldown:
            return None

        self._last_emitted_at = observed_at
        self._observations.clear()
        dimensions = len(normalized)
        return tuple(
            sum(candidate[index] for candidate in matching) / len(matching)
            for index in range(dimensions)
        )

    def _discard_expired(self, now: float) -> None:
        while self._observations and now - self._observations[0].seen_at > self.window_seconds:
            self._observations.popleft()

    @staticmethod
    def _distance(left: Sequence[float], right: Sequence[float]) -> float:
        if len(left) != len(right):
            return float("inf")
        return sum((a - b) ** 2 for a, b in zip(left, right, strict=True)) ** 0.5
