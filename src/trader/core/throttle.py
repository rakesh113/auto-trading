"""Priority token bucket for order traffic (design §4).

Every place/modify/cancel takes a token. When tokens are short, higher-priority work
goes first: FLATTEN > STOP > EXIT > ENTRY. Slices count individually.
"""

from __future__ import annotations

import asyncio
import heapq
import itertools
import time
from enum import IntEnum


class Priority(IntEnum):
    FLATTEN = 0
    STOP = 1
    EXIT = 2
    ENTRY = 3

    @classmethod
    def for_reason(cls, reason: str) -> Priority:
        return cls.__members__.get(reason.upper(), cls.ENTRY)


class PriorityThrottle:
    def __init__(self, rate_per_sec: float, burst: int, *, monotonic=time.monotonic) -> None:
        if rate_per_sec <= 0 or burst < 1:
            raise ValueError("rate and burst must be positive")
        self._rate = rate_per_sec
        self._burst = float(burst)
        self._tokens = float(burst)
        self._mono = monotonic
        self._last = monotonic()
        self._seq = itertools.count()
        self._waiters: list[tuple[int, int, asyncio.Future[None]]] = []
        self._timer: asyncio.TimerHandle | None = None

    def _refill(self) -> None:
        now = self._mono()
        self._tokens = min(self._burst, self._tokens + (now - self._last) * self._rate)
        self._last = now

    def _pump(self) -> None:
        self._timer = None
        self._refill()
        while self._waiters and self._tokens >= 1.0:
            _, _, fut = heapq.heappop(self._waiters)
            if fut.cancelled():
                continue
            self._tokens -= 1.0
            fut.set_result(None)
        if self._waiters:
            delay = max((1.0 - self._tokens) / self._rate, 0.001)
            self._timer = asyncio.get_running_loop().call_later(delay, self._pump)

    async def acquire(self, priority: Priority = Priority.ENTRY) -> None:
        fut: asyncio.Future[None] = asyncio.get_running_loop().create_future()
        heapq.heappush(self._waiters, (int(priority), next(self._seq), fut))
        if self._timer is None:
            self._pump()
        await fut
