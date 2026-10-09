# auto-trading
This repository contains customised bots and agents for intra day trading in stocks and futures and options

## Design

The system design (v0.2) is in [`docs/design/trading-system-design.md`](docs/design/trading-system-design.md). The research behind it is in [`docs/research/`](docs/research/).

## Status

Phase 0 (foundations and recorder) is complete. Phase 1 (unattended paper trading) is running. Paper only: nothing places real orders.

Every trading day the laptop runs three services:

| Service | What it does |
|---|---|
| `record` | Records the Upstox feed (4 sockets), re-broadcasts raw frames on 127.0.0.1, converts the day to Parquet after the close |
| `paper` | The trading engine: in-play selection, day type, setups E1/E2, risk, order manager, paper fills; books **A** (day-type gated) and **B** (baseline) |
| `intel` | NSE/BSE filings, the triage bake-off (Jev 1.13 vs Claude Haiku 5.5, in shadow) and the pre-market brief (Opus 5.5, in shadow) |

Telegram receives: start messages, the 08:35 brief, the in-play list at 09:30, every paper entry and exit (book A), kill events, and the end-of-day report (summary plus an HTML file).
Phone commands (PIN in `.env` as `TELEGRAM_COMMAND_PIN`): `/status`, `/pause <PIN>`, `/flatten <PIN>`. They can only tighten; there is no resume from the phone.

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
| `trader eod [--date YYYY-MM-DD]` | Silver Parquet + quality verdict + raw-file retention + backup (runs automatically after each session) |
| `trader paper` | Paper trading every trading day (what the supervisor runs) |
| `trader intel` | Filings, triage bake-off and pre-market brief (what the supervisor runs) |
| `trader replay --date YYYY-MM-DD` | Re-run a recorded day through the same engine; prints the journal digest |
| `trader supervise` | Run and restart the long-running services (record, paper, intel) |

### Running it unattended

The supervisor runs from a separate **runtime copy** of `main` (`..\auto-trading-run`), so work on development branches never touches what is recording or trading. After merging to `main`, deploy outside market hours:

```powershell
powershell -ExecutionPolicy Bypass -File deploy\windows\deploy-runtime.ps1 -Restart
```

This updates the runtime copy, registers the logon task, and restarts the services. Telegram receives start, feed-down, recovery and end-of-day messages (with the data-quality verdict).

### Data on disk

| Tier | Where | Kept | Size |
|---|---|---|---|
| Raw frames (bronze) | `data_dir/bronze/<date>/` | `recorder.bronze_retention_days` (30) | ~0.85 GB per day |
| Parquet (silver) | `data_dir/silver/<date>/` | indefinitely | ~0.5 GB per day |
| Reports, reference | `data_dir/reports`, `data_dir/reference` | indefinitely | small |

Set `recorder.backup_dir` in `config/local.yaml` to copy silver, reference and reports to another drive after each session. You get an alert when free space drops below `recorder.min_free_gb`.

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
  recorder/    bronze raw-frame recorder, local broadcast, daily service, silver Parquet, data quality
  market/      symbol state and bars, history/context, in-play selection, day type, ban list and bands
  strategies/  setup state machines (E1 opening-range retest, E2 VWAP reclaim)
  risk/        sizing, friction gate, hard limits, kills (config/risk.yaml)
  oms/         order and position manager, SQLite journal
  engine/      session engine with books A/B, live and replay runners
  reports/     end-of-day paper report
  intel/       OpenRouter chat, Jev decisions, filings, triage bake-off, pre-market brief
  ops/         logging, notifications, supervisor, keep-awake
  apps/cli.py  the `trader` command
config/        base.yaml, profiles/, universe.yaml, costs.yaml, risk.yaml
tests/         unit, property (order FSM), contract (trader conformance), engine determinism
deploy/        Windows Task Scheduler setup
```
