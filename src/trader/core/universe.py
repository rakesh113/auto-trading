"""Build today's recording/subscription set from config/universe.yaml (design §11)."""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

import httpx
import structlog

from trader.domain.instrument import InstrumentId
from trader.domain.types import Exchange, FeedMode, InstrumentKind
from trader.ports.marketdata import InstrumentMaster

log = structlog.get_logger(__name__)


async def index_constituents(name: str, urls: list[str], cache_dir: Path, month: str) -> list[str]:
    """Symbols of an NSE index, cached per month. Falls back to the newest cache."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    path = cache_dir / f"{name}-{month}.csv"
    if not path.exists():
        for url in urls:
            try:
                async with httpx.AsyncClient(timeout=30, headers={"User-Agent": "Mozilla/5.0"}) as c:
                    r = await c.get(url)
                    r.raise_for_status()
                if b"Symbol" not in r.content[:200]:
                    raise ValueError("unexpected content")
                path.write_bytes(r.content)
                break
            except (httpx.HTTPError, ValueError) as e:
                log.warning("universe.download_failed", url=url, error=repr(e))
    if not path.exists():
        cached = sorted(cache_dir.glob(f"{name}-*.csv"))
        if not cached:
            raise RuntimeError(f"cannot get constituents for {name}")
        path = cached[-1]
        log.warning("universe.using_stale_cache", path=str(path))
    rows = csv.DictReader(io.StringIO(path.read_text(encoding="utf-8-sig")))
    return [r["Symbol"].strip().upper() for r in rows if r.get("Symbol")]


def nearest_future(master: InstrumentMaster, symbol: str, today: date,
                   exchange: Exchange = Exchange.NSE) -> InstrumentId | None:
    futs = sorted(
        (i.id for i in master.all()
         if i.id.kind is InstrumentKind.FUT and i.id.symbol == symbol and i.id.exchange is exchange
         and i.id.expiry and i.id.expiry >= today),
        key=lambda x: x.expiry,  # type: ignore[arg-type,return-value]
    )
    return futs[0] if futs else None


def fno_stock_underlyings(master: InstrumentMaster) -> set[str]:
    return {
        i.underlying.split(":")[2]
        for i in master.all()
        if i.id.kind is InstrumentKind.FUT and i.id.exchange is Exchange.NSE and i.underlying
        and i.underlying.startswith("NSE:EQ:")
    }


def option_window(master: InstrumentMaster, underlying: str, exchange: Exchange, today: date,
                  spot_paise: int, each_side: int) -> list[InstrumentId]:
    """Nearest-expiry CE and PE strikes around spot. Expiry comes from the master only."""
    opts = [i.id for i in master.all()
            if i.id.kind is InstrumentKind.OPT and i.id.symbol == underlying and i.id.exchange is exchange
            and i.id.expiry and i.id.expiry >= today]
    if not opts:
        return []
    expiry = min(o.expiry for o in opts)  # type: ignore[type-var]
    strikes = sorted({o.strike for o in opts if o.expiry == expiry})  # type: ignore[type-var]
    spot = Decimal(spot_paise) / 100
    atm_idx = min(range(len(strikes)), key=lambda k: abs(strikes[k] - spot))  # type: ignore[operator]
    chosen = set(strikes[max(0, atm_idx - each_side): atm_idx + each_side + 1])
    return sorted(o for o in opts if o.expiry == expiry and o.strike in chosen)


@dataclass
class RecordingPlan:
    want: dict[InstrumentId, FeedMode] = field(default_factory=dict)
    missing: list[str] = field(default_factory=list)

    def add(self, iid: InstrumentId | None, mode: FeedMode, label: str) -> None:
        if iid is None:
            self.missing.append(label)
            return
        cur = self.want.get(iid)
        if cur is None or _rank(mode) > _rank(cur):
            self.want[iid] = mode


def _rank(m: FeedMode) -> int:
    return [FeedMode.LTPC, FeedMode.OPTION_GREEKS, FeedMode.FULL, FeedMode.FULL_D30].index(m)


def build_recording_plan(master: InstrumentMaster, uni: dict[str, Any], today: date,
                         nifty500: list[str]) -> RecordingPlan:
    rec = uni.get("record", {})
    plan = RecordingPlan()

    def eq(sym: str) -> InstrumentId | None:
        iid = InstrumentId(Exchange.NSE, InstrumentKind.EQ, sym)
        return iid if master.find(iid) else None

    if rec.get("ltpc_nifty500"):
        for s in nifty500:
            plan.add(eq(s), FeedMode.LTPC, f"nifty500:{s}")
    for s in rec.get("full_indices", rec.get("ltpc_indices", [])):
        iid = InstrumentId.parse(s)
        plan.add(iid if master.find(iid) else None, FeedMode.FULL, f"index:{s}")
    if rec.get("full_fno_stocks"):
        for s in sorted(fno_stock_underlyings(master)):
            plan.add(eq(s), FeedMode.FULL, f"fno:{s}")
    for s in rec.get("full_index_futures", []):
        plan.add(nearest_future(master, s, today), FeedMode.FULL, f"fut:{s}")
    for s in rec.get("depth30_stocks", []):
        plan.add(eq(s), FeedMode.FULL_D30, f"d30:{s}")
    for s in rec.get("depth30_index_futures", []):
        plan.add(nearest_future(master, s, today), FeedMode.FULL_D30, f"d30fut:{s}")
    if plan.missing:
        log.warning("universe.unmapped", count=len(plan.missing), sample=plan.missing[:10])
    return plan
