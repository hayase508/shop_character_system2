from __future__ import annotations

import asyncio
import logging
from typing import Any

from fastapi import WebSocket


logger = logging.getLogger(__name__)


class WebSocketManager:
    def __init__(self) -> None:
        self._connections: set[WebSocket] = set()
        self._lock = asyncio.Lock()
        self._display: WebSocket | None = None
        self._questions_available = False

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        async with self._lock:
            self._connections.add(websocket)
        logger.info("[WEBSOCKET] Connected: clients=%s", await self.connection_count())

    async def disconnect(self, websocket: WebSocket) -> None:
        async with self._lock:
            self._connections.discard(websocket)
            if self._display is websocket:
                self._display = None
                self._questions_available = False
        logger.info("[WEBSOCKET] Disconnected: clients=%s", await self.connection_count())

    async def connection_count(self) -> int:
        async with self._lock:
            return len(self._connections)

    async def claim_display(self, websocket: WebSocket) -> bool:
        async with self._lock:
            if self._display is not None and self._display is not websocket:
                logger.warning("[WEBSOCKET] Display claim rejected; another display is active")
                return False
            self._display = websocket
            self._questions_available = False
            logger.info("[WEBSOCKET] Display is ready")
            return True

    async def set_question_capability(self, websocket: WebSocket, available: bool) -> bool:
        async with self._lock:
            if self._display is not websocket:
                return False
            self._questions_available = bool(available)
            logger.info("[QUESTION] Browser microphone available: %s", available)
            return True

    def is_display(self, websocket: WebSocket) -> bool:
        return self._display is websocket

    def display_ready(self) -> bool:
        return self._display is not None

    def questions_available(self) -> bool:
        return self._display is not None and self._questions_available

    async def broadcast(self, payload: dict[str, Any]) -> int:
        async with self._lock:
            connections = list(self._connections)
            if payload.get("type") == "customer_detected":
                connections = [self._display] if self._display else []

        disconnected: list[WebSocket] = []
        delivered = 0
        for websocket in connections:
            try:
                await asyncio.wait_for(websocket.send_json(payload), timeout=3)
                delivered += 1
            except Exception:
                logger.warning("[WEBSOCKET] Send failed; removing disconnected client")
                disconnected.append(websocket)

        if disconnected:
            async with self._lock:
                for websocket in disconnected:
                    self._connections.discard(websocket)
                    if self._display is websocket:
                        self._display = None
        return delivered
