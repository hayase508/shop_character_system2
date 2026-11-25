from __future__ import annotations

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Sequence

from .config import Settings
from .customer_service import CustomerService, build_greeting_message
from .question_service import (
    LOCAL_VOICE_LINES,
    QuestionAnswerService,
    QuestionContext,
    TouchQuestion,
    is_likely_spoken_question,
    is_meaningful_question,
)
from .speech_service import SpeechRecognizer
from .voicevox_service import VoicevoxService
from .websocket_manager import WebSocketManager


logger = logging.getLogger(__name__)


class QuestionConflictError(RuntimeError):
    pass


@dataclass(slots=True)
class QuestionSession:
    session_id: str
    context: QuestionContext
    deadline: float
    cooldown_customer_id: str | None = None
    gemini_requests_used: int = 0
    current_question_id: str | None = None
    touch_only: bool = False


class ReceptionController:
    IDLE = "IDLE"
    GREETING = "GREETING"
    READY = "READY"
    LISTENING = "LISTENING"
    TRANSCRIBING = "TRANSCRIBING"
    THINKING = "THINKING"
    SPEAKING = "SPEAKING"

    QUESTION_STATES = {READY, LISTENING, TRANSCRIBING, THINKING, SPEAKING}

    def __init__(
        self,
        customer_service: CustomerService,
        websocket_manager: WebSocketManager,
        settings: Settings,
        speech_recognizer: SpeechRecognizer | None = None,
        question_answers: QuestionAnswerService | None = None,
        voicevox: VoicevoxService | None = None,
    ) -> None:
        self.customer_service = customer_service
        self.websocket_manager = websocket_manager
        self.settings = settings
        self.speech_recognizer = speech_recognizer or SpeechRecognizer(settings)
        self.question_answers = question_answers or QuestionAnswerService(settings)
        self.voicevox = voicevox or VoicevoxService(settings)
        self._state = self.IDLE
        self._lock = asyncio.Lock()
        self._last_global_greeting_at: datetime | None = None
        self._person_greeting_at: dict[str, datetime] = {}
        self._current_greeting_id: str | None = None
        self._current_event: dict[str, Any] | None = None
        self._greeting_timeout_task: asyncio.Task[None] | None = None
        self._question_session: QuestionSession | None = None
        self._ready_timeout_task: asyncio.Task[None] | None = None
        self._session_timeout_task: asyncio.Task[None] | None = None
        self._speaking_timeout_task: asyncio.Task[None] | None = None
        self._last_assistance_at = float("-inf")

    async def process_face_encoding(self, encoding: Sequence[float]) -> dict[str, Any] | None:
        now = datetime.now(timezone.utc)
        async with self._lock:
            if not self.websocket_manager.display_ready():
                return None

            try:
                match = await asyncio.to_thread(self.customer_service.match_customer, encoding)
                if match is not None:
                    result = await asyncio.to_thread(
                        self.customer_service.record_returning_visit,
                        match,
                        now,
                    )
                    # Existing customers keep a current last_seen_at even while a
                    # greeting or question session blocks a second interaction.
                    if not self._global_gate_is_open(now) or not self._person_gate_is_open(
                        match.customer.customer_id, now
                    ):
                        return None
                    customer_type = "returning"
                    logger.info(
                        "[CUSTOMER] Returning customer: %s", result.customer.customer_id
                    )
                else:
                    if not self._global_gate_is_open(now):
                        return None
                    result = await asyncio.to_thread(
                        self.customer_service.register_new_customer,
                        encoding,
                        now,
                    )
                    customer_type = "new"
                    logger.info("[CUSTOMER] New customer: %s", result.customer.customer_id)
            except Exception:
                logger.exception("[CUSTOMER] Face matching or visit update failed")
                return None

            event = self._make_event(
                customer_type=customer_type,
                customer_id=result.customer.customer_id,
                visit_count=result.customer.visit_count,
                days_since_last_visit=result.days_since_last_visit,
                discount_eligible=result.discount_eligible,
            )
            self._activate_greeting_locked(event, now)

        await self._announce(event)
        return event

    async def start_debug_event(self, event: dict[str, Any]) -> dict[str, Any] | None:
        now = datetime.now(timezone.utc)
        async with self._lock:
            if self._state != self.IDLE or not self.websocket_manager.display_ready():
                return None
            debug_event = dict(event)
            self._activate_greeting_locked(debug_event, now)
        await self._announce(debug_event)
        return debug_event

    async def finish(self, greeting_id: str | None = None, allow_questions: bool = True) -> bool:
        async with self._lock:
            if self._state != self.GREETING:
                return False
            if greeting_id and greeting_id != self._current_greeting_id:
                return False

            event = dict(self._current_event or {})
            finished_at = datetime.now(timezone.utc)
            self._last_global_greeting_at = finished_at
            customer_id = event.get("customer_id")
            if customer_id:
                self._person_greeting_at[str(customer_id)] = finished_at
            self._current_greeting_id = None
            self._current_event = None
            self._cancel_task(self._greeting_timeout_task)
            self._greeting_timeout_task = None

            microphone_questions = bool(
                self.settings.question_input_mode in {"microphone", "both"}
                and self.settings.vad_enabled
                and self.websocket_manager.questions_available()
            )
            touch_questions = self.settings.question_input_mode in {"touch", "both"}
            can_answer_questions = bool(
                allow_questions
                and self.settings.question_enabled
                and (microphone_questions or touch_questions)
            )
            if can_answer_questions:
                session = QuestionSession(
                    session_id=uuid.uuid4().hex,
                    context=QuestionContext(
                        discount_eligible=bool(event.get("discount_eligible")),
                        days_since_last_visit=event.get("days_since_last_visit"),
                    ),
                    deadline=time.monotonic() + self.settings.question_session_timeout_seconds,
                    # Ephemeral cooldown-only value. It is never exposed to the
                    # question services, Gemini, logs or persistent storage.
                    cooldown_customer_id=str(customer_id) if customer_id else None,
                )
                self._question_session = session
                self._state = self.READY
                self._schedule_session_timeout_locked(session.session_id)
                self._schedule_ready_timeout_locked(session.session_id)
                payload = self._ready_payload(session)
            else:
                self._state = self.IDLE
                payload = {"type": "state_changed", "state": self.IDLE}

        logger.info("[GREETING] Finished")
        logger.info("[STATE] %s", payload["state"])
        await self.websocket_manager.broadcast(payload)
        return True

    async def start_question(self, session_id: str, question_id: str) -> bool:
        if not session_id or not question_id:
            return False
        async with self._lock:
            session = self._require_question_locked(session_id, question_id=None)
            if self._state != self.READY:
                return False
            session.current_question_id = question_id
            self._state = self.LISTENING
            self._cancel_task(self._ready_timeout_task)
            self._ready_timeout_task = None
            payload = self._state_payload(self.LISTENING, session)
        logger.info("[QUESTION] Speech started: question_id=%s", question_id)
        logger.info("[STATE] LISTENING")
        await self.websocket_manager.broadcast(payload)
        return True

    async def answer_touch_question(self, question: TouchQuestion) -> dict[str, Any]:
        """Start a prerecorded FAQ answer selected on the separate touch panel."""
        question_id = uuid.uuid4().hex
        async with self._lock:
            session = self._question_session
            if self._state == self.IDLE:
                session = QuestionSession(
                    session_id=uuid.uuid4().hex,
                    context=QuestionContext(False, None),
                    deadline=time.monotonic() + self.settings.question_session_timeout_seconds,
                    touch_only=True,
                )
                self._question_session = session
            elif session is None or self._state != self.READY:
                raise QuestionConflictError("touch question is not ready")
            session.current_question_id = question_id
            self._state = self.THINKING
            self._cancel_task(self._ready_timeout_task)
            self._ready_timeout_task = None
            started_payload = self._state_payload(self.THINKING, session)
            started_payload.update(
                {
                    "type": "touch_question_started",
                    "question": question.label,
                    "answer_source": "touch_panel",
                    "answer_language": question.language,
                }
            )
        logger.info("[TOUCH] Question selected: %s", question.question_id)
        logger.info("[STATE] THINKING")
        await self.websocket_manager.broadcast(started_payload)

        # Language selection changes subtitles/UI only.  Every locale keeps
        # using the established Japanese Shikoku Metan recording.
        audio_url = self._prerecorded_answer_url(question.audio_key)
        async with self._lock:
            session = self._require_question_locked(session.session_id, question_id)
            if self._state != self.THINKING:
                raise QuestionConflictError("touch answer is stale")
            self._state = self.SPEAKING
            self._schedule_speaking_timeout_locked(session.session_id, question_id)
            answer_payload = self._state_payload(self.SPEAKING, session)
            answer_payload.update(
                {
                    "type": "touch_answer_started",
                    "question": question.label,
                    "answer": question.answer,
                    "spoken_answer": LOCAL_VOICE_LINES[question.audio_key],
                    "answer_source": "touch_panel",
                    "answer_language": question.language,
                    "audio_language": "ja",
                    "audio_url": audio_url,
                    "audio_mime_type": "audio/wav" if audio_url else None,
                    "display_image_url": question.display_image_url,
                    "display_image_layout": question.display_image_layout,
                    "display_image_alt": question.display_image_alt,
                }
            )
        logger.info("[TOUCH] Answer started: %s", question.question_id)
        logger.info("[STATE] SPEAKING")
        await self.websocket_manager.broadcast(answer_payload)
        return answer_payload

    async def start_assistance_prompt(self) -> bool:
        """Play one local prompt after browser-side speech-like sound detection."""
        now = time.monotonic()
        question_id = uuid.uuid4().hex
        async with self._lock:
            if (
                not self.settings.assistance_voice_enabled
                or self._state not in {self.IDLE, self.READY}
                or now - self._last_assistance_at
                < self.settings.assistance_voice_cooldown_seconds
            ):
                return False
            if self._state == self.READY:
                if (
                    self.settings.question_input_mode != "touch"
                    or self._question_session is None
                ):
                    return False
                session = self._question_session
                session.current_question_id = question_id
                self._cancel_task(self._ready_timeout_task)
                self._ready_timeout_task = None
            else:
                session = QuestionSession(
                    session_id=uuid.uuid4().hex,
                    context=QuestionContext(False, None),
                    deadline=now + self.settings.question_session_timeout_seconds,
                    current_question_id=question_id,
                    touch_only=True,
                )
                self._question_session = session
            self._state = self.SPEAKING
            self._last_assistance_at = now
            self._schedule_speaking_timeout_locked(session.session_id, question_id)
            payload = self._state_payload(self.SPEAKING, session)
            payload.update(
                {
                    "type": "assistance_prompt_started",
                    "question": "",
                    "answer": LOCAL_VOICE_LINES["assistance-prompt"],
                    "answer_source": "assistance_prompt",
                    "audio_url": self._prerecorded_answer_url("assistance-prompt"),
                    "audio_mime_type": "audio/wav",
                }
            )
        logger.info("[ASSISTANCE] Human voice detected; prompt started")
        logger.info("[STATE] SPEAKING")
        await self.websocket_manager.broadcast(payload)
        return True

    async def discard_question(self, session_id: str, question_id: str) -> bool:
        async with self._lock:
            try:
                session = self._require_question_locked(session_id, question_id)
            except QuestionConflictError:
                return False
            if self._state != self.LISTENING:
                return False
            session.current_question_id = None
            self._state = self.READY
            self._schedule_ready_timeout_locked(session.session_id)
            payload = self._ready_payload(session)
        logger.info("[QUESTION] Short sound discarded")
        logger.info("[STATE] READY")
        await self.websocket_manager.broadcast(payload)
        return True

    async def process_question_audio(
        self,
        session_id: str,
        question_id: str,
        audio: bytes,
    ) -> dict[str, Any]:
        pipeline_started_at = time.perf_counter()
        async with self._lock:
            session = self._require_question_locked(session_id, question_id)
            if self._state != self.LISTENING:
                raise QuestionConflictError("question is not listening")
            self._state = self.TRANSCRIBING
            transcribing_payload = self._state_payload(self.TRANSCRIBING, session)
        logger.info("[QUESTION] Transcribing: question_id=%s bytes=%s", question_id, len(audio))
        logger.info("[STATE] TRANSCRIBING")
        await self.websocket_manager.broadcast(transcribing_payload)

        whisper_started_at = time.perf_counter()
        try:
            question = await asyncio.wait_for(
                asyncio.to_thread(self.speech_recognizer.transcribe, audio),
                timeout=self.settings.whisper_timeout_seconds,
            )
        except Exception as exc:
            logger.warning("[WHISPER] Transcription failed: %s", type(exc).__name__)
            question = ""
        whisper_seconds = time.perf_counter() - whisper_started_at

        question = question[: self.settings.gemini_max_question_chars].strip()
        if not is_meaningful_question(question) or not is_likely_spoken_question(question):
            async with self._lock:
                session = self._require_question_locked(session_id, question_id)
                if self._state != self.TRANSCRIBING:
                    raise QuestionConflictError("transcription is stale")
                session.current_question_id = None
                self._state = self.READY
                self._schedule_ready_timeout_locked(session.session_id)
                ready_payload = self._ready_payload(session)
            logger.info(
                "[QUESTION] No reliable speech recognized; discarded: question_id=%s",
                question_id,
            )
            logger.info("[STATE] READY")
            await self.websocket_manager.broadcast(ready_payload)
            return {
                "session_id": session_id,
                "question_id": question_id,
                "question": "",
                "answer": "",
                "answer_source": "no_speech",
                "audio": None,
                "audio_url": None,
                "audio_mime_type": None,
                "discarded": True,
            }

        async with self._lock:
            session = self._require_question_locked(session_id, question_id)
            if self._state != self.TRANSCRIBING:
                raise QuestionConflictError("transcription is stale")
            self._state = self.THINKING
            thinking_payload = self._state_payload(self.THINKING, session)
            if question:
                thinking_payload.update({"type": "question_recognized", "question": question})
            requests_used = session.gemini_requests_used
            context = session.context
        logger.info("[QUESTION] Transcription completed: question_id=%s", question_id)
        logger.info("[STATE] THINKING")
        await self.websocket_manager.broadcast(thinking_payload)

        answer_started_at = time.perf_counter()
        result = await self.question_answers.answer(question, context, requests_used)
        display_question = question
        answer_seconds = time.perf_counter() - answer_started_at

        async with self._lock:
            session = self._require_question_locked(session_id, question_id)
            if self._state != self.THINKING:
                raise QuestionConflictError("answer is stale")
            preview_payload = self._state_payload(self.THINKING, session)
            preview_payload.update(
                {
                    "type": "answer_text_ready",
                    "question": display_question,
                    "answer": result.text,
                    "answer_source": result.source,
                }
            )
        await self.websocket_manager.broadcast(preview_payload)

        audio_url = self._prerecorded_answer_url(result.audio_key)
        audio_data: bytes | None = None
        tts_seconds = 0.0
        if audio_url:
            logger.info("[AUDIO] Using prerecorded answer: %s", result.audio_key)
        elif self.settings.voicevox_enabled:
            tts_started_at = time.perf_counter()
            try:
                synthesized = await asyncio.wait_for(
                    asyncio.to_thread(self.voicevox.synthesize, result.text),
                    timeout=self.settings.voicevox_timeout_seconds,
                )
                if self.voicevox.is_wav(synthesized):
                    audio_data = synthesized
                else:
                    logger.warning("[VOICEVOX] Response was not WAV")
            except Exception as exc:
                logger.warning("[VOICEVOX] Synthesis failed: %s", type(exc).__name__)
            finally:
                tts_seconds = time.perf_counter() - tts_started_at

        async with self._lock:
            session = self._require_question_locked(session_id, question_id)
            if self._state != self.THINKING:
                raise QuestionConflictError("answer is stale")
            if result.gemini_attempted:
                session.gemini_requests_used += 1
            self._state = self.SPEAKING
            self._schedule_speaking_timeout_locked(session.session_id, question_id)
            answer_payload = self._state_payload(self.SPEAKING, session)
            answer_payload.update(
                {
                    "type": "answer_started",
                    "question": display_question,
                    "answer": result.text,
                    "answer_source": result.source,
                }
            )
        logger.info("[QUESTION] Answer ready: question_id=%s source=%s", question_id, result.source)
        logger.info(
            "[PERFORMANCE] Question pipeline: whisper=%.3fs answer=%.3fs "
            "voicevox=%.3fs total=%.3fs source=%s",
            whisper_seconds,
            answer_seconds,
            tts_seconds,
            time.perf_counter() - pipeline_started_at,
            result.source,
        )
        logger.info("[STATE] SPEAKING")
        await self.websocket_manager.broadcast(answer_payload)
        return {
            "session_id": session_id,
            "question_id": question_id,
            "question": display_question,
            "answer": result.text,
            "answer_source": result.source,
            "audio": audio_data,
            "audio_url": audio_url,
            "audio_mime_type": "audio/wav" if audio_data else None,
        }

    def _prerecorded_answer_url(self, audio_key: str | None) -> str | None:
        if not audio_key or not all(
            character.isalnum() or character in {"-", "_"} for character in audio_key
        ):
            return None
        relative_url = f"/static/audio/faq/{audio_key}.wav"
        asset_path = self.settings.static_dir / relative_url.removeprefix("/static/")
        try:
            version = asset_path.stat().st_mtime_ns
        except OSError:
            logger.warning("[AUDIO] Prerecorded answer missing: %s", asset_path)
            return None
        return f"{relative_url}?v={version}"

    async def finish_answer(self, session_id: str, question_id: str) -> bool:
        async with self._lock:
            try:
                session = self._require_question_locked(session_id, question_id)
            except QuestionConflictError:
                return False
            if self._state != self.SPEAKING:
                return False
            self._cancel_task(self._speaking_timeout_task)
            self._speaking_timeout_task = None

        await asyncio.sleep(self.settings.vad_resume_delay_ms / 1000)

        async with self._lock:
            try:
                session = self._require_question_locked(session_id, question_id)
            except QuestionConflictError:
                return False
            if self._state != self.SPEAKING:
                return False
            session.current_question_id = None
            # Every completed voice response opens a fresh touch-panel window.
            # Reset the session deadline so the full READY timeout is available
            # even when the greeting or answer itself took several seconds.
            session.deadline = time.monotonic() + max(
                self.settings.question_session_timeout_seconds,
                self.settings.question_ready_timeout_seconds,
            )
            self._state = self.READY
            self._schedule_session_timeout_locked(session.session_id)
            self._schedule_ready_timeout_locked(session.session_id)
            payload = self._ready_payload(session)
        logger.info("[QUESTION] Answer finished: question_id=%s", question_id)
        logger.info("[STATE] %s", payload["state"])
        await self.websocket_manager.broadcast(payload)
        return True

    async def fail_question(self, session_id: str, question_id: str) -> bool:
        async with self._lock:
            try:
                session = self._require_question_locked(session_id, question_id)
            except QuestionConflictError:
                return False
            if self._state not in {
                self.LISTENING, self.TRANSCRIBING, self.THINKING, self.SPEAKING
            }:
                return False
            self._cancel_task(self._speaking_timeout_task)
            self._speaking_timeout_task = None
            session.current_question_id = None
            if session.touch_only:
                self._clear_question_session_locked()
                self._state = self.IDLE
                payload = {"type": "state_changed", "state": self.IDLE}
            else:
                self._state = self.READY
                self._schedule_ready_timeout_locked(session.session_id)
                payload = self._ready_payload(session)
        logger.warning("[QUESTION] Browser reported a question error")
        logger.info("[STATE] %s", payload["state"])
        await self.websocket_manager.broadcast(payload)
        return True

    async def question_capability_changed(self, available: bool) -> None:
        if available or self.settings.question_input_mode in {"touch", "both"}:
            return
        async with self._lock:
            active = self._state in self.QUESTION_STATES
            session_id = self._question_session.session_id if self._question_session else None
        if active and session_id:
            await self.end_question_session(session_id, "microphone_unavailable")

    async def end_question_session(self, session_id: str, reason: str) -> bool:
        async with self._lock:
            if not self._question_session or self._question_session.session_id != session_id:
                return False
            finished_at = datetime.now(timezone.utc)
            self._last_global_greeting_at = finished_at
            if self._question_session.cooldown_customer_id:
                self._person_greeting_at[
                    self._question_session.cooldown_customer_id
                ] = finished_at
            self._clear_question_session_locked()
            self._state = self.IDLE
        logger.info("[QUESTION] Session ended: reason=%s", reason)
        logger.info("[STATE] IDLE")
        await self.websocket_manager.broadcast(
            {"type": "state_changed", "state": self.IDLE, "reason": reason}
        )
        return True

    async def abort_active(self, reason: str = "display_disconnected") -> bool:
        async with self._lock:
            state = self._state
            greeting_id = self._current_greeting_id
            session_id = self._question_session.session_id if self._question_session else None
        if state == self.GREETING:
            return await self.finish(greeting_id, allow_questions=False)
        if state in self.QUESTION_STATES and session_id:
            return await self.end_question_session(session_id, reason)
        return False

    async def snapshot(self) -> dict[str, Any]:
        async with self._lock:
            session = self._question_session
            return {
                "type": "state_changed",
                "state": self._state,
                "greeting_id": self._current_greeting_id,
                "question_session_id": session.session_id if session else None,
                "question_id": session.current_question_id if session else None,
            }

    async def current_event(self) -> dict[str, Any] | None:
        async with self._lock:
            return dict(self._current_event) if self._current_event else None

    def camera_processing_allowed(self) -> bool:
        """Cheap cross-thread hint; the locked state checks remain authoritative."""
        return self._state == self.IDLE and self.websocket_manager.display_ready()

    async def close(self) -> None:
        for task in (
            self._greeting_timeout_task,
            self._ready_timeout_task,
            self._session_timeout_task,
            self._speaking_timeout_task,
        ):
            self._cancel_task(task)
        await self.question_answers.gemini.close()

    def _global_gate_is_open(self, now: datetime) -> bool:
        if self._state != self.IDLE:
            return False
        if self._last_global_greeting_at is None:
            return True
        elapsed = (now - self._last_global_greeting_at).total_seconds()
        return elapsed >= self.settings.global_cooldown_seconds

    def _person_gate_is_open(self, customer_id: str, now: datetime) -> bool:
        previous = self._person_greeting_at.get(customer_id)
        if previous is None:
            return True
        elapsed = (now - previous).total_seconds()
        return elapsed >= self.settings.person_cooldown_seconds

    def _activate_greeting_locked(self, event: dict[str, Any], now: datetime) -> None:
        greeting_id = uuid.uuid4().hex
        event["greeting_id"] = greeting_id
        self._state = self.GREETING
        self._current_greeting_id = greeting_id
        self._current_event = dict(event)
        self._last_global_greeting_at = now
        customer_id = event.get("customer_id")
        if customer_id:
            self._person_greeting_at[str(customer_id)] = now

        self._greeting_timeout_task = asyncio.create_task(
            self._finish_after_timeout(greeting_id)
        )
        logger.info("[VISIT] Visit count: %s", event.get("visit_count"))
        logger.info("[VISIT] Days since last visit: %s", event.get("days_since_last_visit"))
        logger.info(
            "[DISCOUNT] Eligible: %s",
            str(bool(event.get("discount_eligible"))).lower(),
        )
        logger.info("[GREETING] Started")
        logger.info("[STATE] GREETING")

    async def _announce(self, event: dict[str, Any]) -> None:
        delivered = await self.websocket_manager.broadcast(event)
        if delivered == 0:
            logger.warning("[GREETING] No display is connected; returning to IDLE")
            await self.finish(str(event["greeting_id"]), allow_questions=False)

    async def _finish_after_timeout(self, greeting_id: str) -> None:
        try:
            await asyncio.sleep(self.settings.greeting_timeout_seconds)
            logger.warning("[GREETING] Timed out; forcing IDLE")
            await self.finish(greeting_id, allow_questions=False)
        except asyncio.CancelledError:
            return

    async def _ready_timeout(self, session_id: str, delay: float) -> None:
        try:
            await asyncio.sleep(delay)
            await self.end_question_session(session_id, "ready_timeout")
        except asyncio.CancelledError:
            return

    async def _session_timeout(self, session_id: str) -> None:
        try:
            await asyncio.sleep(self.settings.question_session_timeout_seconds)
            await self.end_question_session(session_id, "session_timeout")
        except asyncio.CancelledError:
            return

    async def _speaking_timeout(self, session_id: str, question_id: str) -> None:
        try:
            await asyncio.sleep(self.settings.question_speaking_timeout_seconds)
            logger.warning("[QUESTION] Speaking timed out: question_id=%s", question_id)
            await self.end_question_session(session_id, "speaking_timeout")
        except asyncio.CancelledError:
            return

    def _schedule_ready_timeout_locked(self, session_id: str) -> None:
        self._cancel_task(self._ready_timeout_task)
        session = self._question_session
        if session is None:
            return
        remaining = max(0.0, session.deadline - time.monotonic())
        delay = min(self.settings.question_ready_timeout_seconds, remaining)
        self._ready_timeout_task = asyncio.create_task(self._ready_timeout(session_id, delay))

    def _schedule_session_timeout_locked(self, session_id: str) -> None:
        self._cancel_task(self._session_timeout_task)
        self._session_timeout_task = asyncio.create_task(self._session_timeout(session_id))

    def _schedule_speaking_timeout_locked(self, session_id: str, question_id: str) -> None:
        self._cancel_task(self._speaking_timeout_task)
        self._speaking_timeout_task = asyncio.create_task(
            self._speaking_timeout(session_id, question_id)
        )

    def _clear_question_session_locked(self) -> None:
        self._question_session = None
        self._cancel_task(self._ready_timeout_task)
        self._cancel_task(self._session_timeout_task)
        self._cancel_task(self._speaking_timeout_task)
        self._ready_timeout_task = None
        self._session_timeout_task = None
        self._speaking_timeout_task = None

    def _require_question_locked(
        self,
        session_id: str,
        question_id: str | None,
    ) -> QuestionSession:
        session = self._question_session
        if session is None or session.session_id != session_id:
            raise QuestionConflictError("question session is stale")
        if question_id is not None and session.current_question_id != question_id:
            raise QuestionConflictError("question id is stale")
        return session

    @staticmethod
    def _cancel_task(task: asyncio.Task[None] | None) -> None:
        current = asyncio.current_task()
        if task and task is not current and not task.done():
            task.cancel()

    def _ready_payload(self, session: QuestionSession) -> dict[str, Any]:
        remaining = max(
            0,
            int(
                min(
                    self.settings.question_ready_timeout_seconds,
                    session.deadline - time.monotonic(),
                )
            ),
        )
        return {
            "type": "state_changed",
            "state": self.READY,
            "question_session_id": session.session_id,
            "session_seconds_remaining": remaining,
            "gemini_requests_remaining": max(
                0,
                self.settings.gemini_max_requests_per_session - session.gemini_requests_used,
            ),
        }

    @staticmethod
    def _state_payload(state: str, session: QuestionSession) -> dict[str, Any]:
        return {
            "type": "state_changed",
            "state": state,
            "question_session_id": session.session_id,
            "question_id": session.current_question_id,
        }

    def _make_event(
        self,
        customer_type: str,
        customer_id: str,
        visit_count: int,
        days_since_last_visit: int | None,
        discount_eligible: bool,
    ) -> dict[str, Any]:
        return {
            "type": "customer_detected",
            "customer_type": customer_type,
            "customer_id": customer_id,
            "visit_count": visit_count,
            "days_since_last_visit": days_since_last_visit,
            "discount_eligible": discount_eligible,
            "message": build_greeting_message(
                customer_type,
                days_since_last_visit,
                discount_eligible,
                self.settings.discount_valid_days,
            ),
        }
