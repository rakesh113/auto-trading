"""The Clock port: the only source of "now" in core code (design §10, look-ahead prevention)."""

from __future__ import annotations

from datetime import date, datetime
from typing import Protocol

from trader.domain.types import IST


class Clock(Protocol):
    def now_ns(self) -> int: ...

    def monotonic_ns(self) -> int: ...

    async def sleep(self, seconds: float) -> None: ...


def now_ist(clock: Clock) -> datetime:
    return datetime.fromtimestamp(clock.now_ns() / 1e9, IST)


def today_ist(clock: Clock) -> date:
    return now_ist(clock).date()
