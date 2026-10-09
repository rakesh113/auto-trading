# auto-trading
This repository contains customised bots and agents for intra day trading in stocks and futures and options

## Design

The system design (v0.2) is in [`docs/design/trading-system-design.md`](docs/design/trading-system-design.md). The research behind it is in [`docs/research/`](docs/research/).

## Status

Phase 0 (foundations and recorder) is in progress. Paper trading only; nothing places real orders.

## Setup (Windows laptop)

```powershell
python -m venv .venv
.venv\Scripts\pip install -e .[dev]
copy .env.example .env        # then fill in UPSTOX_ANALYTICS_TOKEN (and OPENROUTER_API_KEY later)
.venv\Scripts\trader check    # validates config, secrets and Upstox access
```

Recorded data, reference files, logs and reports go to `system.data_dir` (default `D:/trading-data`).
Override machine-specific settings in `config/local.yaml` (git-ignored).

## Commands

| Command | What it does |
|---|---|
| `trader check` | Validate config and secrets; reach Upstox with the analytics token |
| `trader instruments [--refresh]` | Load today's instrument master; show expiries |
| `trader record` | Daily recorder, forever: waits for each trading day, records 08:50–15:50 IST |
| `trader record-now --minutes N` | Record from now for N minutes (smoke test) |
| `trader dq [--date YYYY-MM-DD]` | Data-quality report for a recorded day |
| `trader supervise` | Run and restart the long-running services |

Start everything at logon: `powershell -ExecutionPolicy Bypass -File deploy\windows\install-tasks.ps1`.

## Paper or live: one config switch

`execution.venue` picks the trader by name. Everything else (strategies, risk, OMS) sees the same `Trader` interface.

```yaml
execution:
  venue: paper        # paper | upstox | <any registered trader>
```

Live trading is refused unless **all** hold: profile `live`, `TRADER_LIVE_ARMED=yes` set in the session, and the venue's daily access token present. See `src/trader/core/app.py`.

### Adding another broker

1. Create `src/trader/adapters/<broker>/trader.py` with a class that subclasses `trader.ports.execution.Trader`, declares its `caps`, implements `place`, `modify`, `cancel`, `snapshot` and `build`, and is decorated with `@traders.register("<broker>")`.
2. Add its module to the built-ins in `src/trader/core/registry.py`, or ship it as a separate package with an entry point in group `trader.traders`.
3. Add a harness for it in `tests/contract/test_trader_conformance.py`; it must pass the same suite as `paper` and `upstox`.
4. Set `execution.venue: <broker>` and put its settings under `execution.settings.<broker>`.

Feeds, instrument masters, notifiers and LLM providers plug in the same way (registries in `core/registry.py`).

## Layout

```
src/trader/
  domain/      instruments, market events, orders + state machine, positions (prices in paise)
  ports/       interfaces: Trader, MarketDataFeed, InstrumentMaster, Clock, RawRecorder, Notifier
  core/        config, registry, composition root (build_app), costs, calendar, universe, throttle
  adapters/    paper/ (simulated fills)  upstox/ (REST, websocket feed, protobuf, live trader)
  recorder/    bronze raw-frame recorder, daily service, data-quality report
  intel/       LLM providers (OpenRouter)
  ops/         logging, notifications, supervisor, keep-awake
  apps/cli.py  the `trader` command
config/        base.yaml, profiles/, universe.yaml, costs.yaml
tests/         unit, property (order FSM), contract (trader conformance)
deploy/        Windows Task Scheduler setup
```
