"""WebSocket hub (Contract #5).

Owns the broadcast bus + per-client connection lifecycle. The bus assigns
monotonic event IDs and keeps the last 1 000 events in a ring buffer so
reconnecting clients can ``resume`` from the cursor they last acknowledged.

Wire protocol (client → daemon):

  ``{"type": "resume", "since": <int>}``     — replay events with id > since.
                                                 Send once immediately after connect.
  ``{"type": "ping"}``                       — daemon replies with ``{"type": "pong"}``.

Wire protocol (daemon → client):

  Every broadcast event:
  ``{"id": <int>, "name": "v1.entity.verb", "payload": {...}, "timestamp_utc": "<iso>"}``

  Replay envelope (sent once before the live stream after a resume):
  ``{"type": "replay", "events": [<event>, ...], "buffer_min_id": <int>}``

  If ``since`` is older than ``buffer_min_id``, the daemon emits an error event:
  ``{"name": "v1.ws.replay_window_exceeded", "payload": {"since": N, "buffer_min_id": M}}``
  and the client is expected to refetch state from REST.
"""

from __future__ import annotations

import asyncio
import logging
from collections import deque
from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field

from .api_versions import event_name
from .time_utils import to_iso, utc_now

log = logging.getLogger(__name__)

# Contract #5 — buffer 1 000 events.
RING_BUFFER_SIZE = 1000


class Event(BaseModel):
    """One broadcast event."""

    id: int
    name: str  # 'v1.entity.verb' — Contracts #7, #10
    payload: dict[str, Any] = Field(default_factory=dict)
    timestamp_utc: str  # ISO 8601 UTC (Contract #24)


SubscriberFn = Callable[[Event], Awaitable[None]]


class EventBus:
    """Monotonic event ID counter + ring buffer + subscriber fan-out.

    Methods are coroutine-safe via a single ``asyncio.Lock``. Synchronous code
    (e.g. orphan reconciler running before uvicorn boots) can call
    :meth:`publish_sync` to enqueue events that will be drained on the first
    awaited tick.
    """

    def __init__(self, buffer_size: int = RING_BUFFER_SIZE) -> None:
        self._next_id = 1
        self._buffer: deque[Event] = deque(maxlen=buffer_size)
        self._subscribers: set[SubscriberFn] = set()
        self._lock = asyncio.Lock()

    # ── ID + buffer state ────────────────────────────────────────────────

    @property
    def last_event_id(self) -> int:
        return self._next_id - 1

    @property
    def buffer_min_id(self) -> int:
        """ID of the oldest event still replayable; ``0`` if empty."""

        return self._buffer[0].id if self._buffer else 0

    def buffer_size(self) -> int:
        return len(self._buffer)

    # ── publishing ───────────────────────────────────────────────────────

    async def publish(self, name: str, payload: dict[str, Any] | None = None) -> Event:
        async with self._lock:
            event = Event(
                id=self._next_id,
                name=name,
                payload=payload or {},
                timestamp_utc=to_iso(utc_now()),
            )
            self._next_id += 1
            self._buffer.append(event)
            subscribers = list(self._subscribers)

        # Fan out outside the lock so a slow subscriber can't block the bus.
        for handler in subscribers:
            try:
                await handler(event)
            except Exception:  # pragma: no cover — defensive
                log.exception("WS subscriber raised; dropping event for that subscriber.")

        return event

    # ── replay ───────────────────────────────────────────────────────────

    def replay_since(self, since: int) -> list[Event]:
        """Return buffered events with ``id > since`` (newest order preserved).

        Empty list if the caller is already up-to-date. Caller is responsible
        for handling the "since older than buffer_min_id" case via
        :meth:`replay_window_exceeded`.
        """

        return [e for e in self._buffer if e.id > since]

    def replay_window_exceeded(self, since: int) -> bool:
        """Has ``since`` fallen off the back of the ring buffer?

        ``since == 0`` is the "first connect ever" case — never an error.
        """

        if since <= 0:
            return False
        return since < self.buffer_min_id

    # ── subscriptions ────────────────────────────────────────────────────

    async def subscribe(self, handler: SubscriberFn) -> None:
        async with self._lock:
            self._subscribers.add(handler)

    async def unsubscribe(self, handler: SubscriberFn) -> None:
        async with self._lock:
            self._subscribers.discard(handler)


class _Resume(BaseModel):
    type: str = Field(pattern=r"^resume$")
    since: int = Field(ge=0)
    token: str | None = None  # device auth token (Milestone H)


class WsHub:
    """Connects a FastAPI :class:`WebSocket` to the :class:`EventBus`."""

    def __init__(self, bus: EventBus, auth: object | None = None) -> None:
        self.bus = bus
        # AuthManager — optional so tests can build a hub without auth.
        self.auth = auth

    async def handle(self, websocket: WebSocket) -> None:
        await websocket.accept()

        queue: asyncio.Queue[Event] = asyncio.Queue()

        async def deliver(event: Event) -> None:
            await queue.put(event)

        await self.bus.subscribe(deliver)

        sender_task: asyncio.Task[None] | None = None
        try:
            # Phase 1 — wait briefly for an optional resume frame. The
            # protocol says clients SHOULD send it immediately on connect, but
            # we tolerate it not arriving (treat as ``since=0``).
            since, token = await self._read_resume_or_zero(websocket)

            # Auth (Milestone H): a socket straight from this machine is
            # trusted; anything else (LAN, a tunnel) must present a valid
            # device token in the resume frame.
            if self.auth is not None:
                from .auth import is_trusted_local

                if not (is_trusted_local(websocket) or self.auth.verify(token)):
                    await websocket.close(code=1008)  # policy violation
                    return

            if self.bus.replay_window_exceeded(since):
                await websocket.send_json(
                    {
                        "type": "error",
                        "name": event_name("ws", "replay_window_exceeded"),
                        "payload": {
                            "since": since,
                            "buffer_min_id": self.bus.buffer_min_id,
                        },
                    }
                )
                since = 0  # client must refetch state; we won't replay

            await websocket.send_json(
                {
                    "type": "replay",
                    "events": [e.model_dump() for e in self.bus.replay_since(since)],
                    "buffer_min_id": self.bus.buffer_min_id,
                    "last_event_id": self.bus.last_event_id,
                }
            )

            # Phase 2 — fan-out loop + ping listener run concurrently.
            sender_task = asyncio.create_task(self._sender(websocket, queue))
            await self._receiver(websocket)

        except WebSocketDisconnect:
            pass
        finally:
            await self.bus.unsubscribe(deliver)
            if sender_task is not None:
                sender_task.cancel()
                try:
                    await sender_task
                except (asyncio.CancelledError, Exception):
                    pass

    # ── private helpers ──────────────────────────────────────────────────

    async def _read_resume_or_zero(self, websocket: WebSocket) -> tuple[int, str | None]:
        """Return ``(since, token)`` from the optional resume frame."""

        try:
            data = await asyncio.wait_for(websocket.receive_json(), timeout=0.5)
        except (TimeoutError, Exception):
            return 0, None
        try:
            resume = _Resume.model_validate(data)
        except Exception:
            return 0, None
        return resume.since, resume.token

    async def _sender(self, websocket: WebSocket, queue: asyncio.Queue[Event]) -> None:
        while True:
            event = await queue.get()
            await websocket.send_json(event.model_dump())

    async def _receiver(self, websocket: WebSocket) -> None:
        while True:
            data = await websocket.receive_json()
            if isinstance(data, dict) and data.get("type") == "ping":
                await websocket.send_json({"type": "pong"})
            # Unknown messages are ignored on purpose; client + daemon evolve
            # via the versioned event name, not by extending this dispatcher.
