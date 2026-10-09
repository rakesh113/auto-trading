"""End-of-day paper report: Telegram summary + a self-contained HTML file (owner choice).

The HTML lists every trade per book, the vetoes by rule, the in-play list and the
day-type labels. It is written to `<data_dir>/reports/paper-<date>.html` and sent as a
Telegram document, which opens as a page on the phone.
"""

from __future__ import annotations

import html
import json
import sqlite3
from collections import Counter
from datetime import date, datetime
from pathlib import Path
from typing import Any

from trader.core.config import AppConfig
from trader.domain.types import IST


def _rows(db: Path, kind: str) -> list[tuple[int, str, dict[str, Any]]]:
    if not db.exists():
        return []
    con = sqlite3.connect(db)
    try:
        cur = con.execute("SELECT ts_ns, book, data FROM events WHERE kind=? ORDER BY seq", (kind,))
        return [(ts, b, json.loads(d)) for ts, b, d in cur]
    finally:
        con.close()


def _t(ts: int) -> str:
    return datetime.fromtimestamp(ts / 1e9, IST).strftime("%H:%M:%S")


def render_html(day: date, summary: dict[str, Any], journal: Path) -> str:
    closed = _rows(journal, "trade_closed")
    signals = _rows(journal, "signal")
    kills = _rows(journal, "kill")
    daytypes = _rows(journal, "day_type")
    e = html.escape
    parts = [f"""<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Paper report {day}</title>
<style>
:root{{--bg:#fff;--fg:#1a1a1a;--mut:#666;--line:#e3e3e3;--pos:#0a7a3d;--neg:#b42318}}
@media (prefers-color-scheme:dark){{:root{{--bg:#141414;--fg:#eee;--mut:#999;--line:#333;--pos:#4ade80;--neg:#f87171}}}}
body{{background:var(--bg);color:var(--fg);font:14px/1.45 system-ui,sans-serif;margin:0;padding:16px;max-width:1000px}}
h1{{font-size:20px}} h2{{font-size:16px;margin-top:24px}} .mut{{color:var(--mut)}}
table{{border-collapse:collapse;width:100%;font-variant-numeric:tabular-nums}} .wrap{{overflow-x:auto}}
th,td{{border-bottom:1px solid var(--line);padding:4px 8px;text-align:right;white-space:nowrap}}
th:first-child,td:first-child,td.l{{text-align:left}} .pos{{color:var(--pos)}} .neg{{color:var(--neg)}}
</style></head><body><h1>Paper trading — {day}</h1>
<p class="mut">Day type: {e(summary.get('day_type',''))} · In play: {e(', '.join(s.split(':')[2] for s in summary.get('in_play', [])))}</p>
<div class="wrap"><table><tr><th>Book</th><th>P&amp;L ₹</th><th>Trades</th><th>Wins</th><th>Avg R</th><th>Charges ₹</th><th>Equity ₹</th></tr>"""]
    for name, b in summary.get("books", {}).items():
        cls = "pos" if b["pnl"] >= 0 else "neg"
        eq = summary.get("equity", {}).get(name)
        parts.append(f"<tr><td>{name}{' (gated)' if name == 'A' else ' (baseline)'}</td><td class='{cls}'>{b['pnl']:,.0f}</td>"
                     f"<td>{b['trades']}</td><td>{b['wins']}</td><td>{b['avg_r']:+.2f}</td><td>{b['charges']:,.0f}</td>"
                     f"<td>{'' if eq is None else f'{eq:,.0f}'}</td></tr>")
    parts.append("</table></div>")
    if kills:
        parts.append("<h2>Kill events</h2><ul>" + "".join(
            f"<li>{_t(ts)} [{b}] {e(d['reason'])}</li>" for ts, b, d in kills) + "</ul>")
    parts.append("<h2>Trades</h2><div class='wrap'><table><tr><th>Book</th><th>Setup</th><th>Symbol</th><th>Side</th>"
                 "<th>Qty</th><th>Entry</th><th>Exit</th><th>Net ₹</th><th>R</th><th>Exit reason</th></tr>")
    for _ts, b, d in closed:
        cls = "pos" if d["net"] >= 0 else "neg"
        parts.append(f"<tr><td class='l'>{b}</td><td class='l'>{e(d['setup'])}</td><td class='l'>{e(d['iid'].split(':')[2])}</td>"
                     f"<td class='l'>{d['side']}</td><td>{d['qty']}</td><td>{d['entry'] / 100:,.2f}</td>"
                     f"<td>{d['exit'] / 100:,.2f}</td><td class='{cls}'>{d['net'] / 100:,.0f}</td><td>{d['r']:+.2f}</td>"
                     f"<td class='l'>{e(d['reason'])}</td></tr>")
    if not closed:
        parts.append("<tr><td colspan='10' class='l mut'>No trades.</td></tr>")
    parts.append("</table></div>")
    vetoes = Counter((b, d["rule"]) for _ts, b, d in signals if not d["approved"])
    parts.append(f"<h2>Signals</h2><p>{len(signals)} signals, {sum(1 for *_x, d in signals if d['approved'])} approved.</p>")
    if vetoes:
        parts.append("<div class='wrap'><table><tr><th>Book</th><th>Vetoed by rule</th><th>Count</th></tr>" + "".join(
            f"<tr><td class='l'>{b}</td><td class='l'>{e(r)}</td><td>{n}</td></tr>" for (b, r), n in vetoes.most_common())
            + "</table></div>")
    if daytypes:
        parts.append("<h2>Day-type labels</h2><ul>" + "".join(
            f"<li>{_t(ts)} {e(d['label'])} <span class='mut'>{e(json.dumps(d['inputs']))}</span></li>"
            for ts, _b, d in daytypes) + "</ul>")
    parts.append(f"<p class='mut'>Journal digest {e(summary.get('digest', ''))[:16]}</p></body></html>")
    return "".join(parts)


def summary_text(day: date, summary: dict[str, Any]) -> str:
    lines = [f"Paper day {day} — {summary.get('day_type', '')}"]
    for name, b in summary.get("books", {}).items():
        eq = summary.get("equity", {}).get(name)
        lines.append(f"{name}: ₹{b['pnl']:+,.0f} · {b['trades']} trades · {b['wins']} wins · avg {b['avg_r']:+.2f}R"
                     + (f" · equity ₹{eq:,.0f}" if eq is not None else "") + (" · LOCKED" if b.get("locked") else ""))
    return "\n".join(lines)


async def send_daily_report(cfg: AppConfig, day: date, summary: dict[str, Any], notifier: Any) -> Path:
    data_dir = cfg.system.data_dir
    out = data_dir / "reports" / f"paper-{day.isoformat()}.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render_html(day, summary, data_dir / "journal" / f"{day.isoformat()}.sqlite"), encoding="utf-8")
    text = summary_text(day, summary)
    await notifier.notify(text)
    send_doc = getattr(notifier, "send_document", None)
    if send_doc is not None:
        await send_doc(out, caption=f"Full paper report {day}")
    return out
