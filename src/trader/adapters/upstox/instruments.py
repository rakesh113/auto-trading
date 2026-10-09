"""Upstox instrument master → canonical instruments (design §10, §11).

Upstox rebuilds the gzipped master around 06:00 IST. We keep each day's raw file
under `<data_dir>/reference/upstox/` so every day stays point-in-time reproducible.
"""

from __future__ import annotations

import gzip
import json
from collections.abc import Iterable
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING, Any

import httpx
import structlog

from trader.core.registry import masters
from trader.domain.instrument import Instrument, InstrumentId
from trader.domain.types import IST, Exchange, InstrumentKind, OptionRight
from trader.ports.marketdata import InstrumentMaster

if TYPE_CHECKING:
    from trader.core.app import AppContext

log = structlog.get_logger(__name__)

VENUE = "upstox"
_EXCH = {"NSE_EQ": Exchange.NSE, "BSE_EQ": Exchange.BSE, "NSE_INDEX": Exchange.NSE, "BSE_INDEX": Exchange.BSE,
         "NSE_FO": Exchange.NSE, "BSE_FO": Exchange.BSE, "MCX_FO": Exchange.MCX}


def _index_symbol(native_key: str) -> str:
    """'NSE_INDEX|Nifty 50' → 'NIFTY50'; 'NSE_INDEX|India VIX' → 'INDIAVIX'."""
    return "".join(ch for ch in native_key.split("|", 1)[1].upper() if ch.isalnum())


def _expiry(ms: int) -> date:
    return datetime.fromtimestamp(ms / 1000, IST).date()


def parse_row(r: dict[str, Any]) -> InstrumentId | None:
    seg = r.get("segment")
    exch = _EXCH.get(seg or "")
    if exch is None:
        return None
    itype = r.get("instrument_type", "")
    if seg in ("NSE_EQ", "BSE_EQ"):
        sym = (r.get("trading_symbol") or "").strip().upper()
        return InstrumentId(exch, InstrumentKind.EQ, sym) if sym and ":" not in sym else None
    if seg in ("NSE_INDEX", "BSE_INDEX"):
        return InstrumentId(exch, InstrumentKind.IDX, _index_symbol(r["instrument_key"]))
    sym = (r.get("underlying_symbol") or r.get("asset_symbol") or "").strip().upper()
    if not sym or not r.get("expiry"):
        return None
    exp = _expiry(int(r["expiry"]))
    if itype == "FUT":
        return InstrumentId(exch, InstrumentKind.FUT, sym, exp)
    if itype in ("CE", "PE"):
        return InstrumentId(exch, InstrumentKind.OPT, sym, exp, Decimal(str(r["strike_price"])), OptionRight(itype))
    return None


@masters.register(VENUE)
class UpstoxInstrumentMaster(InstrumentMaster):
    venue = VENUE

    def __init__(self, *, data_dir: Path, url: str, equity_series: Iterable[str] | None = None,
                 transport: httpx.AsyncBaseTransport | None = None) -> None:
        self._dir = Path(data_dir) / "reference" / VENUE
        self._url = url
        self._series = set(equity_series) if equity_series is not None else {"EQ", "BE"}
        self._transport = transport
        self._by_id: dict[InstrumentId, Instrument] = {}
        self._by_native: dict[str, InstrumentId] = {}
        self.day: date | None = None
        self.duplicates: int = 0

    @classmethod
    def build(cls, ctx: AppContext) -> UpstoxInstrumentMaster:
        return cls(data_dir=ctx.cfg.system.data_dir, url=ctx.cfg.upstox.instruments_url)

    def path_for(self, day: date) -> Path:
        return self._dir / f"instruments-{day.isoformat()}.json.gz"

    async def download(self, day: date) -> Path:
        self._dir.mkdir(parents=True, exist_ok=True)
        dest = self.path_for(day)
        tmp = dest.with_suffix(".part")
        async with httpx.AsyncClient(timeout=120, transport=self._transport) as c:
            resp = await c.get(self._url)
            resp.raise_for_status()
            tmp.write_bytes(resp.content)
        json.loads(gzip.decompress(tmp.read_bytes()))  # refuse to keep a corrupt file
        tmp.replace(dest)
        log.info("instruments.downloaded", path=str(dest), bytes=dest.stat().st_size)
        return dest

    async def load(self, day: date, *, refresh: bool = False) -> int:
        p = self.path_for(day)
        if refresh or not p.exists():
            p = await self.download(day)
        rows = json.loads(gzip.decompress(p.read_bytes()))
        self.load_rows(rows)
        self.day = day
        return len(self._by_id)

    def load_rows(self, rows: list[dict[str, Any]]) -> None:
        by_id: dict[InstrumentId, Instrument] = {}
        by_native: dict[str, InstrumentId] = {}
        dup = 0
        pending_underlying: list[tuple[InstrumentId, str]] = []
        for r in rows:
            if r.get("segment") == "NSE_EQ" and r.get("instrument_type") not in self._series:
                continue  # bonds, SME, T-bills etc. share the NSE_EQ segment
            try:
                iid = parse_row(r)
            except (ValueError, KeyError):
                iid = None
            if iid is None:
                continue
            if iid in by_id:
                dup += 1
                continue
            key = r["instrument_key"]
            inst = Instrument(
                id=iid,
                name=r.get("name") or "",
                tick_size=round(float(r.get("tick_size") or 5)),  # Upstox publishes tick size in paise
                lot_size=int(r.get("lot_size") or 1),
                freeze_qty=int(r["freeze_quantity"]) if r.get("freeze_quantity") else None,
                isin=r.get("isin"),
                series=r.get("instrument_type") if iid.kind is InstrumentKind.EQ else None,
                cas_eligible=bool(r.get("cas_eligible", False)),
                qty_multiplier=Decimal(str(r.get("qty_multiplier") or 1)),
                weekly=r.get("weekly"),
                native={VENUE: key},
            )
            by_id[iid] = inst
            by_native[key] = iid
            if r.get("underlying_key"):
                pending_underlying.append((iid, r["underlying_key"]))
        for iid, ukey in pending_underlying:
            u = by_native.get(ukey)
            if u is not None:
                inst = by_id[iid]
                by_id[iid] = Instrument(**{**{s: getattr(inst, s) for s in inst.__slots__}, "underlying": str(u)})
        self._by_id, self._by_native, self.duplicates = by_id, by_native, dup
        if dup:
            log.warning("instruments.duplicates_skipped", count=dup)

    def get(self, iid: InstrumentId) -> Instrument:
        try:
            return self._by_id[iid]
        except KeyError:
            raise KeyError(f"{iid} not in {VENUE} master for {self.day}") from None

    def find(self, iid: InstrumentId) -> Instrument | None:
        return self._by_id.get(iid)

    def from_native(self, native: str) -> InstrumentId | None:
        return self._by_native.get(native)

    def to_native(self, iid: InstrumentId) -> str:
        return self.get(iid).native_key(VENUE)

    def all(self) -> Iterable[Instrument]:
        return self._by_id.values()

    # ---- helpers used by universe/selection -------------------------------------------------

    def derivatives(self, underlying_symbol: str, kind: InstrumentKind, exchange: Exchange = Exchange.NSE,
                    ) -> list[Instrument]:
        return sorted(
            (i for i in self._by_id.values()
             if i.id.kind is kind and i.id.symbol == underlying_symbol and i.id.exchange is exchange),
            key=lambda i: (i.id.expiry, i.id.strike or 0, i.id.right or ""),
        )

    def expiries(self, underlying_symbol: str, kind: InstrumentKind = InstrumentKind.OPT,
                 exchange: Exchange = Exchange.NSE, on_or_after: date | None = None) -> list[date]:
        """Expiry dates from the contract master — never from weekday logic (design §4)."""
        exps = {i.id.expiry for i in self.derivatives(underlying_symbol, kind, exchange) if i.id.expiry}
        return sorted(e for e in exps if on_or_after is None or e >= on_or_after)
