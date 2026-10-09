"""Per-day exchange reference data the hard rules need (design §6, §7.1).

* F&O ban list (NSE `fo_secban.csv`): banned names → cash longs only, at 0.5x.
* Price bands (Upstox quote API circuit limits): no new entries within 1% of a band.

Fetched once at session start and cached as `<data_dir>/reference/dayref-<date>.json`, so
replay applies exactly what the live run applied. F&O stocks have *dynamic* bands that the
exchange can flex intraday; the start-of-day snapshot is the conservative (narrower) value.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import httpx
import structlog

from trader.adapters.upstox.http import UpstoxHttp
from trader.domain.instrument import InstrumentId
from trader.domain.types import to_paise
from trader.ports.marketdata import InstrumentMaster

log = structlog.get_logger(__name__)

BAN_URL = "https://nsearchives.nseindia.com/content/fo/fo_secban.csv"


@dataclass
class DayReference:
    ban: set[str] = field(default_factory=set)  # NSE symbols
    bands: dict[str, tuple[int, int]] = field(default_factory=dict)  # iid -> (lower, upper) paise

    def band(self, iid: InstrumentId) -> tuple[int, int] | None:
        return self.bands.get(str(iid))

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"ban": sorted(self.ban), "bands": self.bands}), encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> DayReference:
        d = json.loads(path.read_text(encoding="utf-8"))
        return cls(set(d["ban"]), {k: (v[0], v[1]) for k, v in d["bands"].items()})


def parse_ban(text: str) -> set[str]:
    out = set()
    for line in text.splitlines()[1:]:
        parts = [p.strip() for p in line.split(",")]
        if len(parts) >= 2 and parts[1]:
            out.add(parts[1].upper())
    return out


async def fetch_day_reference(http: UpstoxHttp, master: InstrumentMaster, iids: list[InstrumentId]) -> DayReference:
    ref = DayReference()
    try:
        async with httpx.AsyncClient(timeout=20, headers={"User-Agent": "Mozilla/5.0"}) as c:
            r = await c.get(BAN_URL)
            r.raise_for_status()
            ref.ban = parse_ban(r.text)
    except httpx.HTTPError as e:
        log.warning("dayref.ban_failed", error=repr(e))
    natives = {master.to_native(i): i for i in iids if master.find(i)}
    keys = list(natives)
    for k in range(0, len(keys), 450):
        try:
            d = await http.get("/v2/market-quote/quotes", params={"instrument_key": ",".join(keys[k:k + 450])})
        except Exception as e:  # noqa: BLE001
            log.warning("dayref.bands_failed", error=repr(e))
            continue
        for v in (d.get("data") or {}).values():
            iid = natives.get(v.get("instrument_token", ""))
            lo, hi = v.get("lower_circuit_limit"), v.get("upper_circuit_limit")
            if iid is not None and lo and hi:
                ref.bands[str(iid)] = (to_paise(lo), to_paise(hi))
    log.info("dayref.loaded", ban=len(ref.ban), bands=len(ref.bands))
    return ref


async def ensure_day_reference(data_dir: Path, day: date, http_factory, master: InstrumentMaster,
                               iids: list[InstrumentId]) -> DayReference:
    path = Path(data_dir) / "reference" / f"dayref-{day.isoformat()}.json"
    if path.exists():
        return DayReference.load(path)
    http = http_factory()
    try:
        ref = await fetch_day_reference(http, master, iids)
    finally:
        await http.aclose()
    ref.save(path)
    return ref
