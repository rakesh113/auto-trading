"""Pre-trade risk: sizing, friction gate and the hard limits (design §5, §6).

`RiskEngine.evaluate()` is pure: given a signal, the symbol's state and the book's
status, it returns an approved quantity or the first rule that vetoes it. It never
places orders. The OMS asks it before every entry, and the session monitor uses
`should_flatten()` on every quote for the daily-loss and profit-protection kills.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict

from trader.core.costs import CostModel, category
from trader.domain.instrument import InstrumentId
from trader.domain.types import Product, Side, to_paise
from trader.market.state import SymbolState
from trader.strategies.base import Signal


class RiskConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    equity_inr: float
    r_pct: float
    dll_pct: float
    day_ceiling_pct: float
    invariant_frac: float
    soft_warning_frac: float
    open_risk_pct: float
    max_positions: int
    max_same_direction: int
    max_per_sector: int
    symbol_notional_x: float
    gross_x_normal: float
    gross_x_hard: float
    free_margin_frac: float
    intraday_margin_pct: float
    equity_module_frac: float
    friction_max_r: float
    slippage_bps: float
    min_net_rr: float
    stop_floor_pct: float
    stop_floor_atr: float
    last_entry: str
    flatten_cas: str
    flatten_other: str
    streak_losses_cooloff: int
    cooloff_min: int
    max_losers_per_day: int
    profit_protect_start_inr: float
    profit_protect_floor: float
    weekly_stop_pct: float
    monthly_stop_pct: float
    drawdown_ladder: list[tuple[float, float]]
    drawdown_stop_pct: float
    stop_attach_s: float
    stale_feed_s: float
    band_buffer_pct: float = 1.0

    @classmethod
    def load(cls, path: Path) -> RiskConfig:
        return cls(**yaml.safe_load(path.read_text(encoding="utf-8")))

    @staticmethod
    def minute(hhmm: str) -> int:
        h, m = hhmm.split(":")
        return int(h) * 60 + int(m) - (9 * 60 + 15)


@dataclass
class OpenPosition:
    iid: InstrumentId
    side: Side
    qty: int
    entry: int
    stop: int
    ltp: int
    sector: str = ""

    @property
    def open_risk(self) -> int:
        """Further loss if the stop is hit; 0 once the stop is in profit."""
        r = (self.ltp - self.stop) * self.side.sign * self.qty
        return max(r, 0)

    @property
    def notional(self) -> int:
        return self.qty * self.ltp


@dataclass
class BookStatus:
    equity: int  # paise, start-of-day equity
    hwm: int  # high-water mark of end-of-day equity
    realized: int = 0  # today, net of charges
    unrealized: int = 0
    positions: list[OpenPosition] = field(default_factory=list)
    trades_today: int = 0
    losers_today: int = 0
    consecutive_losses: int = 0
    cooloff_until_ns: int = 0
    reduced_trades_left: int = 0
    peak_pnl: int = 0
    week_pnl: int = 0  # before today
    month_pnl: int = 0
    locked: bool = False
    paused: bool = False
    equity_module_loss: int = 0

    @property
    def day_pnl(self) -> int:
        return self.realized + self.unrealized


@dataclass(frozen=True)
class Decision:
    approved: bool
    qty: int = 0
    rule: str = ""
    detail: str = ""
    friction_r: float = 0.0
    size_mult: float = 1.0
    risk_inr: float = 0.0

    @classmethod
    def veto(cls, rule: str, detail: str = "", **kw: Any) -> Decision:
        return cls(False, rule=rule, detail=detail, **kw)


class RiskEngine:
    def __init__(self, cfg: RiskConfig, costs: CostModel, *, sectors: dict[str, str] | None = None) -> None:
        self.cfg = cfg
        self.costs = costs
        self.sectors = sectors or {}

    # ---- limits that scale with the day -------------------------------------------------

    def dll(self, b: BookStatus) -> int:
        return round(b.equity * self.cfg.dll_pct / 100)

    def size_multiplier(self, b: BookStatus, now_ns: int) -> tuple[float, str]:
        mult, why = 1.0, []
        dd = (b.hwm - b.equity) / b.hwm * 100 if b.hwm else 0.0
        for threshold, m in self.cfg.drawdown_ladder:
            if dd >= threshold:
                mult, why = m, [f"drawdown {dd:.1f}%"]
        if -b.day_pnl >= self.cfg.soft_warning_frac * self.dll(b):
            mult = min(mult, 0.5)
            why.append("soft warning")
        if b.reduced_trades_left > 0:
            mult = min(mult, 0.5)
            why.append("after losing streak")
        return mult, ", ".join(why)

    # ---- the decision -------------------------------------------------------------------

    def evaluate(self, sig: Signal, st: SymbolState, b: BookStatus, *, now_ns: int, minute: int,
                 shortable: bool, day: date, gate_reason: str = "", banned: bool = False,
                 band: tuple[int, int] | None = None) -> Decision:
        c = self.cfg
        dll = self.dll(b)
        if gate_reason:
            return Decision.veto("gate", gate_reason)
        if b.locked:
            return Decision.veto("locked", "day locked")
        if b.paused:
            return Decision.veto("paused", "entries paused")
        if minute >= c.minute(c.last_entry):
            return Decision.veto("time", f"no entries after {c.last_entry}")
        if (b.hwm - b.equity) / b.hwm * 100 >= c.drawdown_stop_pct:
            return Decision.veto("drawdown_stop", "maximum drawdown reached")
        if -b.week_pnl >= b.equity * c.weekly_stop_pct / 100:
            return Decision.veto("weekly_stop", "weekly loss limit")
        if -b.month_pnl >= b.equity * c.monthly_stop_pct / 100:
            return Decision.veto("monthly_stop", "monthly loss limit")
        if b.losers_today >= c.max_losers_per_day:
            return Decision.veto("losers", f"{b.losers_today} losing trades today")
        if now_ns < b.cooloff_until_ns:
            return Decision.veto("cooloff", "cool-off after losing streak")
        if sig.side is Side.SELL and not shortable:
            return Decision.veto("short_not_allowed", "shorts only in F&O stocks")
        if sig.side is Side.SELL and banned:
            return Decision.veto("fno_ban", "F&O ban: cash longs only")
        if band is not None and (sig.entry >= band[1] * (1 - c.band_buffer_pct / 100)
                                 or sig.entry <= band[0] * (1 + c.band_buffer_pct / 100)):
            return Decision.veto("price_band", f"within {c.band_buffer_pct}% of a price band {band}")
        if now_ns - st.last_ts > c.stale_feed_s * 1e9:
            return Decision.veto("stale", "symbol data stale")
        if b.equity_module_loss >= c.equity_module_frac * dll:
            return Decision.veto("module_cap", "equity module daily cap used")
        if any(p.iid == sig.iid for p in b.positions):
            return Decision.veto("duplicate", "already positioned in symbol")

        price = sig.entry
        dist = sig.risk_per_share
        spread = (st.ask - st.bid) if st.ask > st.bid else st.tick
        floor = max(price * c.stop_floor_pct / 100, c.stop_floor_atr * st.atr, 3 * spread + 2 * st.tick)
        if dist < floor:
            return Decision.veto("stop_floor", f"stop {dist / 100:.2f} < floor {floor / 100:.2f}")

        mult, why = self.size_multiplier(b, now_ns)
        if banned:
            mult = min(mult, 0.5)
            why = ", ".join(x for x in (why, "F&O ban") if x)
        r_paise = b.equity * c.r_pct / 100 * mult
        # costs per share: statutory + brokerage for a round trip at this price, plus spread and slippage
        qty0 = max(int(r_paise // dist), 1)
        fric_total = self._round_trip_cost(sig.iid, price, qty0, day) + qty0 * (spread + 2 * price * c.slippage_bps / 1e4)
        per_share_fric = fric_total / qty0
        qty = int(r_paise // (dist + per_share_fric))
        caps = {
            "symbol_notional": int(b.equity * c.symbol_notional_x // price),
            "gross": int((b.equity * c.gross_x_normal - sum(p.notional for p in b.positions)) // price),
        }
        used_margin = sum(p.notional for p in b.positions) * c.intraday_margin_pct / 100
        free = b.equity + b.day_pnl - used_margin - b.equity * c.free_margin_frac
        caps["margin"] = int(free // (price * c.intraday_margin_pct / 100)) if free > 0 else 0
        binding = min(caps, key=lambda k: caps[k])
        if caps[binding] < qty:
            qty = caps[binding]
        if qty <= 0:
            return Decision.veto("size", f"zero quantity ({binding} cap)")
        risk = qty * dist
        fric = self._round_trip_cost(sig.iid, price, qty, day) + qty * (spread + 2 * price * c.slippage_bps / 1e4)
        friction_r = fric / risk
        if friction_r > c.friction_max_r:
            return Decision.veto("friction", f"friction {friction_r:.2f}R > {c.friction_max_r}R", friction_r=friction_r)
        blend = sum(t.fraction * sig.r_multiple(t.price) for t in sig.targets)
        need = c.min_net_rr + 2.5 * friction_r
        if blend < need:
            return Decision.veto("reward_risk", f"blended target {blend:.2f}R < {need:.2f}R", friction_r=friction_r)

        new_risk = risk + fric
        open_risk = sum(p.open_risk for p in b.positions)
        if b.day_pnl - open_risk - new_risk < -c.invariant_frac * dll:
            return Decision.veto("invariant", f"open-risk invariant: pnl {b.day_pnl / 100:.0f}, open "
                                 f"{open_risk / 100:.0f}, new {new_risk / 100:.0f}", friction_r=friction_r)
        if open_risk + risk > b.equity * c.open_risk_pct / 100:
            return Decision.veto("open_risk", "total open risk cap", friction_r=friction_r)
        if len(b.positions) >= c.max_positions:
            return Decision.veto("positions", "max concurrent positions", friction_r=friction_r)
        if sum(1 for p in b.positions if p.side is sig.side) >= c.max_same_direction:
            return Decision.veto("direction", "max positions in one direction", friction_r=friction_r)
        sector = self.sectors.get(sig.iid.symbol, "")
        if sector and sum(1 for p in b.positions if p.sector == sector) >= c.max_per_sector:
            return Decision.veto("sector", f"max positions in {sector}", friction_r=friction_r)
        if b.peak_pnl >= to_paise(c.profit_protect_start_inr) and \
                b.day_pnl - new_risk < c.profit_protect_floor * b.peak_pnl:
            return Decision.veto("profit_protect", "would risk giving back protected profit", friction_r=friction_r)
        return Decision(True, qty=qty, rule=binding if caps[binding] == qty else "",
                        detail=why, friction_r=friction_r, size_mult=mult, risk_inr=risk / 100)

    def _round_trip_cost(self, iid: InstrumentId, price: int, qty: int, day: date) -> float:
        cat = category(iid, Product.INTRADAY)
        total = 0.0
        for side in (Side.BUY, Side.SELL):
            total += self.costs.statutory(iid, side, qty, price, Product.INTRADAY, day).total
            total += self.costs.brokerage(cat, qty * price) * (1 + self.costs.gst_rate(day) / 100)
        return total

    # ---- kills --------------------------------------------------------------------------

    def should_flatten(self, b: BookStatus) -> str:
        """Non-empty reason when everything must be flattened now."""
        if b.day_pnl <= -self.dll(b):
            return f"daily loss limit hit ({b.day_pnl / 100:,.0f})"
        if b.peak_pnl >= to_paise(self.cfg.profit_protect_start_inr) and b.day_pnl <= self.cfg.profit_protect_floor * b.peak_pnl:
            return f"profit protection: P&L {b.day_pnl / 100:,.0f} ≤ 50% of peak {b.peak_pnl / 100:,.0f}"
        return ""
