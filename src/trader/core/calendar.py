"""Trading calendar: holidays and session times (design §8, §14).

Holidays come from Upstox `/v2/market/holidays` and are cached per year under
`<data_dir>/reference/`. Special sessions (Muhurat, DR drills) are *not* trading days
for this system unless explicitly enabled (design §14).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any

from trader.domain.types import IST


@dataclass(frozen=True, slots=True)
class Session:
    open: time
    close: time


# Regular sessions (IST). MCX close moves with US daylight time (design §7.4).
EQUITY = Session(time(9, 15), time(15, 30))
PRE_OPEN = Session(time(9, 0), time(9, 12))
MCX_SUMMER = Session(time(9, 0), time(23, 30))
MCX_WINTER = Session(time(9, 0), time(23, 55))


class MarketCalendar:
    def __init__(self, holidays: list[dict[str, Any]]) -> None:
        self._closed: dict[date, set[str]] = {}
        for h in holidays:
            d = date.fromisoformat(h["date"])
            self._closed.setdefault(d, set()).update(h.get("closed_exchanges") or [])

    @classmethod
    def from_cache(cls, path: Path) -> MarketCalendar:
        return cls(json.loads(path.read_text(encoding="utf-8")))

    def is_trading_day(self, d: date, exchange: str = "NSE") -> bool:
        if d.weekday() >= 5:
            return False
        return exchange not in self._closed.get(d, set())

    def next_trading_day(self, d: date, exchange: str = "NSE") -> date:
        d += timedelta(days=1)
        while not self.is_trading_day(d, exchange):
            d += timedelta(days=1)
        return d

    @staticmethod
    def at(d: date, t: time) -> datetime:
        return datetime.combine(d, t, IST)


async def fetch_holidays(http: Any, cache_dir: Path, year: int, *, refresh: bool = False) -> Path:
    """Download (or reuse) the holiday list for `year`. `http` is an UpstoxHttp."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    path = cache_dir / f"holidays-{year}.json"
    if path.exists() and not refresh:
        return path
    body = await http.get("/v2/market/holidays")
    rows = [r for r in body.get("data", []) if str(r.get("date", "")).startswith(str(year))]
    if not rows:
        raise RuntimeError(f"no holidays returned for {year}")
    path.write_text(json.dumps(rows, indent=1), encoding="utf-8")
    return path
