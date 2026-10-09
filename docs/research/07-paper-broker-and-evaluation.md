# Paper Broker and Replay Simulator: Simulation and Evaluation Design

**Legend:** **[V-H/M/L]** means I checked it with web research in this session, at high, medium or low confidence. **[J]** means it is my own judgment or estimate. WebFetch could not resolve DNS in this sandbox, so every check comes from search-result extracts of the cited pages. Read the primary NSE/SEBI circulars and the broker API docs before writing code.

---

## 0. Bottom line

1. **Build the tick and depth recorder first, before any strategy.** Historical 30-level depth for Indian stocks cannot be bought cheaply. Every unrecorded session is replay data you never get back. [J]
2. **Use one engine with two clocks.** Strategy, risk, OMS and PaperExchange are the same objects in live-paper, shadow and replay. Only the clock and the data source change. The paper broker implements the same `BrokerExecution` port as the Upstox and Zerodha adapters and emits the same canonical events.
3. **Keep three fill-model tiers: optimistic, base and conservative.** Make go/no-go decisions only on the conservative tier. Reject any strategy that is profitable only on the optimistic tier.
4. **Costs and slippage decide whether scalping works.** On cash intraday (MIS), statutory charges are about 0.0355% of notional per round trip, plus brokerage. Add about 0.02% slippage per side and a 0.4% stop costs about 0.2R per trade. A scalp setup needs roughly ≥0.3R gross expectancy to be worth trading. After the April 2026 STT change, stock futures cost more than cash MIS for intraday scalps.
5. **4–6 weeks of paper trading cannot confirm a modest edge.** An edge of 0.15R with a 1.1R standard deviation needs about 333 trades with a fixed sample, or about 205 with a sequential test. Use the first 4–6 weeks to prove the plumbing works and to catch clear losers. Plan for 8–12 weeks before the go/no-go decision.
6. **Evaluate the LLM parts by recording and replaying their decisions, plus forward paired A/B tests using counterfactual paper books.** A historical backtest of LLM news judgment from before the model's training cutoff is never trustworthy.
7. **Place cheap 1-share live "probe" orders during the paper phase.** They calibrate latency, market-price-protection behaviour, rejection reasons and how often passive orders fill, before any real capital is at risk.

---

## 1. Facts that shape the simulator

| Fact | Confidence / source |
|---|---|
| The retail algo framework has been live since 1 Apr 2026: static IP for order APIs, OAuth plus daily 2FA, sessions closed at end of day, 10 orders per second per exchange as the registration threshold | [V-M] [Tradejini](https://www.tradejini.com/blogs/what-sebis-new-algo-trading-rules-mean-for-you), [Upstox mandates](https://community.upstox.com/t/important-new-sebi-exchange-mandates-for-api-trading-effective-1st-april-2026/14822) |
| Upstox stopped plain API market orders on 1 Oct 2025. From Apr 2026, Market and SL-M orders get market price protection (MPP) by default through an optional `market_protection` parameter | [V-H] [Upstox](https://community.upstox.com/t/regulatory-update-pausing-market-orders-via-apis/11306); [V-M] for the Apr 2026 part |
| Zerodha requires `market_protection` on API market orders: −1 means auto, 0 is rejected. Its UI table uses 2%, 1% or 0.5% for equity depending on price band | [V-M] [Zerodha MPP](https://support.zerodha.com/category/trading-and-markets/charts-and-orders/order/articles/market-price-protection-on-the-order-window) |
| Upstox `full_d30` gives 30 depth levels on the websocket and needs the Plus plan. Forum reports say d30 is capped at about 50 instruments per user and 1,500 instruments across connections | [V-H] [Feed V3 docs](https://upstox.com/developer/api-documentation/v3/get-market-data-feed); [V-L] for the caps: [forum](https://community.upstox.com/t/market-depth-30-increase-limit-for-more-than-50-instruments/13398) |
| The Upstox feed pushes an update when LTP changes. It is not order-by-order data | [V-L] [forum](https://community.upstox.com/t/what-is-the-time-between-each-tick/3775) |
| Upstox says about 45 ms from its server to exchange acknowledgement, and the v3 order response carries `metadata.latency`. Some users report 1,000–1,500 ms websocket latency | [V-L/M] [45 ms](https://community.upstox.com/t/re-9351107-clarification-on-achieving-45ms-latency-with-upstox-api/9453), [ws latency](https://community.upstox.com/t/websocket-latency-much-higher-than-expected-1000-1500ms-vs-claimed-30-50ms/9103) |
| Closing auction session (CAS) since 3 Aug 2026 for F&O-eligible cash stocks: continuous trading ends 15:15. From 15:15 to 15:20 nothing can be entered, modified or cancelled. SL and iceberg orders are cancelled at 15:15. The close is decided by the auction between 15:30 and 15:35. F&O trading runs to 15:40 | [V-M] [NSE CAS](https://www.nseindia.com/static/products-services/closing-auction-session), [CAS FAQ](https://yesinvest.in/standard-documents-and-policies/faqs/CAS-FAQ-DOC.pdf) |
| MIS auto square-off: Upstox 15:05 for CAS stocks and 15:20 for others. Zerodha 15:12 for CAS stocks. Upstox charges ₹75+GST on the basic plan and ₹50+GST on Plus. Zerodha charges ₹50+GST | [V-M] [Upstox timings](https://help.upstox.com/support/solutions/articles/252251-what-is-auto-square-off-and-what-is-the-auto-square-off-timings-for-different-segments), [Upstox fee](https://upstox.com/help-center/what-are-auto-square-off-charges-248671/), [Zerodha](https://zerodha.com/z-connect/?p=454739) |
| New pre-open session from 7 Sep 2026: 09:00–09:05 market and limit orders; 09:05–09:10 limit only, with a random close between 09:08 and 09:10; matching 09:10–09:12; buffer to 09:15 | [V-M] [Bajaj](https://www.bajajbroking.in/share-market-news/nse-revises-pre-open-rules-key-changes-from-september-7) (sources disagree on whether it covers cash or F&O) |
| STT from 1 Apr 2026: futures 0.05% on the sell side (was 0.02%); options 0.15% of premium on sell (was 0.1%). Intraday cash 0.025% on sell and delivery 0.1% on both sides are unchanged | [V-M/H] [ICICI](https://www.icicidirect.com/ilearn/futures-and-options/articles/stt-changes-in-budget-2026-what-f-o-traders-should-know) |
| NSE transaction charges were revised on 1 Mar 2026 (circular FA73061). Current cash rate 0.00307%, futures 0.00183%, options 0.03553% of premium. The rates from Oct 2024 to Feb 2026 were 0.00297%, 0.00173% and 0.03503% | [V-M] [NSE circular](https://nsearchives.nseindia.com/content/circulars/FA73061.pdf), [Zerodha table](https://support.zerodha.com/category/account-opening/resident-individual/ri-charges/articles/exchange-transaction-charges) |
| Stamp duty on buys: intraday 0.003%, delivery 0.015%, futures 0.002%, options 0.003%. SEBI fee ₹10 per crore. GST 18% on brokerage + transaction charges + SEBI fee, unchanged after GST 2.0 | [V-M] same Zerodha source; [GST](https://www.sahi.com/blogs/gst-on-share-trading-and-fno-what-every-trader-must-know) |
| Upstox intraday brokerage is ₹20 or a percentage per order, whichever is lower. Its own pages say 0.1% in one place and 0.05% in another. The ₹10-per-order API promotion ran to 31 Mar 2026 and I could not confirm what applies now | [V-M] [pricing](https://upstox.com/brokerage-charges/); [V-L] [API offer](https://community.upstox.com/t/stay-ahead-of-the-curve-we-re-extending-10-order-api-pricing-till-march-2026/13277) |
| NSE reviews tick sizes monthly using the month-end close: ₹0.01 below ₹250, ₹0.05 from ₹250 to ₹1,000, ₹0.10 from ₹1,000 to ₹5,000, and so on | [V-M] [Fyers](https://fyers.in/notice-board/tick-size-revision-for-nse-derivatives-cash-segment-effective-april-15-2025/) |
| F&O stocks have a dynamic 10% band that flexes in 5% steps with a 15-minute cooling-off. Non-F&O stocks have fixed 2/5/10/20% bands. MWPL and the F&O ban are delta-based since Oct 2025, and the ban does not affect cash trading | [V-M] [Zerodha](https://zerodha.com/z-connect/?p=381343), [Probe42](https://resources.probe42.in/regulatory-updates/sebi-updates/equity-derivatives-framework-2025/) |
| Intraday leverage comes from exchange margins (VaR + ELM, minimum about 20%), so about 5x at most. It is lower for ASM/high-VaR stocks | [V-M] [Bajaj Finserv](https://www.bajajfinserv.in/sebi-new-margin-rules-intraday-trading) |

**What this means for the design [J]:**
- There are effectively no true market orders any more. Every aggressive order is a protected limit order, so the simulator must model what happens to the unfilled remainder.
- Most liquid Nifty 500 names are F&O stocks, so they fall under CAS. The system must be flat by about 15:00, not 15:20.
- The 50-instrument d30 cap means: record 30-level depth only for the focus list plus a watch list of about 50 names, and use `full` mode (5 levels) for the rest of the Nifty 500.

---

## 2. Architecture: one engine, two clocks

```
MarketDataPort ──► Recorder (parquet: exch_ts, recv_ts, seq, payload)
       │
       ▼
EventBus (Clock: LiveClock | SimClock) ──► FeatureEngine ─► SetupEngine ─► RiskManager ─► OMS
                                                                                          │
                                         BrokerExecution port ◄───────────────────────────┘
                                ┌──────────────┼───────────────┐
                           PaperBroker     UpstoxAdapter    ZerodhaAdapter
                                │
   SessionCalendar · InstrumentMaster(tick/lot/freeze/band/MIS-list/margin%) · PreTradeValidator
   LatencyModel · MatchingSimulator(FillModel tier) · LiquidityLedger · MarginEngine
   ChargesCalculator(effective-dated) · PositionLedger · SquareOffScheduler · FaultInjector
```

- **Live-paper:** LiveClock and the live websocket drive the paper broker.
- **Replay:** SimClock and a ParquetReplayFeed drive the identical code.
- **Shadow mode:** the venue is live and a PaperBroker twin receives a copy of every order intent.
- **Counterfactual books:** paper fills cost nothing, so the paper broker hosts several isolated books at the same time:
  - **A** = production: what the system actually does.
  - **B** = ungated baseline: every deterministic trigger, with no LLM gate or day-type filter.
  - **C** = setups the LLM proposed and risk vetoed.
- Comparing books by day measures what each filter is worth (section 9).

---

## 3. Fill models

### 3.1 Timing: order arrival is delayed, not instant [J]

1. The strategy decides at local time `t_d`.
2. The simulated order reaches the exchange at `t_a = t_d + L_send`. `L_send` is drawn from a fitted lognormal. Default before calibration: median 120 ms, p95 450 ms.
3. The paper broker cannot see the book at `t_a` until the feed delivers it. It therefore fills against the first snapshot whose **exchange timestamp** is ≥ `map(t_a)`, using NTP plus a running estimate of `recv_ts − exch_ts`.
4. It emits ack and fill events at `t_fill + L_ack`.
5. Cancels use `L_cancel`. A cancel that arrives after a fill becomes `CANCEL_REJECTED_ALREADY_FILLED`, which is a real race the strategy must handle.

**Semi-auto (Telegram approval) note.** Add a human-approval delay distribution, for example median 20 s and p95 90 s. Most 1–10 minute scalps will not survive that delay, so in practice semi-auto suits only slower setups. Paper results under semi-auto must include the delay or they will be badly optimistic.

### 3.2 Aggressive orders (Market converted to an MPP limit)

- Protection limit: `L = ref × (1 + s·m)`, where `s = +1` for a buy and −1 for a sell, and `m` is the broker's MPP percentage.
- Fill by walking the opposite side of snapshot `S(t_a)`. For each level, usable quantity is `q_i' = α·q_i − consumed_i`. Default `α = 0.7`, which allows for a stale book and competing aggressors.
- Fill price: `P = Σ p_i·min(q_i', rem) / Q`, over levels with `p_i ≤ L`.
- Any remainder rests as a limit order at `L`. Whether Upstox actually rests or cancels the remainder must be measured with probes (open question).
- The conservative tier adds +1 tick to the fill price.
- **LiquidityLedger:** liquidity consumed by a paper fill is not available again until the snapshot shows that level changed, or 2 s pass. Without this, repeated adds keep re-using the same displayed quantity.
- **Feature consistency:** in live trading, our own resting orders appear in the depth feed. Subtract them in FeatureEngine so depth-imbalance features match between live and paper.

### 3.3 Passive limits: queue position estimate

- **On arrival:** `Q_ahead` = displayed quantity at our price `p` in `S(t_a)`.
- **On each update:**
  - Trades at `p`, `V_p`, are inferred from the change in cumulative volume when LTP equals `p`.
  - Unexplained quantity decrease at `p` is treated as cancellations: `D = max(0, Δq⁻ − V_p)`.
  - Update: `Q_ahead ← max(0, Q_ahead − V_p − f(x)·D)`, where `x = Q_ahead/(Q_ahead+Q_behind)` and `f(x) = x^n`.
- **Choice of `n`:**
  - Base tier: `n = 2`.
  - Conservative tier: `n → ∞`, meaning cancellations only come from behind us.
  - These are the standard probabilistic and "risk-averse" queue models; I know hftbacktest implements them from prior knowledge but did not re-check it.
- **Fill rules:**
  - Partial fill: `min(rem, V_p − Q_ahead_prev)` once the queue ahead is used up.
  - Full fill: the price trades through `p` by at least 1 tick. Conservative tier: no fill on a mere touch.
- **Caveat:** the snapshot feed may update only when LTP changes, so volume attribution is approximate. Count messages per second on day 1. If updates are sparse, start with conservative as the default.
- **After calibration:** replace the heuristic with a logistic model, `P(fill ≤ T) = σ(β·[log(Q_ahead/vol_1m), spread_ticks, imbalance, σ_1m, time-of-day])`.

### 3.4 Stops

- Exchange-resident SL orders trigger on LTP and have no send latency at trigger time. Broker-side triggers (GTT) add broker latency.
- **SL-M (now with MPP):** walk the book at `S(t_trig)` as in 3.2. Conservative tier adds +1 tick.
- **SL-L:** becomes a limit order at its limit price. If the book jumps past it, it stays unfilled, and the system's chase logic must be exercised. Suggested logic: cancel and replace aggressively after 500 ms.
- Slippage beyond the stop is measured and reported as `(fill − stop)/ATR_1m`.

### 3.5 Adverse selection: the main source of paper optimism [J]

1. **Phantom target fills.** Price touches the target, paper books a win, and price reverses. Live, the order was still in the queue and the stop is hit later. Fix: require trade-through or queue depletion for passive fills.
2. **Toxic passive entries.** In real markets you get filled exactly when a large aggressor sweeps through your level. Measure markouts `m_k = s·(mid(t_fill+k) − p_fill)/p_fill` for k = 1 s, 5 s, 30 s and 60 s. If live markouts are δ bps worse than paper, apply δ as a penalty to passive paper fills in the base tier.
3. **Recommendation:** scalp entries use marketable limit orders. Passive orders are used only where queue risk is acceptable, such as targets checked under rule 1.

### 3.6 Gaps, circuits, halts

- If the opposite side of the book is empty (locked circuit), nothing fills and the position is trapped.
- An intraday cash short that cannot be covered at upper circuit becomes a short delivery, which goes to an exchange auction with a penalty. The simulator should model this tail event. Policy suggestion: allow intraday shorts only in F&O stocks (dynamic bands) and never in tight-band (2%/5%) stocks. [J]
- Overnight swing positions: stops cannot work before the open. Assume the fill comes at the first continuous trade after 09:15, at the gapped open price minus slippage. Size swing positions on gap-adjusted risk, for example the 99th percentile overnight gap.

---

## 4. Exchange and broker realism: PreTradeValidator pipeline

Checks run in order, each mapped to a canonical `RejectReason`, with the same mapping in the live adapters:

1. **Session state.**
   - Pre-open windows and whether market orders are allowed in each.
   - CAS freeze (no entry/modify/cancel) from 15:15 to 15:20 for CAS stocks.
   - No new MIS orders after the broker cutoff.
   - Recommendation: v1 does not trade the pre-open auction. Paper returns `SESSION_NOT_SUPPORTED` unless auction simulation is switched on.
2. **Instrument status.**
   - Suspended stocks.
   - Trade-to-trade/BE series, which cannot be traded intraday.
   - ASM/GSM stages, where margin rises toward 100% and leverage falls to 1x.
   - F&O ban list: derivatives may only reduce positions; cash is unaffected.
3. **Price checks.**
   - Price must be a multiple of the tick size, using the monthly tick table.
   - Price must be inside the circuit or dynamic band.
   - Price must be inside the exchange's allowed range around LTP (limit price protection, "out of execution range").
4. **Quantity checks.** Lot size and freeze quantity for F&O, with automatic slicing. Note that slicing is not allowed with market orders on Upstox.
5. **Margin.**
   - Required margin = `qty × price × margin%(stock)`, taken from the daily broker MIS list or exchange VaR+ELM file.
   - Cap at the configured 4x.
   - Margin is blocked by open orders and positions.
6. **Order type rules.** Market orders are converted to MPP limits. No SL, IOC or iceberg orders during CAS.
7. **Rate limits.** Throttle at 8 orders per second, below the 10-per-second SEBI threshold. Emulate HTTP 429 (Upstox code `UDAPI10005`).
8. **Square-off scheduler.** At the broker's time, flatten with an MPP order and charge the configured fee plus GST. Log it as an incident: the system's own flat time should be 14:55 for CAS stocks.

**FaultInjector** (configurable rates):
- Random rejects (0.5%).
- Feed gaps of 2–10 s.
- Delayed acks.
- Websocket reconnects.
- Token expiry at 2FA rollover.

Paper must exercise these failure paths because live trading will hit them.

---

## 5. Costs

### 5.1 Effective-dated charge profile

Charges are stored as an effective-dated table so that replays of 2024–2026 apply the rates in force on each date.

| Component | Cash MIS | Delivery | Stock futures | Options (on premium) |
|---|---|---|---|---|
| STT | 0.025% sell | 0.1% both | 0.05% sell (0.02% before 1-Apr-26) | 0.15% sell (0.1% before) |
| NSE transaction | 0.00307% (0.00297% before 1-Mar-26) | 0.00307% | 0.00183% | 0.03553% |
| Stamp (buy side) | 0.003% | 0.015% | 0.002% | 0.003% |
| SEBI fee | ₹10/cr | ₹10/cr | ₹10/cr | ₹10/cr |
| GST | 18% × (brokerage + transaction + SEBI) | same | same | same |

Brokerage is a broker profile:
- `upstox_retail`: min(₹20, x%) per order, where x is 0.1% or 0.05% depending on which Upstox page is right.
- `upstox_api`: ₹10 flat, valid until 31-Mar-26; current terms unverified.
- `zerodha`: min(₹20, 0.03%) intraday, from my prior knowledge and not re-checked.
- Delivery also has a DP charge per scrip on sell days (verify the amount).

### 5.2 Formula and worked example

For cash MIS, the round-trip statutory cost is:

`0.025 + 2(0.00307) + 0.003 + 0.0002 + 0.18(0.00634) = 0.0355%` of notional, plus brokerage of 2 × ₹20 × 1.18 = ₹47.2.

Example: Rs 1,000 stock, risk R = ₹5,000, stop 0.4% (₹4), quantity 1,250, notional ₹12.5L.

| Item | Amount |
|---|---|
| STT | ₹312.5 |
| Transaction charges | ₹76.8 |
| Stamp | ₹37.5 |
| SEBI fee | ₹2.5 |
| Brokerage | ₹40 |
| GST | ₹21.5 |
| **Total** | **≈₹491 = 0.098R** |

### 5.3 Friction expressed in R

`friction_R ≈ (0.0355% + 2·slip%)/stop% + 47.2/R`

With slippage of 0.02% per side and R = ₹5,000:

| Stop | Statutory | + Slippage | Total friction |
|---|---|---|---|
| 0.25% | 0.15R | 0.16R | **0.31R** |
| 0.40% | 0.10R | 0.10R | **0.20R** |
| 0.60% | 0.07R | 0.07R | **0.14R** |
| 1.00% | 0.045R | 0.04R | **0.085R** |

The same arithmetic shows stock futures at about 0.057% statutory per round trip, more than cash MIS. Delivery swing trades cost about 0.22% plus DP charges, roughly 6x intraday, so a swing setup must clear a higher bar. [J]

### 5.4 Slippage model

`slip_bps = a + b·(spread_bps/2) + c·(Q / depth_within_10bps) + d·σ_1m_bps`, fitted per liquidity bucket. The prior before calibration is the book walk in 3.2.

---

## 6. Drop-in adapter contract

```python
class BrokerExecution(Protocol):
    async def place(req: OrderRequest) -> OrderAck          # idempotent via client_order_id
    async def modify(oid, ModifySpec) -> OrderAck
    async def cancel(oid) -> OrderAck
    async def orders() / trades() / positions() / funds_margins()
    async def margin_quote(reqs: list[OrderRequest]) -> MarginQuote
    def events() -> AsyncIterator[OrderEvent]                # canonical stream
```

**Canonical states:**
`CREATED → SUBMITTED → (REJECTED | OPEN | TRIGGER_PENDING) → PARTIAL → FILLED | CANCEL_PENDING → CANCELLED | MODIFY_PENDING → OPEN | EXPIRED`

- Each live adapter maps broker statuses into these. Upstox's "put order req received", "validation pending", "open pending" and similar all become `SUBMITTED`.
- Paper emits the same intermediate states with modelled delays, so the code paths for races and stale state are tested in paper.
- Each event carries: `client_order_id, broker_order_id, state, filled_qty, avg_px, last_fill{px,qty,ts}, reject_reason, exch_ts, recv_ts, venue`.
- Positions and margin come from the paper ledger, in the live API's shapes.

**Configuration sketch:**

```yaml
execution: {venue: paper, shadow_paper: true, books: [prod, baseline_ungated, vetoed]}
paper:
  fill_tier: conservative
  queue: {model: power, n: 2}
  depth_alpha: 0.7
  latency_ms: {send: {lognormal: [120, 450]}, cancel: {lognormal: [120, 450]}, ack: {lognormal: [80, 300]}}
  mpp_pct: auto
  extra_ticks: {stop: 1, exit_mkt: 1}
  charges_profile: upstox_api@2026-10
  square_off: {cas: "15:05", non_cas: "15:20", fee_inr: 50, gst: 0.18}
  faults: {reject_rate: 0.005, feed_gap_per_day: 2}
```

---

## 7. Calibration loop

1. **Phase P0 (paper plus probes).**
   - About 20–40 one-share live orders per day.
   - Mix: marketable limit, join-best-bid limit, SL-M, cancel-after-N-seconds.
   - Measures: true `L_send`, `L_ack`, `L_cancel`, MPP remainder behaviour, rejection codes, and time to passive fill compared with the paper queue prediction.
   - Queue position is the same for the first share whatever the order size, so 1-share orders are valid for fill-probability calibration.
   - Cost: if the "0.1%, whichever is lower" brokerage applies to API orders, each probe costs only a few rupees. Under a flat ₹10 per API order it costs more. Confirm the tariff.
2. **Phase L1+ (live small, with shadow twin).**
   - Every live order has a paper twin with the same decision time and parameters.
   - Per order, record: arrival mid, paper fill, live fill, fill or no-fill, time to fill, markouts.
3. **Fitting.**
   - Latency distributions come straight from timestamps.
   - Queue exponent `n` and logistic fill model by maximum likelihood on live fill/no-fill outcomes.
   - Slippage coefficients by regression of live implementation shortfall.
   - Re-fit weekly. Require ≥50 observations per bucket. Shrink toward the prior (Bayesian). Version and store every parameter set, and stamp each trade with the version used.
4. **Acceptance: paper is considered calibrated when all of these hold.**
   - Median absolute live-minus-paper shortfall ≤ 0.03R per trade.
   - Live/paper passive fill-rate ratio between 0.85 and 1.15.
   - Live/paper latency p95 ratio ≤ 1.3.
   - Otherwise, freeze scaling and re-fit.

---

## 8. Backtest and replay

**Recorder.**
- Each message stores `exch_ts, recv_ts, seq, token, LTP, LTQ, cum_vol, OI, depth[30×2](px, qty)`.
- Partition by date and instrument, compress with ZSTD, query with DuckDB.
- Size estimate [J]: about 50 d30 names × about 5 messages per second × 22.5k s ≈ 5.6M messages per day. Roughly 10 GB raw, 1–2 GB compressed per day.
- Also record every news, filing and LLM event with its `available_ts`.

**Tick replay.**
- Deterministic: seeded RNG, config hash and git SHA stamped on every run.
- Merges market and non-market events strictly by `available_ts`.

**Candle backtests (setups longer than scalps, and history before recording began).**
- If both the stop and the target sit inside the same bar, assume the stop was hit first.
- Signal on bar close; enter at the next bar's open plus half the spread plus impact.
- Limit orders fill only on trade-through by ≥1 tick.
- Fill size capped at 10% of the bar's volume.
- If the open gaps past the stop, fill at the open.
- 1-minute bars cannot validate 1–3 minute scalps. Those need tick replay.

**Point-in-time data.**
- Nifty 500 membership is rebuilt from niftyindices monthly files and the semi-annual review announcements, including delisted and merged names [V-L] ([forum](https://tradingqna.com/t/where-can-i-find-historical-composition-of-nifty-indices/7163)).
- Filings are timestamped at the exchange broadcast time. Fundamentals are dated by the results filing date, not the quarter end. News is dated by our first-seen time.
- **Web search cannot be used in backtests.** It returns today's pages, which leaks the future.

**Corporate actions.** Use adjusted series for features. Simulate trades on raw prices so tick sizes, bands and costs stay correct.

**Overfitting controls.**
- Rolling walk-forward: 6 months train, 1 month test.
- Purged and embargoed cross-validation for labels that overlap in time.
- A trial registry that counts every variant tested, with the Deflated Sharpe Ratio reported.
- Choose parameters from flat, stable regions of performance, not the single best peak.
- Use Upstox expired-contract data later for F&O, so expired contracts are not missing from history.

---

## 9. LLM components in backtests

Pre-cutoff history is contaminated: the model may simply know what happened, and web tools return current pages.

**Recommended approach:**

1. **LLM decision ledger, used for record and replay (primary).**
   - Log every call: model ID and version, prompt, hash of the input snapshot, parameters, output JSON, latency and cost.
   - Replays reuse the frozen outputs. This lets you honestly re-test the deterministic parts (stops, sizing, triggers) around real LLM decisions.
2. **Forward paired A/B (primary measure of what the LLM adds).**
   - Compare book A (with LLM) against book B (ungated baseline) on the same days.
   - Compute the paired daily difference in R. Pairing removes the shared market noise.
   - **LLM uplift** = mean(A − B) per trade, with a confidence interval.
   - The LLM layer stays only if its uplift exceeds its cost: API spend plus missed good trades.
3. **Anonymised historical tests (secondary, only for narrow classifiers such as day-type).**
   - Mask ticker, dates and price levels.
   - Run a leakage probe: ask the model to identify the masked stock or date. If it does better than chance, discard the result.
   - Never use this for news interpretation, because the news text itself identifies the event.
4. **Post-cutoff windows** are clean only if their inputs were archived at the time, and they are short. Treat them as a bonus, not a basis.

**Calibration of LLM confidence.**
- Brier score, reliability diagram, expected calibration error. Needs about 30–50 decisions per confidence bucket.
- Day-type accuracy is scored against a deterministic labeller applied after the close. Example: trend day if |close − open| ≥ 0.6 × range and range ≥ 1.2 × ATR20.

---

## 10. Evaluation statistics and gates

**Metrics.** Report each of these per setup, per day-type, per time bucket (09:15–09:45, 09:45–11:30, 11:30–13:30, 13:30–15:00) and per LLM confidence decile:
- Net expectancy in R.
- Profit factor.
- Win rate and average win/loss.
- Maximum drawdown in % and in R.
- Daily Sharpe and Sortino.
- MAE/MFE (use for stop/target design on training folds only).
- Implementation shortfall.
- Fill rate.
- Latency.

**Sample size.** Edge μ = 0.15R, σ = 1.1R, so σ/μ = 7.33.

| Test | Trades needed |
|---|---|
| CI lower bound > 0 at 95% (only 50% power) | (1.96 × 7.33)² ≈ **207** |
| One-sided α = 0.05, power 80% | ((1.645 + 0.842) × 7.33)² ≈ **333** |
| Two-sided α = 0.05, power 80% | (2.802 × 7.33)² ≈ **422** |
| Clustering: 3 trades/day, ρ = 0.2, design effect 1.4 | **466** |
| SPRT (H0: μ = 0 vs H1: μ = 0.15, α = 0.05, β = 0.2), average sample if edge is real | ≈**205** (about 10 weeks at 4 trades/day) |
| SPRT, average sample if there is no edge | ≈**144** |

SPRT details: each trade adds `LLR = (μ₁/σ²)(x − μ₁/2)`. Accept the edge when the running sum reaches ln 16 = 2.77. Reject it at −1.56.

**What 4–6 weeks can show.** After 100 trades the 95% confidence interval is still about ±0.22R.

**Daily Sharpe is weak evidence.** Its standard error is about `√((1+SR²/2)/T)`. With 60 days that is about 0.13, around a true daily value near 0.2. Trade-level statistics carry far more information.

**Losing streaks.** At a 45% win rate, expect a run of about ln(450)/ln(1/0.55) ≈ 10 consecutive losses somewhere in 1,000 trades. At 0.5% risk per trade, that is about a 5% drawdown from bad luck alone.

**Gate: paper → live L1 (10–20% size).** All of the following:
- ≥40 trading days.
- SPRT accepts, or ≥200 trades with bootstrap 90% CI lower bound > 0, measured on the **conservative** tier.
- Net expectancy ≥ +0.10R.
- Profit factor ≥ 1.25.
- Maximum drawdown ≤ 6%.
- Still positive after removing the best 5% of trades.
- Still positive under conservative +1 tick per side.
- Zero breaches of the daily risk limit.
- Zero unreconciled orders in the last 20 days.

**Gate: L1 → L2 (50%) → L3 (100%).** Each step needs ≥20 days and ≥80 trades, plus:
- Live expectancy not significantly worse than the shadow twin (paired test, p > 0.1).
- Average slippage gap ≤ 0.05R.

**Kill criteria.**
- Daily loss −2%: no new entries.
- Daily loss −2.5%: flatten and stop for the day.
- Drawdown −6% from peak: system back to paper.
- A setup whose rolling 50-trade expectancy falls below −0.1R, or whose CUSUM alarm fires, is disabled.
- Live-minus-paper gap > 0.1R per trade over 30 trades: stop scaling.
- Feed stale for more than 5 s with open positions: flatten.
- An unknown rejection code, or a reconciliation mismatch: stop.

---

## 11. Reporting and journal

**Daily report (auto at 15:45):**
- Gross and net P&L, costs, and R for each trade.
- Implementation shortfall and markouts.
- Fill and reject rates; latency p50/p95.
- Adherence to the LLM plan: trades planned vs taken, with skip reasons.
- Predicted vs realised day-type.
- Results from books A, B and C.
- Live vs shadow gap.
- Incidents.

**Weekly report:**
- Per-setup expectancy with confidence intervals and SPRT status.
- Equity curve and drawdown.
- Calibration curves.
- MAE/MFE.
- Parameter and model version changes.
- Data-quality log.
- Trial-registry count.

**Journal schema** (Postgres; large snapshots go to object storage, referenced by content hash):
- `decision`: `id, ts, available_ts, kind(brief/plan/gate), model_id, prompt_hash, inputs_snapshot_ref, output_json, confidence, rationale, latency_ms, cost_inr`
- `plan`: `id, decision_id, symbol, setup, direction, entry_rule, stop, targets, max_risk_R, valid_until, day_type`
- `signal`: `id, plan_id?, setup, ts, features_snapshot_ref, book_snapshot_ref, risk_verdict, veto_reason`
- `order`: `client_id, signal_id, book(prod/baseline/vetoed), venue, type, px, qty, mpp, state_history[], reject_reason, param_version`
- `fill`: `order_id, ts_exch, ts_recv, px, qty, liquidity(maker/taker), queue_est, arrival_mid`
- `trade`: `id, entry/exit fills, R_multiple, gross, charges_breakdown, net, MAE, MFE, hold_s, markouts{1,5,30,60s}, exit_reason`
- `shadow_pair`: `live_order_id, paper_order_id, shortfall_diff_bps, fill_match`

---

## 12. Open questions for the owner

1. **Upstox tariffs.** Which API brokerage applies now, ₹10 flat, ₹20, or "₹20 or 0.1% whichever is lower"? Are you on Plus (₹50 square-off fee) or Basic? This decides probe cost and the cost profile.
2. **Static IP host.** Where will the system run? The static IP requirement and latency both depend on it, and so do the latency priors.
3. **Semi-auto stage.** Do you accept that Telegram approval applies only to slower setups, with scalps going straight from paper to small automatic live trading?
4. **Probes.** Are you willing to run about 20–40 one-share live probe orders per day during the paper phase? It needs the static IP and app registration done early.
5. **Shorting.** Do you allow intraday shorts in non-F&O stocks? I recommend no, because of circuit and short-delivery auction risk.
6. **Expected trade count.** How many trades per day do you expect, around 3–6? It sets the paper duration: about 205 trades under SPRT is roughly 7–14 weeks.
7. **Paper duration.** Can the paper phase run 8–12 weeks instead of 4–6, if statistics require it?
8. **Storage.** Is about 1–2 GB per day of recorded depth acceptable, and how long should it be kept?