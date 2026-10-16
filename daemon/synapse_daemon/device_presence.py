"""Periodic account device presence independent of the Settings UI."""
from __future__ import annotations

import asyncio
import logging

log = logging.getLogger(__name__)


class DevicePresenceLoop:
    def __init__(self, profile, *, interval_seconds: float = 120.0):
        self.profile = profile
        self.interval_seconds = interval_seconds
        self._task: asyncio.Task | None = None

    def _publish(self) -> None:
        if not self.profile._state_row()["user_id"]:
            return
        self.profile.ensure_current_host()
        self.profile._sync_to_remote(best_effort=True)

    async def _run(self) -> None:
        while True:
            try:
                await asyncio.to_thread(self._publish)
            except asyncio.CancelledError:
                raise
            except Exception:
                log.warning("Account device presence refresh failed; retrying later", exc_info=True)
            await asyncio.sleep(self.interval_seconds)

    async def start(self) -> None:
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._run(), name="synapse-device-presence")

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
