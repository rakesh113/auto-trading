"""Clock implementations: wall time for paper/live, simulated time for replay and tests."""

from __future__ import annotations

import asyncio
import time


class WallClock:
    def now_ns(self) -> int:
        return time.time_ns()

    def monotonic_ns(self) -> int:
        return time.monotonic_ns()

    async def sleep(self, seconds: float) -> None:
        await asyncio.sleep(seconds)


class SimClock:
    """Manually advanced clock. `sleep` advances time instead of waiting."""

    def __init__(self, start_ns: int = 0) -> None:
        self._now = start_ns

    def now_ns(self) -> int:
        return self._now

    def monotonic_ns(self) -> int:
        return self._now

    def set(self, ts_ns: int) -> None:
        if ts_ns < self._now:
            raise ValueError("SimClock cannot go backwards")
        self._now = ts_ns

    def advance(self, seconds: float) -> None:
        self._now += int(seconds * 1e9)

    async def sleep(self, seconds: float) -> None:
        self.advance(seconds)
        await asyncio.sleep(0)
