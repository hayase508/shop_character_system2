from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Sequence

from .config import Settings
from .customer_service import CustomerService, build_greeting_message
from .websocket_manager import WebSocketManager


logger = logging.getLogger(__name__)


class ReceptionController:
    IDLE = "IDLE"
    GREETING = "GREETING"

    def __init__(
        self,
        customer_service: CustomerService,
        websocket_manager: WebSocketManager,
        settings: Settings,
    ) -> None:
        self.customer_service = customer_service
        self.websocket_manager = websocket_manager
        self.settings = settings
        self._state = self.IDLE
        self._lock = asyncio.Lock()
        self._last_global_greeting_at: datetime | None = None
        self._person_greeting_at: dict[str, datetime] = {}
        self._current_greeting_id: str | None = None
        self._current_event: dict[str, Any] | None = None
        self._timeout_task: asyncio.Task[None] | None = None

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
                    # Keep last_seen_at current, even during speech/cooldown.
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
            self._activate_locked(event, now)

        await self._announce(event)
        return event

    async def start_debug_event(self, event: dict[str, Any]) -> dict[str, Any] | None:
        now = datetime.now(timezone.utc)
        async with self._lock:
            if self._state != self.IDLE or not self.websocket_manager.display_ready():
                return None
            debug_event = dict(event)
            self._activate_locked(debug_event, now)
        await self._announce(debug_event)
        return debug_event

    async def finish(self, greeting_id: str | None = None) -> bool:
        task_to_cancel: asyncio.Task[None] | None = None
        async with self._lock:
            if self._state != self.GREETING:
                return False
            if greeting_id and greeting_id != self._current_greeting_id:
                return False

            self._state = self.IDLE
            finished_at = datetime.now(timezone.utc)
            self._last_global_greeting_at = finished_at
            if self._current_event:
                self._person_greeting_at[self._current_event["customer_id"]] = finished_at
            self._current_greeting_id = None
            self._current_event = None
            task_to_cancel = self._timeout_task
            self._timeout_task = None

        current_task = asyncio.current_task()
        if task_to_cancel and task_to_cancel is not current_task:
            task_to_cancel.cancel()
        logger.info("[GREETING] Finished")
        logger.info("[STATE] IDLE")
        await self.websocket_manager.broadcast({"type": "state_changed", "state": self.IDLE})
        return True

    async def snapshot(self) -> dict[str, Any]:
        async with self._lock:
            return {
                "type": "state_changed",
                "state": self._state,
                "greeting_id": self._current_greeting_id,
            }

    async def current_event(self) -> dict[str, Any] | None:
        async with self._lock:
            return dict(self._current_event) if self._current_event else None

    async def close(self) -> None:
        task = self._timeout_task
        self._timeout_task = None
        if task:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

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

    def _activate_locked(self, event: dict[str, Any], now: datetime) -> None:
        greeting_id = uuid.uuid4().hex
        event["greeting_id"] = greeting_id
        self._state = self.GREETING
        self._current_greeting_id = greeting_id
        self._current_event = dict(event)
        self._last_global_greeting_at = now
        customer_id = event.get("customer_id")
        if customer_id:
            self._person_greeting_at[str(customer_id)] = now

        self._timeout_task = asyncio.create_task(self._finish_after_timeout(greeting_id))
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
            await self.finish(str(event["greeting_id"]))

    async def _finish_after_timeout(self, greeting_id: str) -> None:
        try:
            await asyncio.sleep(self.settings.greeting_timeout_seconds)
            logger.warning("[GREETING] Timed out; forcing IDLE")
            await self.finish(greeting_id)
        except asyncio.CancelledError:
            return

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
