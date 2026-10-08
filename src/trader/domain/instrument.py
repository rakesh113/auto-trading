"""Canonical instrument identity (design §10).

An `InstrumentId` is a broker-neutral string, e.g.::

    NSE:EQ:RELIANCE
    NSE:IDX:NIFTY50
    NSE:FUT:NIFTY:2026-10-27
    NSE:OPT:NIFTY:2026-10-13:25000:CE
    MCX:FUT:CRUDEOILM:2026-10-19

Strategies, risk and storage only ever see these. Each venue adapter maps them to its
own native keys (Upstox `instrument_key`, Kite token) through the InstrumentMaster.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from trader.domain.types import Exchange, InstrumentKind, OptionRight, Paise


def _fmt_strike(strike: Decimal) -> str:
    s = format(strike.normalize(), "f")
    return s


@dataclass(frozen=True, slots=True, order=True)
class InstrumentId:
    exchange: Exchange
    kind: InstrumentKind
    symbol: str
    expiry: date | None = None
    strike: Decimal | None = None
    right: OptionRight | None = None

    def __post_init__(self) -> None:
        if ":" in self.symbol or not self.symbol:
            raise ValueError(f"bad symbol {self.symbol!r}")
        if self.kind in (InstrumentKind.FUT, InstrumentKind.OPT) and self.expiry is None:
            raise ValueError(f"{self.kind} needs an expiry")
        if self.kind is InstrumentKind.OPT and (self.strike is None or self.right is None):
            raise ValueError("option needs strike and right")
        if self.kind is not InstrumentKind.OPT and (self.strike is not None or self.right is not None):
            raise ValueError("only options carry strike/right")

    def __str__(self) -> str:
        parts = [self.exchange.value, self.kind.value, self.symbol]
        if self.expiry is not None:
            parts.append(self.expiry.isoformat())
        if self.strike is not None:
            parts.append(_fmt_strike(self.strike))
        if self.right is not None:
            parts.append(self.right.value)
        return ":".join(parts)

    @classmethod
    def parse(cls, s: str) -> InstrumentId:
        p = s.split(":")
        if len(p) < 3:
            raise ValueError(f"bad instrument id {s!r}")
        exch, kind, sym = Exchange(p[0]), InstrumentKind(p[1]), p[2]
        if kind in (InstrumentKind.EQ, InstrumentKind.IDX):
            if len(p) != 3:
                raise ValueError(f"bad instrument id {s!r}")
            return cls(exch, kind, sym)
        if kind is InstrumentKind.FUT:
            if len(p) != 4:
                raise ValueError(f"bad instrument id {s!r}")
            return cls(exch, kind, sym, date.fromisoformat(p[3]))
        if len(p) != 6:
            raise ValueError(f"bad instrument id {s!r}")
        return cls(exch, kind, sym, date.fromisoformat(p[3]), Decimal(p[4]), OptionRight(p[5]))

    @property
    def is_derivative(self) -> bool:
        return self.kind in (InstrumentKind.FUT, InstrumentKind.OPT)


@dataclass(frozen=True, slots=True)
class Instrument:
    """Point-in-time reference data for one tradable (or index) instrument."""

    id: InstrumentId
    name: str
    tick_size: Paise
    lot_size: int
    freeze_qty: int | None = None
    isin: str | None = None
    series: str | None = None  # NSE equity series (EQ, BE, ...)
    underlying: str | None = None  # canonical id string of the underlying, if any
    cas_eligible: bool = False  # closing-auction-session stock (design §4)
    qty_multiplier: Decimal = Decimal(1)  # MCX: rupee P&L per 1-point move per unit of qty
    weekly: bool | None = None
    native: dict[str, str] = field(default_factory=dict, compare=False)  # venue -> native key

    def native_key(self, venue: str) -> str:
        try:
            return self.native[venue]
        except KeyError:
            raise KeyError(f"{self.id} has no {venue} mapping") from None
