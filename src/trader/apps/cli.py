"""Command line: `trader <command>` (or `python -m trader.apps.cli <command>`).

  check         validate config and secrets, reach Upstox with the analytics token
  instruments   download/load today's master and print a summary
  record        run the daily recorder forever (what the supervisor runs)
  record-now    record from now for N minutes (smoke test; works outside hours too)
  dq            data-quality report for a recorded day
  eod           end-of-day: silver Parquet + quality verdict + raw-file retention + backup
  supervise     start and babysit the long-running services
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections import Counter
from datetime import date, timedelta

from trader.core.config import load_config, secret


def _cfg(args: argparse.Namespace):
    from trader.ops.logging import setup_logging

    cfg = load_config(args.profile)
    setup_logging(cfg.system.log_level, cfg.system.data_dir / "logs", name=args.cmd)
    return cfg


async def _check(args: argparse.Namespace) -> int:
    from trader.adapters.upstox.http import UpstoxHttp
    from trader.core.app import LiveTradingBlocked, check_live_guard
    from trader.core.registry import traders

    cfg = _cfg(args)
    print(f"profile={cfg.profile} venue={cfg.execution.venue} data_dir={cfg.system.data_dir}")
    ok = True
    try:
        check_live_guard(cfg, traders.get(cfg.execution.venue))
        print("live guard: ok")
    except LiveTradingBlocked as e:
        print(f"live guard: BLOCKED ({e})")
        ok = cfg.profile != "live"
    for env in (cfg.upstox.analytics_token_env, cfg.llm.api_key_env):
        try:
            secret(env)
            print(f"secret {env}: present")
        except Exception as e:  # noqa: BLE001
            print(f"secret {env}: MISSING ({e})")
            ok = ok and env != cfg.upstox.analytics_token_env
    http = UpstoxHttp(secret(cfg.upstox.analytics_token_env), api_base=cfg.upstox.api_base)
    try:
        body = await http.get("/v3/feed/market-data-feed/authorize")
        print("upstox feed authorize:", "ok" if body.get("data") else body)
        body = await http.get("/v2/market/status/NSE")
        print("upstox market status:", (body.get("data") or {}).get("status"))
    except Exception as e:  # noqa: BLE001
        print("upstox:", e)
        ok = False
    finally:
        await http.aclose()
    import httpx

    async with httpx.AsyncClient(timeout=15) as c:
        try:
            r = await c.get(f"{cfg.llm.base_url}/key", headers={"Authorization": f"Bearer {secret(cfg.llm.api_key_env)}"})
            d = r.json().get("data", {})
            print(f"openrouter key: HTTP {r.status_code}, limit_remaining=${d.get('limit_remaining')}")
        except Exception as e:  # noqa: BLE001
            print("openrouter key:", e)
        if cfg.notifier.provider == "telegram":
            try:
                r = await c.get(f"https://api.telegram.org/bot{secret('TELEGRAM_BOT_TOKEN')}/getMe")
                print("telegram bot:", r.json().get("result", {}).get("username") if r.json().get("ok") else r.text)
            except Exception as e:  # noqa: BLE001
                print("telegram:", e)
                ok = False
    cfg.system.data_dir.mkdir(parents=True, exist_ok=True)
    print("data_dir writable: ok")
    return 0 if ok else 1


async def _instruments(args: argparse.Namespace) -> int:
    from trader.core.app import build_app
    from trader.core.clock import WallClock
    from trader.ports.clock import today_ist

    cfg = _cfg(args)
    app = build_app(cfg, with_feed=False, with_trader=False)
    day = today_ist(WallClock())
    n = await app.master.load(day, refresh=args.refresh)
    kinds = Counter(f"{i.id.exchange}:{i.id.kind}" for i in app.master.all())
    print(f"{n} instruments for {day}: {dict(sorted(kinds.items()))}")
    for sym, exch in (("NIFTY", "NSE"), ("SENSEX", "BSE"), ("BANKNIFTY", "NSE")):
        from trader.domain.types import Exchange, InstrumentKind

        exps = app.master.expiries(sym, InstrumentKind.OPT, Exchange(exch), on_or_after=day)  # type: ignore[attr-defined]
        print(f"  {sym} option expiries: {[e.isoformat() for e in exps[:4]]}")
    return 0


async def _record(args: argparse.Namespace) -> int:
    from trader.recorder.service import run_forever

    await run_forever(_cfg(args))
    return 0


async def _record_now(args: argparse.Namespace) -> int:
    from trader.core.clock import WallClock
    from trader.ports.clock import now_ist
    from trader.recorder.service import record_day

    cfg = _cfg(args)
    until = now_ist(WallClock()) + timedelta(minutes=args.minutes)
    summary = await record_day(cfg, until=until)
    print(json.dumps({k: (v[:20] if isinstance(v, list) else v) for k, v in summary.items()}, indent=1))
    return 0


async def _dq(args: argparse.Namespace) -> int:
    from trader.core.clock import WallClock
    from trader.ports.clock import today_ist
    from trader.recorder.dq import analyze_day, render

    cfg = _cfg(args)
    day = date.fromisoformat(args.date) if args.date else today_ist(WallClock())
    rep = analyze_day(cfg.system.data_dir, day)
    out = cfg.system.data_dir / "reports" / f"dq-{day.isoformat()}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(rep, indent=1, default=str), encoding="utf-8")
    print(render(rep))
    print(f"\nfull report: {out}")
    return 0


async def _eod(args: argparse.Namespace) -> int:
    from trader.core.clock import WallClock
    from trader.ports.clock import today_ist
    from trader.recorder.service import end_of_day

    cfg = _cfg(args)
    day = date.fromisoformat(args.date) if args.date else today_ist(WallClock())
    print(await asyncio.to_thread(end_of_day, cfg, day))
    return 0


def _supervise(args: argparse.Namespace) -> int:
    from trader.ops.supervisor import supervise

    _cfg(args)
    prof = ["--profile", args.profile] if args.profile else []
    supervise({"recorder": [*prof, "record"]})
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="trader")
    p.add_argument("--profile", default=None, help="replay | paper | shadow | live (default: config)")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("check")
    s = sub.add_parser("instruments")
    s.add_argument("--refresh", action="store_true")
    sub.add_parser("record")
    s = sub.add_parser("record-now")
    s.add_argument("--minutes", type=float, default=2.0)
    s = sub.add_parser("dq")
    s.add_argument("--date", default=None)
    s = sub.add_parser("eod")
    s.add_argument("--date", default=None)
    sub.add_parser("supervise")
    args = p.parse_args(argv)
    if args.cmd == "supervise":
        return _supervise(args)
    fn = {"check": _check, "instruments": _instruments, "record": _record, "record-now": _record_now,
          "dq": _dq, "eod": _eod}[args.cmd]
    return asyncio.run(fn(args))


if __name__ == "__main__":
    sys.exit(main())
