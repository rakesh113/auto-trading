"""Data-quality report for one recorded day (design §11, Phase 0 exit criteria).

Checks: depth levels actually received in full_d30 (some accounts get only 5),
crossed books, feed lag (our receive time − Upstox server time), silent gaps during
market hours, reconnects and decode errors.
"""

from __future__ import annotations

import statistics
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, datetime, time
from pathlib import Path
from typing import Any

from trader.adapters.upstox.decode import decode_frame
from trader.adapters.upstox.feed import KIND_FRAME, KIND_STATE
from trader.domain.market import Quote
from trader.domain.types import IST, FeedMode
from trader.recorder.bronze import read_frames

MARKET_OPEN = time(9, 15)
MARKET_CLOSE = time(15, 30)
GAP_S = 5.0


def _pct(xs: list[float], p: float) -> float | None:
    if not xs:
        return None
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(p / 100 * len(xs)))]


@dataclass
class StreamStats:
    frames: int = 0
    quotes: int = 0
    decode_errors: int = 0
    keys: set[str] = field(default_factory=set)
    modes: Counter[str] = field(default_factory=Counter)
    d30_levels: Counter[int] = field(default_factory=Counter)
    crossed: int = 0
    lag_ms: list[float] = field(default_factory=list)
    gaps: list[tuple[str, float]] = field(default_factory=list)
    states: list[str] = field(default_factory=list)
    per_minute: Counter[str] = field(default_factory=Counter)


def analyze_day(data_dir: Path, day: date) -> dict[str, Any]:
    root = Path(data_dir) / "bronze" / day.isoformat()
    if not root.exists():
        raise FileNotFoundError(root)
    o = datetime.combine(day, MARKET_OPEN, IST).timestamp() * 1e9
    c = datetime.combine(day, MARKET_CLOSE, IST).timestamp() * 1e9
    report: dict[str, Any] = {"date": day.isoformat(), "streams": {}}
    for sdir in sorted(p for p in root.iterdir() if p.is_dir()):
        st = StreamStats()
        last_ts: int | None = None
        for f in sorted(sdir.glob("*.frames.zst")):
            for ts, kind, payload in read_frames(f):
                if kind == KIND_STATE:
                    st.states.append(f"{datetime.fromtimestamp(ts / 1e9, IST):%H:%M:%S} {payload.decode()}")
                    continue
                if kind != KIND_FRAME:
                    continue
                st.frames += 1
                if last_ts is not None and o <= ts <= c and (ts - last_ts) / 1e9 > GAP_S:
                    st.gaps.append((f"{datetime.fromtimestamp(last_ts / 1e9, IST):%H:%M:%S}", (ts - last_ts) / 1e9))
                last_ts = ts
                st.per_minute[f"{datetime.fromtimestamp(ts / 1e9, IST):%H:%M}"] += 1
                try:
                    events = decode_frame(payload, ts, lambda _k: None)
                except Exception:  # noqa: BLE001
                    st.decode_errors += 1
                    continue
                for ev in events:
                    if not isinstance(ev, Quote):
                        continue
                    st.quotes += 1
                    st.keys.add(ev.native)
                    st.modes[ev.mode.value] += 1
                    if ev.ts_server_ms:
                        st.lag_ms.append(ts / 1e6 - ev.ts_server_ms)
                    if ev.mode is FeedMode.FULL_D30 and not ev.snapshot:
                        st.d30_levels[max(len(ev.bids), len(ev.asks))] += 1
                    if ev.bids and ev.asks and ev.bids[0].price >= ev.asks[0].price:
                        st.crossed += 1
        lag = [x for x in st.lag_ms if -60_000 < x < 60_000]
        report["streams"][sdir.name] = {
            "frames": st.frames, "quotes": st.quotes, "unique_keys": len(st.keys), "modes": dict(st.modes),
            "decode_errors": st.decode_errors, "crossed_books": st.crossed,
            "d30_levels_hist": dict(sorted(st.d30_levels.items())),
            "lag_ms": {"p50": _pct(lag, 50), "p95": _pct(lag, 95), "p99": _pct(lag, 99),
                       "mean": statistics.fmean(lag) if lag else None},
            "gaps_over_5s_in_market": len(st.gaps), "worst_gaps": sorted(st.gaps, key=lambda g: -g[1])[:5],
            "peak_frames_per_min": max(st.per_minute.values()) if st.per_minute else 0,
            "states": st.states[-20:],
        }
    return report


def _fmt(v: Any) -> str:
    return f"{v:.0f}" if isinstance(v, float) else str(v)


def render(report: dict[str, Any]) -> str:
    lines = [f"Data-quality report {report['date']}", ""]
    defects = 0
    for name, s in report["streams"].items():
        lag = s["lag_ms"]
        lines.append(f"[{name}] frames={s['frames']} quotes={s['quotes']} keys={s['unique_keys']} "
                     f"peak/min={s['peak_frames_per_min']}")
        lines.append(f"  lag ms p50/p95/p99 = {_fmt(lag['p50'])}/{_fmt(lag['p95'])}/{_fmt(lag['p99'])}")
        lines.append(f"  decode_errors={s['decode_errors']} crossed={s['crossed_books']} "
                     f"gaps>5s={s['gaps_over_5s_in_market']} {s['worst_gaps'][:3]}")
        if s["d30_levels_hist"]:
            hist = s["d30_levels_hist"]
            full = sum(v for k, v in hist.items() if k >= 30)
            total = sum(hist.values())
            lines.append(f"  d30 depth: {full}/{total} snapshots had 30 levels; histogram {hist}")
            if total and full / total < 0.5:
                lines.append("  !! depth-30 is NOT arriving as 30 levels; check the Plus plan on the token")
                defects += 1
        defects += s["decode_errors"] > 0
        if s["states"]:
            lines.append(f"  connection events: {s['states'][-5:]}")
        lines.append("")
    lines.append("CLEAN" if defects == 0 else f"{defects} defect(s)")
    return "\n".join(lines)

