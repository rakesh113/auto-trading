# Architecture Report: Modular AI-Assisted Intraday/Scalping System for Indian Markets

*Role: principal architect for the trading system. Date: 2026-10-08. Design only, no code written.*

---

## 0. Verified facts that constrain the architecture

| # | Fact | Confidence | Source |
|---|---|---|---|
| F1 | Upstox Market Data Feed V3 is binary protobuf. Modes: `ltpc`, `option_greeks`, `full` (5-level), `full_d30` (30-level). On Plus, `full_d30` is capped at **50 instrument keys**, with a combined cap of about 1,500 and up to 5 connections per user. The Basic plan has 2 connections and no D30. | medium | [Upstox V3 feed doc](https://upstox.com/developer/api-documentation/v3/get-market-data-feed), [community: D30 50-limit](https://community.upstox.com/t/market-depth-30-increase-limit-for-more-than-50-instruments/13398) |
| F2 | Broker feeds push snapshots when something changes. They are **not exchange tick-by-tick**. Kite sends about ≤1 tick/s per instrument (sometimes 2). One user measured about 3 msgs/s on Nifty from Upstox. | medium | [Kite forum](https://kite.trade/forum/discussion/998/are-the-3-different-modes-in-websockets-triggered-at-different-frequencies), [Upstox community](https://community.upstox.com/t/clarification-needed-does-upstox-api-provide-raw-exchange-tick-by-tick-every-trade-order-event-or-aggregated-data/13150) |
| F3 | The SEBI retail algo framework has applied in full since **1 Apr 2026**. Static IP is mandatory for **order endpoints only** (primary plus backup, changeable once a week). Data and portfolio APIs work from any IP. Up to **10 orders/sec per exchange-segment** needs no registration, and brokers reject anything above it. | high (framework/date), medium (details) | [SEBI 30-Sep-2025 circular](https://www.sebi.gov.in/sebi_data/attachdocs/sep-2025/1759232056254.pdf), [Zerodha static IP](https://support.zerodha.com/category/trading-and-markets/general-kite/kite-api/articles/static-ip), [Zerodha Z-Connect](https://zerodha.com/z-connect/general/a-comprehensive-overview-of-nses-circular-on-the-new-retail-algo-trading-framework) |
| F4 | NSE treats **every client API order as an algo order**, tagged with a generic algo ID when under 10 OPS. One source says OPS may count modifies and cancels, not just new orders. | medium | [NSE Retail Algo FAQ](https://nsearchives.nseindia.com/web/sites/default/files/inline-files/FAQ_Retail_Algo_03112025_NSE.pdf) |
| F5 | Plain market and SL-M orders over API need `market_protection`; a value of 0 is rejected. On Kite, `-1` means automatic and `0–100` is a percentage. | medium | [Kite forum](https://kite.trade/forum/discussion/comment/51267), [Upstox Apr-2026 notice](https://community.upstox.com/t/important-new-sebi-exchange-mandates-for-api-trading-effective-1st-april-2026/14822) |
| F6 | Upstox allows **one active API app per user** from 1 Apr 2026. Staff say generating a new access token **expires the previous token**. | medium | [Upstox notice](https://community.upstox.com/t/important-new-sebi-exchange-mandates-for-api-trading-effective-1st-april-2026/14822), [earlier notice](https://community.upstox.com/t/important-api-apps-regulatory-update/11307) |
| F7 | Upstox tokens expire at **03:30 IST the next day** and there are no refresh tokens. The "Access Token Request" flow needs human approval (in-app or WhatsApp) and then sends the token to a notifier webhook. Upstox discourages automating login. | medium-high | [Access Token Request](https://upstox.com/developer/api-documentation/access-token-request), [community](https://community.upstox.com/t/access-token-validity/4646) |
| F8 | Kite limits: 10 orders/s, 400/min, 5,000/day, applied per account; HTTP 429 above that. WebSocket allows 3 connections × 3,000 tokens with **5-level depth only**. Connect costs ₹500/month with data; the free "Personal" tier has no market data. | medium | [Kite forum: rate limits](https://kite.trade/forum/discussion/16203/non-deterministic-and-inconsistent-rate-limit-of-10-orders-sec), [Zerodha charges](https://support.zerodha.com/category/trading-and-markets/general-kite/kite-api/articles/what-are-the-charges-for-kite-apis) |
| F9 | Upstox Place Order V3 has auto-slicing by freeze quantity (max 25 child orders), latency reported in `meta`, and a sandbox. Upstox claims about 30–45 ms execution; users report up to about 1 s. | medium (features), low (latency) | [Place Order V3](https://upstox.com/developer/api-documentation/v3/place-order), [community latency](https://community.upstox.com/t/order-execution-latency-enhancements/7209) |
| F10 | Upstox historical V3 has minute candles from **Jan 2022**, about 1 month per request. The expired-instruments API supports 1/3/5/15/30-minute and daily intervals. The historical API does not serve today; use the intraday API for that. | medium | [Upstox release post](https://community.upstox.com/t/get-historical-data-in-any-time-frame-you-wished-we-built-new-releases-at-upstox-api/8845), [expired intervals](https://community.upstox.com/t/issue-with-expired-contract-historical-data-10-minute-timeframe-using-python-sdk/12473) |
| F11 | `upstox-python-sdk` **2.30.0** (7 Sep 2026) includes MarketDataStreamerV3, PortfolioDataStreamer (orders by default; positions, holdings and GTT need opting in), auto-reconnect, the `X-Algo-Name` header and `sandbox=True`. | high | [PyPI](https://pypi.org/project/upstox-python-sdk/), [update_types](https://community.upstox.com/t/portfolio-stream-feed-websocket-client/12689) |
| F12 | NautilusTrader is moving to a v2 Rust core: 1.231 (Aug 2026) is the last 1.x, and v2 is at RC4 (Sep 2026). There is **no official Indian broker adapter**; a community `nautilus-fyers` adapter exists. | medium | [RELEASES.md](https://raw.githubusercontent.com/nautechsystems/nautilus_trader/master/RELEASES.md), [nautilustrader.io](https://www.nautilustrader.io/) |

**What these facts mean for the design (judgment):**
- **The feed and the broker set the speed limit, not our code.** Snapshots arrive every 0.3–1 s and an order round trip takes 50–300 ms. A Python core with under 5 ms internal p99 adds almost nothing. For 1–10 minute scalps, the edge comes from signal quality and execution tactics, not microseconds. Rust is not needed in v1.
- **Each broker account needs one owner of its connection.** F6 means one app and one live token per Upstox account. F3/F8 mean one OPS budget per account. F1 means a fixed number of WebSocket connections per user. Together they force a **Broker Gateway singleton per broker account**. If your existing options agent uses the same Upstox account, the two systems **will invalidate each other's tokens** and will share OPS and socket limits. This is the most important open question below.
- **The 50-key D30 cap forces tiered subscriptions** (Section 4). It happens to match the "few in-play names" strategy.
- **No naked market orders.** Every entry and exit is a marketable limit order or carries protection (F5). The OMS builds this in.
- **Every morning needs a human step.** The token must be approved by phone before trading. The lifecycle scheduler has to treat this as a gate (Section 8).

---

## 1. Architectural style and ports

**Style:** hexagonal (ports and adapters) around a deterministic, event-driven core, split into two planes:

- **Hot plane** (deterministic, driven by ticks, one thread): Feed → Normalizer → BarBuilder/FeatureEngine → SetupEngine + FastModel → Risk → OMS → Execution adapter. It **never awaits** anything slow.
- **Cold plane** (async, seconds to minutes): LLM agents, news, filings, fundamentals, options analytics, reports. It talks to the hot plane only through **versioned, immutable artefacts**: `Watchlist`, `DayTypeAssessment`, `TradePlan`, `RiskOverride`. Each artefact has `valid_from` and `valid_until`.
- **LLM output can only tighten.** An artefact can narrow what the hot plane does (allowed setups, symbols, size multiplier ≤ 1.0). It can never widen the static risk caps.

**Port signatures (sketch):**

```python
class Clock(Protocol):
    def now_ns(self) -> int: ...                 # sim or wall; the ONLY source of "now" in core
    def monotonic_ns(self) -> int: ...
    def schedule(self, at_ns: int, cb: Callable[[], None], name: str) -> TimerId: ...
    def cancel(self, tid: TimerId) -> None: ...

class MarketDataFeed(Protocol):
    caps: FeedCaps                               # modes, max_depth, per-mode key limits, max_conns
    async def start(self) -> None: ...
    async def set_subscriptions(self, want: Mapping[InstrumentId, FeedMode]) -> SubResult: ...  # declarative diff
    def events(self) -> AsyncIterator[MarketEvent]: ...   # Tick | Depth | MarketStatus | FeedGap | FeedState
    def health(self) -> FeedHealth: ...

class HistoricalData(Protocol):
    async def bars(self, iid, tf: Timeframe, start, end, *, as_of: datetime, oi=False) -> pa.Table: ...
    async def intraday_bars(self, iid, tf, *, as_of) -> pa.Table: ...
    async def expired_instruments(self, underlying, expiry: date) -> list[Instrument]: ...

class InstrumentMaster(Protocol):
    async def load(self, day: date) -> MasterSnapshot: ...
    def get(self, iid: InstrumentId) -> Instrument: ...
    def from_native(self, venue: Venue, native: str | int) -> InstrumentId: ...
    def to_native(self, iid: InstrumentId, venue: Venue) -> NativeRef: ...
    def universe(self, name: str, as_of: date) -> list[InstrumentId]: ...   # point-in-time NIFTY500

class BrokerExecution(Protocol):
    caps: BrokerCaps          # order types, market_protection, slicing, ops_limit, gtt/oco, tag_maxlen
    async def place(self, o: OrderRequest) -> SubmitResult: ...           # idempotent on client_order_id
    async def modify(self, coid: ClientOrderId, a: OrderAmend) -> SubmitResult: ...
    async def cancel(self, coid: ClientOrderId) -> SubmitResult: ...
    async def snapshot(self) -> BrokerSnapshot: ...      # orders, trades, positions, funds
    async def margin_for(self, orders: Sequence[OrderRequest]) -> MarginQuote: ...
    def exec_events(self) -> AsyncIterator[ExecEvent]: ...  # OrderUpdate | FillReport | Reject | StreamGap

class PortfolioView(Protocol):                    # read-only projection, single writer = Portfolio
    def position(self, iid) -> Position: ...
    def open_risk_paise(self) -> int: ...
    def day_pnl(self) -> PnL: ...                 # realized, mtm, est_charges
    def exposure(self) -> Exposure: ...           # gross, net, by_sector, margin_used

class NewsSource(Protocol):
    async def fetch(self, q: NewsQuery, since: datetime) -> list[NewsItem]: ...  # first_seen stamped by us
class FilingsSource(Protocol):
    async def fetch(self, since: datetime) -> list[Filing]: ...   # dedupe key (exchange, filing_id/hash)
    async def attachment(self, f: Filing) -> Document: ...
class FundamentalsSource(Protocol):
    async def snapshot(self, iid, as_of: date) -> Fundamentals: ...
class OptionsAnalytics(Protocol):
    async def chain(self, underlying, expiry) -> OptionChain: ...
    def metrics(self, c: OptionChain) -> ChainMetrics: ...   # pcr, max_pain, oi_buildup, atm_iv, iv_pctile, skew

class LLMProvider(Protocol):
    caps: LLMCaps             # json_schema_output, tools, prompt_cache, server_web_search, ctx_window
    async def generate(self, req: LLMRequest[T]) -> LLMResult[T]: ...
# LLMRequest: model_alias ("analyst"/"triage"), system: list[Block(text, cacheable)], messages,
#   tools: list[ToolSpec(name, json_schema)], output: type[T] (pydantic), max_tokens, timeout_s, budget_tag
# LLMResult: value: T, raw_text, usage(in, out, cache_read, cache_write), cost_inr, latency_ms, model_id

class FastModel(Protocol):
    meta: ModelMeta           # name, version, feature_schema_hash, trained_until, calibration
    def predict(self, x: np.ndarray) -> np.ndarray: ...   # sync, no I/O, p99 < 200 µs

class Notifier(Protocol):
    async def notify(self, n: Notification) -> None: ...
    async def request_approval(self, a: ApprovalRequest, timeout_s: float) -> Approval: ...

class EventStore(Protocol):    # append-only, per-stream sequence numbers
    async def append(self, stream: str, events: Sequence[Event]) -> None: ...
    def read(self, stream: str, from_seq: int = 0) -> AsyncIterator[Event]: ...
class RawRecorder(Protocol):
    def write(self, feed: str, kind: str, ts_recv_ns: int, payload: bytes) -> None: ...  # non-blocking
```

**LLM agent loop.** The agent loop runs in *our* code, not inside a provider SDK, so changing providers only swaps the request and response mapping. Tools are provider-neutral `ToolSpec`s and are **read-only** (`get_features`, `get_filing`, `get_chain`, `search_news`).

**LLM decorators**, stacked as composable wrappers:
- `Recording`: stores the prompt hash and full response. Needed for replay determinism and audit.
- `BudgetGuard`: caps ₹ per day and per agent.
- `FallbackChain`: tries providers in order.
- `SchemaRepair`: one retry on a validation failure, then fail closed.
- `Cache`: keyed by (prompt hash, inputs hash).

**FastModel and "Jev".** I read "Jev" as "fast, non-LLM decision models": gradient-boosted trees or logistic models exported to ONNX or Treelite, running in-process in tens of µs. Even fast hosted LLMs take 200 ms–2 s round trip, are nondeterministic, and cannot be backtested honestly. They belong in the cold plane for news triage within seconds, never in per-tick decisions.

**Event envelope.** Every event carries:
- `event_id` (ULID), `type`, `schema_version`
- `ts_exch_ns`, `ts_recv_ns`, `ts_proc_ns`
- `source`, `seq`
- `correlation_id` (plan → signal → intent → orders → fills) and `causation_id`

**Event types:**
- Market: `Tick`, `Depth`, `Bar`, `MarketStatus`, `FeedGap`
- Derived: `FeatureUpdate`, `Signal`, `OrderIntent`, `RiskDecision`
- Orders: `OrderSubmitted`, `OrderAccepted`, `OrderPartiallyFilled`, `OrderFilled`, `OrderCancelled`, `OrderRejected`, `OrderExpired`, `OrderAmended`, `Fill`
- Portfolio and artefacts: `PositionChanged`, `PlanPublished`, `PlanExpired`, `DayTypeChanged`, `WatchlistChanged`
- Control: `RiskStateChanged` (NORMAL/REDUCED/HALTED/FLATTEN), `KillSwitch`, `Heartbeat`, `Alert`

---

## 2. Canonical domain model

**InstrumentId** is a readable, broker-independent key:
- `NSE:EQ:RELIANCE`
- `NSE:FUT:NIFTY:2026-10-27`
- `NSE:OPT:NIFTY:2026-10-13:25000:CE`
- `MCX:FUT:CRUDEOIL:2026-10-19`

**Instrument attributes:**
- Identity: `isin`, `exchange_token`
- Contract: `lot_size`, `tick_size_paise`, `freeze_qty`, `expiry`, `strike`, `opt_type`, `underlying_id`
- Daily flags: `circuit_lo` and `circuit_hi`, `mis_allowed`, `mis_leverage`, `fno_ban`, `asm_gsm_stage`, `t2t`
- `broker_refs`, for example `{upstox: "NSE_EQ|INE002A01018", kite: {token: 738561, tradingsymbol: "RELIANCE", exchange: "NSE"}}`

The mapping table is snapshotted **per trading day**, so the code can survive renames, F&O rollovers and ISIN changes. Startup refuses to trade if any watchlist symbol fails to map on the chosen venue.

**Numbers:**
- Prices are **int64 paise**, and quantities are ints, throughout the hot path. This avoids float drift and is friendly to numpy and numba.
- `Decimal` is used only at the journal and report edges.

**Market data types:**
- **Tick:** `ltp`, `ltq`, `vol_cum`, `atp` (the exchange's own VWAP, which should be used), `oi`, `bid1/ask1` with sizes, `tbq/tsq`, `ts_exch`, `ts_recv`.
- **DepthSnapshot:** fixed `int64[2, 30, 3]` arrays (side × level × {price, qty, orders}) plus `n_levels`.
- **Bar:** built **locally from ticks**, so live and replay match. Fields: `o, h, l, c, v, oi, vwap, n_updates, buy_vol_est, sell_vol_est`. Broker 1-minute candles are used only for reconciliation and backfill.

**Orders: intent versus broker order.**
- `OrderIntent` comes from a strategy and is broker-agnostic. Fields: `intent_id`, `strategy_id`, `plan_id`, `iid`, `side`, `risk_budget_paise` or `qty`, `entry{MARKETABLE_LIMIT|LIMIT|STOP_LIMIT, px, max_slip_bps}`, `stop_px`, `targets[]`, `time_stop_s`, `product{MIS,CNC,NRML}`, `valid_until`.
- `RiskDecision` contains `verdict{APPROVE,RESIZE,REJECT}`, `approved_qty`, `rule_hits[]` and `risk_state_hash`.
- `Order` is owned by the OMS and only the OMS mutates it. Fields: `client_order_id` (deterministic, fits the broker `tag`), `broker_order_id`, `exchange_order_id`, `group_id` (the bracket), `role{ENTRY,STOP,TARGET,EXIT,FLATTEN}`, `state`, `qty`, `filled_qty`, `avg_px_paise`, `px`, `trigger`, `version`.
- `Fill` is deduplicated by broker `trade_id`.
- `Position` contains `net_qty`, `avg_px`, `realized`, `mtm`, `open_risk_to_stop` and a `bracket` reference.

**Plans, signals, journal.**
- `TradePlan` is a pydantic model: `plan_id`, `version`, `author{agent, model_id, prompt_hash}`, `valid_from/until`, `iid`, `bias`, `allowed_setups[{setup_id, params}]`, `entry_zone`, `invalidation_px`, `targets`, `max_risk_inr`, `confidence`, `catalysts[]`, `evidence_refs[]`, `rationale`.
- Deterministic sanity checks run after schema validation: stop within [0.3, 3]×ATR, prices inside circuit bands, the setup exists, the setup is allowed for the current day-type.
- `Signal` contains `setup_id`, `score`, the feature-vector hash and the model version.
- `JournalEntry` holds every correlation ID, entry and exit, MAE/MFE, slippage against signal price, charges, R-multiple, plan adherence, the LLM rationale and the post-trade review.

**Order state machine, normalized across brokers:**

```
PENDING_NEW ─(WAL write, send)→ SUBMITTED ─ack→ ACCEPTED ─┬→ PARTIALLY_FILLED → FILLED*
     │                     │ timeout              ├→ TRIGGER_PENDING → ACCEPTED (SL triggered)
     │                     └→ UNKNOWN ─reconcile→ (adopt actual state | REJECTED_LOCAL*)
     └→ REJECTED*         ACCEPTED/PARTIAL → PENDING_CANCEL → CANCELLED*;  → PENDING_AMEND → ACCEPTED
                          any → REJECTED* | EXPIRED*          (* terminal)
```

- Broker statuses map onto this through a table. Upstox and Kite both use "open pending", "validation pending", "trigger pending", "complete", "modify pending" and similar.
- `filled_qty` is monotonic and terminal states take precedence. Out-of-order updates are resolved by (filled_qty, broker ts).
- An illegal transition never crashes the process. It emits an `Alert` and forces reconciliation.

---

## 3. One code path for backtest, replay, paper and live

| Profile | Clock | Feed | Execution | Purpose |
|---|---|---|---|---|
| research | n/a | Parquet bars | vectorized (polars/vectorbt) | idea screening only; **not** the validation path |
| replay | Sim | `ReplayFeed` (recorded raw frames) | `PaperBroker` | validation, regression, determinism |
| paper-live | Wall | live WebSocket | `PaperBroker` | forward test |
| shadow | Wall | live WebSocket | `PaperBroker` + read-only real broker (`margin_for`, order validation via sandbox) | proves order construction and margin |
| live | Wall | live WebSocket | `UpstoxExecution` / `KiteExecution` | real money |

**The kernel is a discrete-event simulator.**
- In replay it merges recorded streams with a heap ordered by **`ts_recv`**, which is what we actually knew and when, not `ts_exch`.
- Before delivering each event it fires every timer due earlier.
- Inside the process, dispatch is **synchronous and in fixed handler order** (one bus, no per-component `asyncio.Queue`). This makes runs bit-for-bit reproducible.

**PaperBroker is just another adapter**, with pluggable `FillModel`, `LatencyModel` and `CostModel`:
- A **marketable** order arrives at `t + latency` (lognormal, median about 150–200 ms, calibrated later from live acks) and walks the depth snapshot current *at arrival*.
- A **passive limit** order fills only when trades print *through* its price, or at its price once the queue ahead of it has been consumed. Queue position is estimated from depth at placement and decremented by volume traded at that price.
- The default is the conservative mode.
- `CostModel` uses versioned charge tables (STT, exchange, SEBI, stamp, GST, brokerage), because charges get revised.

**How look-ahead is ruled out:**
1. Core code reads time only through `Clock`. `datetime.now`/`time.time` are banned with a ruff `banned-api` rule.
2. Historical reads must pass `as_of`. In sim, an `AsOfGuard` raises if `end > as_of` (for example, asking for today's daily bar before the close).
3. Bars are emitted only after close: first event past the boundary plus a 250 ms grace. "Forming bar" is a separate, explicitly typed stream.
4. Universe and instrument data are point-in-time: Nifty 500 membership, the F&O ban list and ASM/GSM lists as of each day.
5. LLM artefacts are replayed **from the recording**, published at `created_ts + observed_latency`. Regenerating past plans with today's model is labelled "contaminated" and excluded from performance claims.
6. News and filings use **our first-seen timestamp**, not the article's stated time.
7. CI runs two gates. **Determinism:** replay a golden day twice and require an identical journal hash. **Live/replay parity:** replay each paper-live day and diff signals and intents; anything under 100% means hidden nondeterminism.

---

## 4. Runtime topology and event bus

**Recommendation: a modular monolith for the hot path, plus satellite processes.**

| Process | Contents | Restart impact |
|---|---|---|
| `broker-gateway` (one per broker account; can live inside `trader-core` at first) | token custody, WebSocket connections, OPS limiter, portfolio stream | central; see the shared-account question below |
| `trader-core` | uvloop event loop: feed client, normalizer, bars, features, setups, FastModel, risk, OMS, portfolio, **square-off logic** | trading pauses; broker-resident stops protect positions |
| `recorder` | raw-frame tee written to Parquet | none on trading |
| `intel-worker(s)` | LLM agents, news, filings, fundamentals, chain analytics | none (artefacts expire, so behaviour falls back to safe) |
| `conductor` | daily lifecycle, token flow, master downloads | none intraday |
| `api` | FastAPI plus WebSocket to the UI, command ingress | none |
| `deadman` | about 150 lines, watches the `trader-core` heartbeat | see Section 7 |
| infra | Postgres, NATS, Prometheus, Grafana, Loki, Caddy | — |

**Load estimate (judgment).** Roughly 600 `ltpc` + 200 `full` + 40 `full_d30` instruments, averaging 1–3 msgs/s with bursts of a few thousand per second at 09:15. Protobuf decode (upb) at about 5–50 µs per message uses well under one core.

**When to split.** Instrument the event-loop lag. If p99 lag exceeds 5 ms, move feed decode into its own process that publishes over ZeroMQ `ipc://` (about 30–60 µs). The `MarketDataFeed` port makes that move invisible to the core.

**Bus choice (judgment):**

| Option | Latency (localhost, typical) | Durability | Fit |
|---|---|---|---|
| in-process sync dispatch | ~µs | none | **hot path: required for determinism** |
| ZeroMQ | tens of µs | none (you build it) | only if the feed process is split out |
| Redis Streams | ~0.2–1 ms | yes, consumer groups | good, but no native request/reply |
| **NATS + JetStream** | ~0.1–0.5 ms | JetStream streams + KV with watch | **recommended for everything between processes** |

NATS wins here for four reasons:
- Request/reply suits acknowledged commands such as kill switch and approvals.
- Subject wildcards (`md.NSE.EQ.*`, `cmd.trader.*`) make routing simple.
- The KV store with watch drives feature flags and hot parameters.
- It is a single small binary.

The **hot path never crosses the bus.** The bus carries only recorder and UI fan-out, artefacts coming in, commands coming in, and alerts going out.

**Subscription tiering**, driven by the Watchlist artefact and re-tiered at most every 5 minutes to limit churn:

| Tier | Mode | Size | Contents |
|---|---|---|---|
| A (in-play) | `full_d30` | ≤40 | leaves headroom under the 50 cap |
| B (candidates) | `full` | ≤200 | |
| C (universe) | `ltpc` | Nifty 500 + indices + VIX | |

Each strategy declares the minimum tier it needs. The depth scalper, for example, requires A.

---

## 5. Plugin system and configuration

**Composition and plugins.**
- Configuration is layered YAML (`base` → `profile` → `local` → env vars) and validated by pydantic-settings.
- The fully resolved config is **hashed and stored with every run, signal and order**.
- A single composition root, `build_app(cfg)`, wires everything. No DI framework is needed.
- Plugins come from a decorator registry (`@register("execution", "upstox")`) plus `importlib.metadata` entry points (`trader.execution`, `trader.feed`, `trader.llm`, ...) for external packages.

**Capability negotiation is what makes plug-and-play safe.** At startup, each enabled strategy's `requires` (for example `depth>=20`, `market_protection`, `segment=NFO`) is checked against the chosen adapters' `caps`. A D30 scalper therefore refuses to start on a Kite feed instead of silently degrading.

```yaml
profile: paper                      # replay | paper | shadow | live
clock: wall
broker_accounts:
  upstox_main: {adapter: upstox, token_source: access_token_request, ops_budget: 8, static_ip_required: true}
market_data: {feed: upstox_main, tiers: {A: {mode: full_d30, max: 40}, B: {mode: full, max: 200}, C: {mode: ltpc, max: 600}}}
execution: {adapter: paper, paper: {fill_model: queue_conservative, latency_ms: {dist: lognormal, median: 180, p99: 900}}}
llm:
  analyst: {provider: anthropic, model: "<id>", fallback: ["openai:<id>"]}
  triage:  {provider: openai, model: "<small-id>"}
  record: true
  daily_budget_inr: 1500
risk: {capital_inr: 1000000, risk_per_trade_pct: 0.4, scalp_risk_per_trade_pct: 0.25, max_open_risk_pct: 1.0,
       daily_reduce_pct: 1.5, daily_halt_pct: 2.0, daily_flatten_pct: 2.5, max_gross_leverage: 4.0,
       max_positions: 4, max_trades_day: 20, consec_loss_cooldown: {losses: 4, minutes: 30}}
strategies: [strategies/orb_pullback.yaml, strategies/vwap_reclaim.yaml, strategies/depth_scalper.yaml]
```

**Secrets.**
- Never stored in YAML. Use sops + age-encrypted `.env` files and Docker secrets.
- Daily access tokens are stored encrypted in Postgres with their expiry.
- Logs scrub anything that matches token patterns.

**Feature flags and hot reload.** Flags live in NATS KV, and every change is audited. Parameters fall into three classes:

| Class | Examples | When it applies |
|---|---|---|
| (a) tighten-only | disable a strategy, blacklist a symbol, size multiplier ↓, max trades ↓ | immediately, at any time |
| (b) bounded tuning | thresholds inside a range validated in research | from the next *new* signal, never mid-position |
| (c) restart-only | adapters, model versions, **any loosening of risk** | after market hours, with two-step confirmation |

---

## 6. Persistence

**Raw recorder.**
- Records **raw broker frames** (protobuf bytes plus `ts_recv`) so the normalizer can be re-run after a bug fix.
- Writes an append-only length-prefixed log for crash safety, and compacts every 5 s into Parquet (zstd), partitioned `date/feed/kind`.

**Volume estimate (judgment).** One D30 snapshot is about 1.4 KB raw. At 40 names × about 3/s × 22,500 s, that is about 2.7M snapshots, or about 4 GB/day raw and about 0.4–1 GB/day compressed. Keep 30 days on NVMe and move older data to object storage. Start recording in week 1: broker APIs cannot give you historical depth, so **every unrecorded day is lost training data for the scalper.**

| Data | Store | Why |
|---|---|---|
| raw frames, normalized ticks/depth, features | Parquet + **DuckDB** | zero-ops, fast replay and research |
| 1-minute bars, intraday feature snapshots for the UI | Postgres (TimescaleDB extension optional) | one database to operate |
| orders (**append-only `order_events`**, the source of truth), fills, positions_eod, plans, signals, risk_decisions, journal, approvals, alerts, config_runs | **Postgres** | several writers, transactions |
| LLM calls (prompt hash, model, tokens, ₹, latency, response) | Postgres + blob store | audit, replay, cost tracking |
| system metrics | Prometheus | |

QuestDB and ClickHouse are excellent but not justified for 1 trader and fewer than 1,000 instruments. Revisit them if ad-hoc SQL over months of ticks becomes routine. SQLite is acceptable for one-off research runs only.

**Backups:** nightly `pg_dump` plus WAL archiving to object storage, and Parquet sync.

---

## 7. OMS and risk placement

**Pipeline:** Signal → Sizer → `PreTradeRisk` → OMS → `Throttle` → `Guardian` → Adapter.

`PreTradeRisk` is pure functions over in-memory state, cheapest check first, taking under 100 µs in total:

1. **System:** kill switch off; within the trading window; feed fresh for this instrument (≤3 s for Tier A); token valid; reconciliation clean; clock offset under 250 ms.
2. **Instrument:** MIS allowed; not ASM/GSM/T2T; not in F&O ban; at least 2% from the circuit band; spread ≤ `max_spread_bps` (for example 8 bps for scalps); ADV ≥ ₹50 cr; top-5 depth ≥ 3× order quantity.
3. **Per trade:** `qty·|entry−stop| + est_costs + est_slippage ≤ R` (₹4k swing-intraday, ₹2.5k scalp); stop ≥ max(3 ticks, 0.25×ATR₁ₘ).
4. **Portfolio:** open risk ≤ 1% (₹10k); gross ≤ 4× (₹40L); margin used ≤ 80%; per-symbol ≤ 25% of gross; sector bucket caps; ≤4 concurrent positions.
5. **Daily, computed pessimistically:** `allowed_new_risk = halt_limit − realized_loss − mtm_loss − open_risk`. At −1.5% size is halved, at −2% new entries halt, at −2.5% everything is flattened and halted. Slippage is the buffer up to the 3% hard ceiling. The consecutive-loss cooldown also applies.
6. **Rate:** a priority token bucket at **8 OPS** per exchange-segment (2 below the regulatory 10), in priority order FLATTEN > STOP > EXIT > ENTRY. Entries may never use the last 3 tokens. Because modifies may count toward OPS (F4), trailing stops are amended at most once every 3 s.
7. **Fat-finger:** notional ≤ ₹15L per order; limit price within ±1% of LTP; quantity ≤ freeze quantity (or explicit slicing).

**Guardian** is a separate module with independent code. It sits at the adapter boundary and enforces static last-chance caps (max notional, max orders per minute, max open orders), so a bug in the main risk engine cannot get past it.

**Order construction (Indian specifics):**
- **Entry:** a marketable limit at `ask + n ticks`, capped at `max_slip_bps`. The OMS cancels it after 2–3 s if unfilled.
- **Stop:** a **broker-resident SL-limit** with a wide limit offset, placed as soon as each fill arrives and sized to the filled quantity. If price gaps through the limit and the stop stays unfilled 2 s after triggering, the OMS cancels it and sends an aggressive marketable exit.
- **Target:** handled in software by default, to save OPS. If a resting target is used, the OMS runs its own OCO. If both legs fill, the overfill is detected and flattened immediately.
- **Scalps:** a time stop at T+N minutes.

**Idempotency.**
- `client_order_id = base32(intent_id, role, attempt)`, fitted to the broker tag length (verify Upstox and Kite tag limits).
- **Write-ahead:** `PENDING_NEW` is persisted before sending.
- **No automatic resend after a timeout.** On a timeout the order becomes `UNKNOWN`. The OMS looks it up in the order book by tag, adopts it if found, and otherwise marks it `REJECTED_LOCAL` after two polls (about 3 s) and allows `attempt+1`.
- Never put retry decorators on `place()`.

**Reconciliation**, every 5 s, on every reconnect, and on any anomaly:
- Fetch orders, trades and positions, and diff them against the OMS projection.
- **For positions, the broker is the truth.** A mismatch that persists for more than 2 cycles halts new entries.
- Orders carrying our tag prefix are adopted. Untagged orders are classed as external, counted in risk, and optionally halt trading.
- Missed fills are backfilled from the trades API and deduplicated by `trade_id`.
- **Naked-position invariant:** every open position must have live stops covering its full quantity. If not, a stop is placed at STOP priority.

**Disconnects.**
- **Feed drop:** affected instruments are marked stale and blocked for new entries; continuity-dependent features are invalidated until warm again; reconnect uses backoff of 0.5→30 s with jitter.
- **Portfolio stream drop:** the OMS polls orders every 1 s until the stream is back.

**Restart.** The core moves through `BOOTING → RECONCILING → WARMING → READY → TRADING`:
1. Rebuild state from today's `order_events`.
2. Pull the broker snapshot and reconcile.
3. Verify stops are in place.
4. Rehydrate strategy position context from the database.
5. Warm features from the intraday candles API plus the recorder.

If reconciliation fails, the core enters `SAFE` (flatten-only).

**Kill switch**, four levels:
1. Pause entries.
2. Cancel working entry orders.
3. Flatten everything.
4. Lock: no restart without manual unlock.

Triggers: the UI, Telegram `/kill` with a PIN, or automatic (daily-loss tier, failed reconciliation, feed down for more than 60 s with open positions, abnormal order rate, clock skew).

**Dead-man's switch.** The `deadman` process connects to the broker on its own and runs level 2, then level 3, if the `trader-core` heartbeat is missing for more than 10 s during market hours with positions open.

---

## 8. Reliability and operations

**Watchdogs and metrics (Prometheus):**
- `feed_staleness_s{tier}`
- `loop_lag_ms` (alert at p99 > 10 ms)
- `tick_to_intent_us`, `intent_to_ack_ms` (alert at p95 > 1 s)
- `feed_latency_ms` = ts_recv − ts_exch
- `ops_bucket_level`
- `risk_rejects{rule}`, `recon_diffs`
- `pnl_realized`, `open_risk`
- `token_ttl_s`
- `chrony_offset_ms` (warn at 50, halt at 250)
- `llm_cost_inr{agent}`, `llm_latency_ms`

Logs are structlog JSON with correlation IDs, shipped to Loki. Grafana alerting goes to Telegram at three severity levels (info, warn, page).

**Daily lifecycle (IST), run by `conductor`; safety-critical square-off is also inside `trader-core`:**
- **07:30** Download instrument masters (Upstox and Kite) → build canonical mapping snapshot. Load Nifty 500 PIT list, F&O ban, ASM/GSM, circuit bands, holiday calendar.
- **08:00** Send Upstox Access Token Request → you approve on your phone → the notifier webhook receives the token, verified by calling the profile API → stored encrypted. Telegram reminders at 08:30 and 08:50. **If there is no token by 09:05, the system runs paper-only for the day.**
- **08:00–09:10** Intel plane runs: overnight news and filings, global cues, pre-open (09:00–09:08) gap scan, LLM brief → `Watchlist`, `DayTypeAssessment` prior, `TradePlan`s.
- **09:10** Set subscription tiers and warm features.
- **09:15** Market opens; setup-specific entry embargoes apply (for example none before 09:20 except ORB).
- **Intraday:** event-driven LLM refresh (filing triage in under 5 s, deep analysis in 20–60 s) and re-tiering every 5 minutes or less often.
- **15:00** No new entries.
- **15:10** Flatten MIS. Keep the square-off time configurable and at least 10 minutes before the broker's auto square-off (confirm each broker's time).
- **15:40+** EOD reconciliation against broker trades, P&L after charges, journal, LLM post-market review, Parquet compaction and upload, backups.
- **Weekly:** FastModel retrain and evaluation, paper-versus-live divergence report.

**Deployment.**
- A Mumbai-region VPS with a static or elastic IP (4 vCPU, 16 GB, 200 GB NVMe is enough), running Docker Compose.
- A **standby VPS whose IP is pre-registered in the backup slot**, because the IP can change only once a week (F3).
- Caddy terminates TLS. Only the notifier webhook is public. The UI sits behind Tailscale or Cloudflare Access. SSH is key-only.
- Upstox webhooks carry no signature, so the token is verified by calling an API with it.

**Time.**
- chrony with several sources: the cloud provider's time service, time.google.com, in.pool.ntp.org.
- Durations use the monotonic clock. Both exchange and receive timestamps are always stored.

---

## 9. Language and technology choices

**Python 3.12+ with uvloop.**

| Purpose | Choice |
|---|---|
| Hot-path event types | **msgspec Structs** or slotted dataclasses (faster than pydantic) |
| Config, LLM I/O, artefacts | **pydantic v2** |
| Features | numpy, numba for incremental O(1) updates (VWAP, ATR, RVOL, OFI, microprice, depth imbalance) |
| Batch and research | polars, DuckDB, pyarrow |
| Protobuf decode | `protobuf` with the upb backend |

**Broker I/O.**
- Both `upstox-python-sdk` and `kiteconnect` are synchronous HTTP clients (swagger/urllib3 and requests). This is my assessment and should be verified.
- **Write thin async adapters** on `httpx` with persistent keep-alive connection pools, so orders never pay a TLS handshake or block the loop.
- Use the SDKs for reference, for non-critical calls in a thread executor, and for the sandbox.
- WebSocket: own client on `websockets` or `picows`, so reconnects and gap detection are under our control.

**Other libraries:** FastAPI, uvicorn, nats-py, asyncpg, SQLAlchemy 2, Alembic, APScheduler (AsyncIOScheduler, in `conductor`), structlog, prometheus-client, ruff, pyright (strict), pytest, and **hypothesis** for property tests of the OMS state machine.

**FastModel stack:** LightGBM, exported through Treelite or ONNX Runtime.

**When to use Rust (pyo3/maturin):** only if profiling shows feature computation over 1 ms per event or D30 decode saturating a core. That is unlikely at this scale.

**Build or adopt NautilusTrader.** It already provides a Rust core, a MessageBus, an identical backtest/live path and an OMS. Against it:
- v2 is mid-migration (F12).
- It has no Indian adapters, and the India-specific work has to be custom either way: tokens, market protection, OPS limits, MIS square-off, D30.
- You need to own and understand the core code.

**Recommendation:** build a lean core (about 6–8k LOC) that deliberately copies Nautilus's Clock, MessageBus, Cache, ExecEngine and RiskEngine patterns, and re-evaluate once Nautilus v2 is stable (around Q1 2027).

---

## 10. Repository layout and build order

```
src/trader/
  domain/       ids, instrument, money(paise), events, order FSM, position, plan, risk types (pure)
  ports/        Protocols above
  core/         clocks (wall/sim), sync message bus, timer wheel, lifecycle FSM, composition root
  marketdata/   normalizer, bar builder, depth book, subscription tier manager, staleness
  features/     incremental indicators + feature schema/versioning
  strategies/   Strategy base, setup engine, setups/ (orb_pullback, vwap_reclaim, depth_scalper)
  models/       FastModel runtime, registry, schema-hash guard
  risk/         pre-trade rules, daily risk state, guardian
  oms/          order manager, bracket/OCO, throttle (priority OPS), idempotency, reconciliation
  portfolio/    positions, P&L, cost model (versioned charge tables)
  intel/        agents (premarket, filings, daytype, planner, reviewer), prompts/, schemas/
  adapters/     upstox/{auth,rest_async,ws_v3,portfolio_stream,instruments,history}, kite/, paper/,
                replay/, llm/{anthropic,openai,local,recording,budget,fallback}, news/, filings/{nse,bse},
                fundamentals/, options/, notify/telegram, storage/{postgres,parquet,duckdb}
  apps/         trader_core, recorder, intel_worker, conductor, api, deadman
  ops/          metrics, logging, health
research/       notebooks, vectorized tests, labelling, model training (never imported by src)
tests/          unit, property (OMS FSM), contract/ (one conformance suite every adapter must pass), golden_days/
deploy/         docker-compose.yml, Caddyfile, chrony.conf, grafana/
config/         base.yaml, profiles/, strategies/, risk.yaml, universe.yaml
```

The **adapter conformance suite** is what proves plug-and-play. It is one parametrized test set covering place, amend, cancel, partial fills, rejects, idempotent replay and reconnect. It runs against paper, the Upstox sandbox and recorded cassettes for Upstox and Kite.

**Milestones** (one developer with AI assistance, so roughly):

| Milestone | Weeks | Scope | Exit criterion |
|---|---|---|---|
| M0 | 1 | domain, ports, config, clock, bus, instrument master and mapping, VPS + static IP, token flow | 100% of watchlist mapped on both venues |
| M1 | 2–3 | Upstox V3 feed, normalizer, **recorder live** | 5 days recorded, <0.1% gaps |
| M2 | 3–4 | bars, features, ReplayFeed | determinism test green |
| M3 | 4–6 | PaperBroker, OMS FSM, risk, portfolio, costs, journal; 2 deterministic setups in paper-live | a full unattended day; replay parity 100% |
| M4 | 5–7, parallel | intel plane (filings, news, LLM port with recording), watchlist → tiers, UI v1, Telegram | brief out by 09:10 daily |
| M5 | 7–10 | scalper: labels, FastModel trained on 4–6+ weeks of D30 data, shadow inference | out-of-sample metrics hold in paper |
| M6 | 8–12 | Upstox live adapter (sandbox → 1-share live), reconciliation, kill switch, dead-man; semi-auto approvals | 2 weeks with zero reconciliation breaks |
| M7 | later | Kite adapter (second broker proves the ports), F&O, a selective swing/CNC module, MCX | |

---

## 11. UI

**Stack:**
- **Grafana** for time series (P&L, risk, latency, feed health).
- A small **FastAPI + HTMX/Alpine** control panel (or NiceGUI) over WebSocket or SSE.
- **Telegram** for mobile alerts, approvals and kill switch.
- Avoid Streamlit for live control: its rerun model is a poor fit.

**Screens:**
1. **Cockpit:** a large PAPER/LIVE banner; daily P&L against the −1.5/−2/−2.5% tiers; open risk; OPS bucket; token TTL; feed health per tier.
2. **Positions and orders:** each position shows whether its stop is present.
3. **In-play watchlist:** tier, day-type, catalysts.
4. **Plans:** LLM rationale, evidence links, confidence, validity, status.
5. **Signals:** feature snapshot and model score for each signal.
6. **Journal and post-market review.**
7. **Controls:** kill levels, pause strategy, blacklist symbol (all tighten-only). Every command is audited, and flatten needs two-step confirmation.

---

## Open questions for the owner

1. **Does the existing options-selling agent use the same Upstox account?** If yes, one app and one token (F6), shared OPS and shared WebSocket limits force a shared `broker-gateway` that both systems consume. The alternative is to run this system's execution on a different account or broker (for example Zerodha). This changes the topology.
2. Are you willing to approve the Upstox token on your phone every trading morning around 08:00–09:00? If you miss it, the system trades paper-only that day.
3. Is a Mumbai cloud VPS with a static IP and a standby (about ₹4–10k/month) acceptable, or do you want it running at home? Home broadband would need a static IP and a UPS.
4. Do you already have any recorded tick or depth history? If not, the scalper's ML stage cannot start until about 4–6 weeks after the recorder goes live.
5. Is ~0.3–1 s from feed snapshot to exchange acceptable for your scalping concept? If you need faster, retail broker APIs cannot deliver it, and an authorised tick-by-tick vendor would become a new `MarketDataFeed` adapter.
6. Will you also trade manually on the same account? That affects how reconciliation treats untagged orders: halt, or include in risk.
7. Should Zerodha be an execution alternative only, or also a second data feed (₹500/month)? Mixing Upstox data with Kite execution adds timestamp and price-alignment checks.
8. What daily order budget do you have in mind (for example ≤30 entries)? It sets the OPS reserve, trailing-stop amend policy and cost assumptions.
9. Should swing positions be CNC delivery only (no leverage, separate risk bucket), and who approves going overnight: always you, or automatic above a score threshold?
10. Is web plus Telegram enough for the UI, or do you need a mobile-native view?