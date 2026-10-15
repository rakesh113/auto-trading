"""Historical candles and each symbol's pre-market context (design §7.1, §11).

`DailyContext` holds what the hot path needs before the open: ATR14, previous-day
high/low/close, 20-day volume curve by minute (for RVOL), median turnover, 52-week
high/low and moving averages. Built once per day from Upstox history and cached as
JSON under `<data_dir>/reference/context/<date>.json`, so replay uses exactly the
context the live run used (point-in-time, design §10).
"""

from __future__ import annotations

import asyncio
import json
import statistics
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import quote

import structlog

from trader.adapters.upstox.http import UpstoxError, UpstoxHttp
from trader.domain.instrument import InstrumentId
from trader.domain.types import IST, to_paise
from trader.ports.marketdata import InstrumentMaster

log = structlog.get_logger(__name__)

SESSION_MINUTES = 360  # 09:15 → 15:15 continuous session used for volume curves (CAS starts 15:15)


@dataclass
class DailyContext:
    iid: str
    atr14: int  # paise
    pdh: int
    pdl: int
    pdc: int
    pd_volume: int
    median_turnover_cr: float  # 20-day median of close × volume, ₹ crore
    high_52w: int
    low_52w: int
    sma20: int
    sma50: int
    # cumulative average volume at each minute since 09:15 over the last ≤20 sessions
    vol_curve: list[float] = field(default_factory=list)

    def expected_volume_by(self, minutes_since_open: int) -> float | None:
        if not self.vol_curve:
            return None
        i = min(max(minutes_since_open, 1), len(self.vol_curve)) - 1
        return self.vol_curve[i] or None


def _atr(daily: list[list[Any]], n: int = 14) -> float:
    """daily rows oldest→newest: [ts, o, h, l, c, v, oi]. Wilder-free simple mean of true range."""
    trs = []
    for prev, cur in zip(daily, daily[1:], strict=False):
        h, lo, pc = cur[2], cur[3], prev[4]
        trs.append(max(h - lo, abs(h - pc), abs(lo - pc)))
    tail = trs[-n:]
    return sum(tail) / len(tail) if tail else 0.0


def build_context(iid: InstrumentId, daily_newest_first: list[list[Any]],
                  minutes_newest_first: list[list[Any]]) -> DailyContext | None:
    daily = list(reversed(daily_newest_first))
    if len(daily) < 20:
        return None
    last = daily[-1]
    closes = [r[4] for r in daily]
    turnover = [r[4] * r[5] / 1e7 for r in daily[-20:]]
    # volume curve: per session, cumulative volume by minute from 09:15
    sessions: dict[str, list[float]] = {}
    for ts, _o, _h, _l, _c, v, *_ in reversed(minutes_newest_first):
        t = datetime.fromisoformat(ts)
        m = (t.hour * 60 + t.minute) - (9 * 60 + 15)
        if 0 <= m < SESSION_MINUTES:
            sessions.setdefault(t.date().isoformat(), [0.0] * SESSION_MINUTES)[m] += v
    curves = []
    for per_min in list(sessions.values())[-20:]:
        cum, acc = [], 0.0
        for x in per_min:
            acc += x
            cum.append(acc)
        curves.append(cum)
    vol_curve = [statistics.fmean(c[i] for c in curves) for i in range(SESSION_MINUTES)] if curves else []
    yr = daily[-252:]
    return DailyContext(
        iid=str(iid), atr14=to_paise(_atr(daily)), pdh=to_paise(last[2]), pdl=to_paise(last[3]),
        pdc=to_paise(last[4]), pd_volume=int(last[5]), median_turnover_cr=statistics.median(turnover),
        high_52w=to_paise(max(r[2] for r in yr)), low_52w=to_paise(min(r[3] for r in yr)),
        sma20=to_paise(statistics.fmean(closes[-20:])), sma50=to_paise(statistics.fmean(closes[-50:])),
        vol_curve=[round(x) for x in vol_curve],
    )


class ContextStore:
    def __init__(self, data_dir: Path) -> None:
        self.dir = Path(data_dir) / "reference" / "context"

    def path(self, day: date) -> Path:
        return self.dir / f"{day.isoformat()}.json"

    def load(self, day: date) -> dict[str, DailyContext]:
        raw = json.loads(self.path(day).read_text(encoding="utf-8"))
        return {k: DailyContext(**v) for k, v in raw.items()}

    def save(self, day: date, ctx: dict[str, DailyContext]) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        tmp = self.path(day).with_suffix(".part")
        tmp.write_text(json.dumps({k: asdict(v) for k, v in ctx.items()}), encoding="utf-8")
        tmp.replace(self.path(day))


async def fetch_contexts(http: UpstoxHttp, master: InstrumentMaster, iids: list[InstrumentId], day: date,
                         *, concurrency: int = 4) -> dict[str, DailyContext]:
    """Context for `day` from candles strictly before `day` (no look-ahead)."""
    to = (day - timedelta(days=1)).isoformat()
    sem = asyncio.Semaphore(concurrency)
    out: dict[str, DailyContext] = {}

    async def one(iid: InstrumentId) -> None:
        key = quote(master.to_native(iid), safe="")
        async with sem:
            try:
                d = await http.get(f"/v3/historical-candle/{key}/days/1/{to}/{(day - timedelta(days=400)).isoformat()}")
                m = await http.get(f"/v3/historical-candle/{key}/minutes/1/{to}/{(day - timedelta(days=30)).isoformat()}")
            except UpstoxError as e:
                log.warning("history.failed", iid=str(iid), error=str(e))
                return
        c = build_context(iid, d["data"]["candles"], m["data"]["candles"])
        if c is not None:
            out[str(iid)] = c

    await asyncio.gather(*(one(i) for i in iids))
    log.info("history.contexts", requested=len(iids), built=len(out))
    return out


def ist_now_minutes(ts_ns: int) -> int:
    """Minutes since 09:15 IST for a timestamp (negative before the open)."""
    t = datetime.fromtimestamp(ts_ns / 1e9, IST)
    return (t.hour * 60 + t.minute) - (9 * 60 + 15)
