"""Transaction cost model driven by config/costs.yaml (design §5).

Used by the paper trader to charge fills, by risk for the friction gate, and later to
reconcile against contract notes.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

import yaml

from trader.domain.instrument import InstrumentId
from trader.domain.types import Exchange, InstrumentKind, Paise, Product, Side


@dataclass(frozen=True, slots=True)
class Charges:
    brokerage: float = 0.0
    stt: float = 0.0
    exchange_txn: float = 0.0
    sebi: float = 0.0
    stamp: float = 0.0
    gst: float = 0.0

    @property
    def total(self) -> Paise:
        return round(self.brokerage + self.stt + self.exchange_txn + self.sebi + self.stamp + self.gst)


def category(iid: InstrumentId, product: Product) -> str:
    if iid.exchange is Exchange.MCX:
        return "commodity_options" if iid.kind is InstrumentKind.OPT else "commodity_futures"
    if iid.kind is InstrumentKind.FUT:
        return "futures"
    if iid.kind is InstrumentKind.OPT:
        return "options"
    return "equity_delivery" if product is Product.DELIVERY else "equity_intraday"


def _txn_key(cat: str) -> str:
    return {"equity_intraday": "equity", "equity_delivery": "equity"}.get(cat, cat.removeprefix("commodity_"))


class CostModel:
    def __init__(self, schedules: list[dict[str, Any]], brokerage: dict[str, Any]) -> None:
        self._schedules = sorted(schedules, key=lambda s: s["effective_from"])
        self._brokerage = brokerage

    @classmethod
    def load(cls, path: Path, profile: str) -> CostModel:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        profiles = raw["brokerage_profiles"]
        if profile not in profiles:
            raise KeyError(f"unknown cost profile {profile!r}; known: {sorted(profiles)}")
        return cls(raw["schedules"], profiles[profile])

    def _schedule(self, day: date) -> dict[str, Any]:
        chosen = None
        for s in self._schedules:
            eff = s["effective_from"]
            eff = eff if isinstance(eff, date) else date.fromisoformat(str(eff))
            if eff <= day:
                chosen = s
        if chosen is None:
            raise LookupError(f"no cost schedule in effect on {day}")
        return chosen

    def brokerage(self, cat: str, order_turnover: float) -> float:
        """Brokerage for one executed order of `order_turnover` paise."""
        rule = self._brokerage.get(cat, {})
        fee = float(rule.get("flat_paise", 0))
        if "pct" in rule:
            fee = min(fee, order_turnover * rule["pct"] / 100)
        return fee

    def statutory(
        self, iid: InstrumentId, side: Side, qty: int, price: Paise, product: Product, day: date,
        multiplier: float = 1.0,
    ) -> Charges:
        """All charges except brokerage and the GST on brokerage."""
        s = self._schedule(day)
        cat = category(iid, product)
        turnover = qty * price * multiplier
        side_key = "buy" if side is Side.BUY else "sell"
        stt = turnover * s["stt"].get(cat, {}).get(side_key, 0.0) / 100
        txn = turnover * s["exchange_txn"].get(iid.exchange.value, {}).get(_txn_key(cat), 0.0) / 100
        sebi = turnover * s["sebi_fee"] / 100
        stamp = turnover * s["stamp_duty"].get(cat, 0.0) / 100 if side is Side.BUY else 0.0
        gst = (txn + sebi) * s["gst"] / 100
        return Charges(stt=stt, exchange_txn=txn, sebi=sebi, stamp=stamp, gst=gst)

    def gst_rate(self, day: date) -> float:
        return float(self._schedule(day)["gst"])

    def round_trip_bps(self, iid: InstrumentId, price: Paise, qty: int, product: Product, day: date) -> float:
        """Statutory + brokerage for buy and sell of the same size, in bps of notional."""
        cat = category(iid, product)
        notional = qty * price
        total = 0.0
        for side in (Side.BUY, Side.SELL):
            c = self.statutory(iid, side, qty, price, product, day)
            b = self.brokerage(cat, notional)
            total += c.total + b * (1 + self.gst_rate(day) / 100)
        return total / notional * 1e4
