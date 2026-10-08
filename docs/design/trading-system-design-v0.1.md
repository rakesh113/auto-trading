# AI Trading Desk: System Design v0.1 (draft for discussion)

**Status:** draft for owner review. Design only; no code yet.
**Date:** 2026-10-08.
**Inputs:** 13 specialist and red-team reports in [`docs/research/`](../research/). They carry verified facts with sources and confidence tags. Where reports disagreed, this document uses the value the red team corrected.
**Not covered:** the existing options-selling agent. It stays separate. Section 13 covers where the two systems touch.

---

## 0. Decisions at a glance

| # | Decision | Main reason |
|---|---|---|
| D1 | **The LLM is the strategist and analyst, and it can only narrow what the system does.** Rule engines plus small ML models act as the trader. Deterministic code acts as risk manager (with veto) and execution desk. | LLM latency and non-determinism; LLM decisions on pre-cutoff history can't be honestly backtested. |
| D2 | **Two-speed loop: Plan → Permit → Trigger.** The LLM writes plans over minutes. Plans become immutable, expiring permits. Rules and ML fire triggers in milliseconds inside those permits. | Gives discretionary judgement and scalping speed in one design. |
| D3 | **Costs choose the instrument.** Stocks: cash MIS. Index direction: weekly ATM/ITM options on Nifty and Sensex. **No futures for intraday.** | Budget 2026 STT: futures 0.05%, options 0.15% of premium. Cash intraday is unchanged at 0.025%. |
| D4 | **A friction gate in code.** If estimated costs plus slippage exceed 0.2R, the trade is not taken. | Costs relative to stop size are the main way retail intraday and scalping lose. |
| D5 | **Daily loss: 2% hard limit (flatten and lock for the day).** 3% exists only as a catastrophic ceiling for gaps and slippage. R ≤ 0.5%, run at 0.25% in the first live month. | Five 3% days make a 15% drawdown. A new, unvalidated system will have such days. |
| D6 | **The paper broker is a drop-in adapter with conservative fills.** Go-live is decided per setup, on the conservative fill tier, using a sequential test (SPRT). | Paper optimism is the main cause of false go-lives. |
| D7 | **The tick and 30-level depth recorder is built first and runs every day.** | No broker or affordable vendor sells historical depth. Every unrecorded day is lost. |
| D8 | **Data source and execution venue are separate config choices.** Upstox supplies data through a 1-year read-only Analytics Token. Execution is `paper`, `upstox` or `zerodha`. | Upstox allows one API app per user, and the existing agent probably uses it (§13). |
| D9 | **Hexagonal (ports and adapters) architecture.** One engine serves replay, paper, shadow and live. Startup checks each strategy's requirements against the adapters' capabilities, and every adapter must pass a shared conformance test suite. | True plug-and-play, without silent degradation. |
| D10 | **A no-LLM baseline book always runs alongside.** An LLM agent stays only if its measured improvement exceeds its cost. | LLM spend is a real hurdle on ₹10L of capital. |
| D11 | **Scalping starts as a recording and research track.** The ML filter comes only after 50–100 recorded sessions. Jev and fast LLMs are used for text triage only, in shadow mode first. | Snapshot feeds, cost per trade, and no depth history. |
| D12 | **MCX starts with an operations layer** (contract calendar, rolls, tender/delivery, margin stress, band locks) before any MCX strategy. Mini and micro contracts only. | Compulsory delivery, pre-expiry margin and locked-limit days are the real MCX risks. |

---

## 1. Goals and constraints (from the owner)

- **Capital:** ₹10L. Daily risk appetite 2–3%. Intraday leverage up to 4x.
- **Paper first:** live paper trading comes first. The execution venue is selected by config: paper, Upstox, Zerodha, or others later.
- **Holding period:** intraday first. Swing trades only for exceptional setups, because of overnight geopolitical risk.
- **Modules:** intraday stocks, intraday options (index and stock), 1–10 minute scalps, and MCX commodities (intraday and positional).
- **Universe:** liquid Nifty 500 names, focusing each day on a few that are in play by news or price.
- **Modularity:** plug-and-play replacement of the LLM, broker, market-data and news sources.
- **Data available:**
  - web search (Claude/OpenAI)
  - NSE/BSE announcement scrapers
  - fundamentals APIs
  - historical candles and live quotes
  - option chain, PCR, max pain and OI
  - websocket feeds
  - Upstox Plus, which includes 30-level depth and expired-contract history
  - Zerodha Kite
- **Separation:** this is a new system, separate from the existing options-selling agent.

---

## 2. Where the edge can come from

**Likely sources of edge, in order:**
1. **Selection.** Trade 5–8 names a day whose flow is one-sided and driven by news. Sit out choppy names and bad days. Most retail losses come from trading the wrong stock on the wrong day.
2. **Catalyst interpretation.** Read every filing consistently and scale its materiality to the company's size. A ₹200 cr order is noise for a ₹50,000 cr company and about 10% of revenue for a ₹2,000 cr company.
   - News reaches an actionable plan 45–100 s after dissemination. So the trade is the **continuation or second leg**, not the first tick.
3. **Discipline applied by a machine.** Stops always honoured, no averaging down, no revenge trading, a daily lock.
4. **Cheap delta.** Express index direction through weekly options on trend days.
5. **Structural theta.** A hedged expiry-day afternoon iron fly or condor, only when the day is range-bound.
6. **Slow trend in commodities.** Positional, at small size. It diversifies the equity book.

**Not sources of edge for this system (do not build):**
- sub-second index lead-lag
- queue-position games
- reading spoof orders
- MCX vs COMEX/NYMEX arbitrage
- naked option selling
- futures scalping
- intraday condors on non-expiry days
- selling volatility right after an IV spike

**Expectations:**
- Year-1 success means **positive expectancy after all costs, at small size**.
- Operating costs (LLM, VPS, data) of ₹10–25k a month equal 12–30% of capital a year, which is a real hurdle. Keep them **≤ ₹10k a month during paper trading**.
- The scalping report's realistic target, if scalping works, is +0.1 to +0.25R net per trade. 3–4 of 6 candidate scalp setups may never pass the gate.

---

## 3. The core concept: a trading desk with two speeds

| Desk role | System component | Speed | Technology |
|---|---|---|---|
| Strategist | Pre-market Strategist agent | 08:30–09:12 | Strong LLM, with tools |
| Analysts | Filings/News triage, then Materiality Analyst | Event-driven, 2–40 s | Fast LLM or Jev (triage); strong LLM (materiality) |
| Plan writer | Stock Analyst agent, which outputs a `TradePlan` | 20–75 s | LLM |
| Trader | Setup engine (state machines) plus fast ML filter | milliseconds | Code plus LightGBM |
| Risk manager | Pre-trade risk, open-risk invariant, kill switch | microseconds | Code |
| Execution desk | OMS, throttle, broker adapters | milliseconds | Code |
| Coach | Post-market reviewer, weekly tuner (human-approved) | After hours | LLM, batch |

```
 COLD PLANE (seconds–minutes)                         HOT PLANE (milliseconds, deterministic)
 ┌───────────────────────────────┐                    ┌──────────────────────────────────────────┐
 │ News/filings ─► Triage ─► Materiality                │ Feed ─► Normalizer ─► Bars/Features      │
 │ Market sitrep ─► Strategist ─► Watchlist, day prior  │            │                             │
 │ Symbol sitrep ─► Plan writer ─► TradePlan (level IDs)│            ▼                             │
 │                    │                                 │  Setup state machines ─► ML filter       │
 │                    ▼ validate (schema, grounding,    │            │  (inside Permit only)       │
 │              risk policy)                            │            ▼                             │
 │              PERMIT (immutable, versioned, expiring)─┼──────► Risk (sizing, invariant, veto)    │
 │              can only NARROW: symbols, dirs,         │            ▼                             │
 │              setups, size_mult ≤ 1, blackouts        │  OMS ─► Throttle ─► Guardian ─► Adapter  │
 └───────────────────────────────┘                    └──────────────────────────────────────────┘
```

**Rules of the loop:**
- **Plans use level IDs, not prices.** The context builder gives the LLM a table of computed levels (`L.ORH15`, `L.PDH`, `L.VWAP`, `L.RND1400`). A plan says, for example, "break above `L.ORH15` + 0.1 ATR", and code resolves that to a price. This removes most hallucinated numbers before validation even runs.
- **Permits only restrict.** If the permit is missing or expired, no new entries are made. Exits are always deterministic and always allowed.
- **News creates a blackout, not a signal.** When a filing lands on a watchlist symbol, deterministic code sets `FRESH_UNASSESSED`. That pauses new entries in the symbol until triage (and materiality analysis, if needed) clears it. The LLM's latency defines the blackout window.
- **The hot path never waits on an LLM.**

---

## 4. Market-structure facts (Oct 2026) that shape the design

Details and sources are in research reports 01, 02, 06, 08 and 09.

| Fact | Design rule |
|---|---|
| The SEBI retail algo framework has been fully in force since 1 Apr 2026. Static IP applies to **order endpoints only** (primary plus backup, changed at most weekly). Daily 2FA. Orders are tagged as algo. Unregistered algos may send ≤ 10 orders/s per exchange, and modifies and cancels count. | Self-throttle at **5 orders/s**, with priority FLATTEN > STOP > EXIT > ENTRY. At most one trailing-stop modify per 3 s. Paper mode needs no static IP. |
| Market orders are converted to market-price-protection (MPP) orders. Kite rejects `market_protection=0`. SL-M is blocked on options. HTTP success does not mean the order was accepted, because RMS rejections arrive later. | Send **marketable limit orders with our own price cap** everywhere. The OMS waits on the order stream before treating an order as live. |
| **Upstox allows one active API app per user.** Generating a new token can expire the previous one. WebSocket connections, the order-rate cap, depth-30 slots and REST limits are all shared per account. | §13: a broker-topology decision is required. |
| The **Upstox Analytics Token** is valid for 1 year, read-only, and covers the feed and historical data. | Paper mode can run unattended with no daily login. Confirm with Upstox that generating it leaves the existing agent's app and token alone. |
| Feeds are **conflated snapshots** (about 1–4 per second). There is no tick-by-tick data and no historical depth. Upstox `full_d30` is limited to **about 50 keys per account**, and its depth levels carry no order count. Kite offers only 5 levels. | Record from day 1. Aggregate features over ≥ 10 s. Re-tier subscriptions at most every 5 minutes. |
| **Closing Auction Session (from 3 Aug 2026)** for F&O stocks: continuous trading ends at 15:15, and SL and iceberg orders are **cancelled at 15:15**. F&O trades until 15:40. Upstox MIS square-off moved to **15:10** for CAS stocks and 15:25 for others (from 11 Sep 2026). Zerodha squares off CAS stocks at 15:12. | No new entries after **14:40 (CAS) / 14:50 (non-CAS)**. CAS names flat by **15:00**, non-CAS by **15:12**. A CAS stock's official close is an auction price; treat it that way in previous-close and label logic after 3 Aug 2026. |
| **Pre-open revised (7 Sep 2026):** 09:00–09:05 market and limit orders; 09:05–09:10 limit orders only, with a random close between 09:08 and 09:10; matching 09:10–09:12. SL orders are not accepted. Futures have had a pre-open since Dec 2025; options are excluded. | The final indicative equilibrium price arrives around 09:12. The in-play list is finalised at 09:12. |
| **STT from 1 Apr 2026:** cash intraday 0.025% sell side (unchanged); futures 0.05% sell side; options 0.15% of sell premium. NSE transaction charge (from 1 Mar 2026): cash 0.00307%, futures 0.00183%, options 0.03553%. | Cost schedules are stored as data with effective dates, and live fills are reconciled to contract notes. |
| Weekly expiries: **Nifty on Tuesday, Sensex on Thursday.** BankNifty, FinNifty and Midcap are monthly only. A holiday moves expiry earlier: Tue 10 Nov 2026 is a holiday, so that week's Nifty expiry is Mon 9 Nov, and Muhurat trading is Sun 8 Nov. Lot sizes are Nifty 65 and Sensex 20, and an upward revision is likely soon. | Take expiry dates and lot sizes from the **contract master every day**. Never use weekday logic. Special sessions are disabled by default. |
| Intraday equity leverage is at most 5x (the higher of 20% margin or VaR+ELM). F&O stocks have dynamic price bands; other stocks have fixed 2/5/10/20% bands. | **Shorts only in F&O stocks.** Block new entries within about 1% of a price band. |
| Option-chain OI refreshes about every 3 minutes. | OI is context and a logged feature, never a hard gate. |
| Upstox GTT orders require an ENTRY leg, so they cannot protect an existing position. Zerodha's single-leg GTT can. | Overnight protection depends on the broker (§7.5). |
| NSE reportedly blocks cloud IP ranges for scripted access. | Run filings ingestion from home or another residential IP, or use BSE/RSS or a paid feed as fallback. |
| Upstox reportedly disabled MCX API trading in Apr 2026 (to verify). Upstox's expired-data API covers NSE/BSE F&O from about Oct 2024 with gaps; MCX coverage is unconfirmed. | MCX execution may need Zerodha. Verify in week 1. |
| **Current regime:** Nifty about 22,776 (6 Oct), after an 8-week losing streak. VIX 13.6–14.7, with headline spikes (+26% on 8 Jul). Brent about $100. FIIs net sellers for 15 months. The Q2 results season is starting. | Short setups matter. Event and geopolitical gates matter. The paper phase will cover a results season, which makes a good stress test. |

---

## 5. Costs and instrument choice

**Cash MIS round trip** ≈ 3.55 bps × notional, plus fixed brokerage of ₹47 (₹20/order including GST) or ₹71 (Upstox Plus at ₹30/order; verify on the contract note).

**Friction expressed in R**, where R is the rupees lost if the stop is hit:

```
friction_R ≈ (3.55 + spread_bps + 2·slippage_bps) / stop_bps  +  fixed_brokerage / R
breakeven_win_rate = (1 + friction_R) / (1 + target_R)
```

| Stop (R = ₹5k, 2 bps spread, 1 bp slippage per side) | Notional | Friction |
|---|---|---|
| 15 bps | ₹33L | **0.51R** (lethal) |
| 25 bps | ₹20L | 0.31R |
| 40 bps | ₹12.5L | **0.20R** (the gate) |
| 60 bps | ₹8.3L | 0.14R |
| 100 bps | ₹5L | ~0.085R |

**Hard gates in code:**
- `friction_R ≤ 0.2`, which in practice means cash stops of at least about 35–40 bps;
- expected move ≥ 3 × friction.

**Instrument choice:**

| Intent | Instrument | Why |
|---|---|---|
| Stock direction, intraday | **Cash MIS** | Cheapest. Futures cost about 2.1 bps more per round trip. |
| Stock trade where a gap or halt is the risk (binary news, circuit-prone name) | ITM stock option (liquidity whitelist only) or a debit spread | Loss is defined |
| Index direction, hold ≤ 1.5–2 h (≤ 1 h on expiry day) | **Nifty/Sensex weekly ATM or 1-ITM option, Δ 0.55–0.65** | One Nifty futures lot costs about ₹740 in STT; the same delta in options costs about ₹100. Theta erases the advantage on longer holds. |
| Index direction, longer hold | Debit spread | Theta |
| Range day or theta | **Expiry-day afternoon iron fly or condor only** | The only window where taking profit at 50% of credit is realistic |
| Swing | CNC (no leverage) or a defined-risk option spread | Gap risk |
| MCX | Mini or micro futures, **all lots batched in one order** | Fixed ₹20 brokerage dominates small orders |

**Leverage in practice.** Notional ÷ equity = R% ÷ stop%. With R = 0.5% and a 0.5% stop, that is 1x. Reaching 4x needs a 0.125% stop, which fails the friction gate. **Expect 1–2.5x gross.** 4x is a cap, not a target.

**Brokerage.** Upstox Plus at ₹30/order versus Zerodha at ₹20 is about a ₹10/order difference. At 10 round trips a day that is about ₹59k a year, roughly 6% of capital.

---

## 6. Risk framework (₹10L)

| Rule | Value |
|---|---|
| **Daily loss limit (DLL), hard** | **2% = ₹20k**, realized plus MTM. Flatten and lock for the day. |
| Catastrophic ceiling | 3% = ₹30k, reachable only through gaps or slippage. Trips the kill switch; manual reset the next day. |
| Soft warning | −1.2%: size 0.5x, A+ setups only. |
| **Open-risk invariant** | `realized_today + Σ open_risk_i + new_risk ≥ −0.9 × DLL`, where `open_risk_i = qty × \|LTP − stop\| + est_exit_cost`. |
| R per trade | Intraday ≤ 0.5% (₹5k), **0.25% for the first live month**. Scalps 0.25% (₹2.5k). Long options ₹5k (₹3k on expiry day), with premium capped so that cap% × premium ≤ 2R. |
| Stop-distance floor | ≥ max(0.25% × price, 0.15 × ATR14 daily, 3 × median spread + 2 ticks), **and** friction ≤ 0.2R |
| Open risk / concurrency | ≤ 1.5% total. At most 4 intraday positions plus 2 scalps, and at most 3 in the same direction with beta > 0.8. At most 2 per sector. |
| Exposure | Gross 3x normal, **4x hard**. Per symbol ≤ 1.2x equity. Keep ≥ 20% free margin. |
| Index exposure | Beta-weighted Nifty-equivalent delta ≤ about ₹12–15L, sized by a stress test: a 1.5% move plus a 30% IV move must fit in the remaining DLL. |
| Module sub-caps (inside the global DLL, not additive) | Equity ₹12k · Options ₹8k · Scalping ₹5k while unproven · MCX ₹8k. The evening MCX budget is min(₹8k, remaining DLL − ₹2.5k buffer). |
| Risk day | The IST calendar date, from 09:00 to the MCX close. **One ledger across equity and MCX.** Equity profits never increase the MCX budget. |
| Overnight gap reserve | ≤ 0.75% (₹7.5k) total across equity swing and MCX positional, **carved out of** the next day's DLL. |
| Weekly / monthly | −4%: stop live trading for the rest of the week. −8%: halt, then 10 paper sessions and a written post-mortem. |
| Drawdown ladder | 5% / 8% / 12% from the high-water mark: size 0.75x / 0.5x / 0.25x. **15%: full stop and strategy review.** |
| Streaks | 3 losses in a row: 30-minute cool-off, then 2 trades at 0.5x. 4 losers in a day: intraday done. |
| Profit protection | Once the day's peak is ≥ ₹10k: no new entries below 60% of the peak; flatten at 50%. |
| Shared account with the options agent | A **combined ledger and DLL** (§13). |

**Hard rules.** These are code, never touched by the LLM, and changed only by owner-signed config outside market hours:
- The DLL and kill tiers.
- R caps and the open-risk invariant.
- A broker-side stop within 2–5 s of every fill, otherwise flatten.
- Never average down, never widen a stop.
- The flatten times.
- Universe exclusions.
- Limit orders only.
- Order-rate cap.
- Reconciliation halt.
- A stale feed blocks new entries.
- The LLM never creates orders.

**Soft parameters the LLM may tune, within bounds and logged:**
- Disable setups.
- Set a size multiplier between 0.25 and 1.0.
- Rank the watchlist and score materiality.
- Choose targets between 1 and 4R and the trailing method.
- Set time stops of 10–60 min.
- Turn scalping on or off.
- Nominate swing trades (the hard gates still apply).
- Supply the day-type prior.

---

## 7. Modules

### 7.1 Intraday equity: the anchor module

**Universe (rebuilt monthly from the Nifty 500):**
- **Tier A (scalp-eligible):** 20-day median turnover ≥ ₹300 cr, median spread ≤ 3 bps, F&O stock.
- **Tier B (momentum-eligible):** turnover ≥ ₹75 cr, spread ≤ 8 bps, price ₹100–10,000.
- **Hard exclusions:** ASM/GSM/ESM at any stage; T2T/BE series; fixed band ≤ 10%; listed less than 30 days ago; a corporate-action ex-date today.
- **F&O-ban names:** cash longs only, at 0.5x.

**In-play score (0–100).** Computed at 08:45, **09:12** (after pre-open), 09:30, 10:30, 12:30 and 13:30, and on any new filing.

| Component | Weight |
|---|---|
| Catalyst materiality (LLM score) | 25 |
| Gap ÷ ATR, measured from the pre-open price | 15 |
| Pre-open volume, plus futures pre-open imbalance | 10 |
| RVOL in the first 15 minutes | 15 |
| Relative strength vs Nifty and the sector | 10 |
| Location (PDH/PDL, range edge, 52-week high or ATH) | 10 |
| OI quadrant | 10 |
| Block/bulk deals, index events | 5 |

Penalties for: spread above threshold, a move already larger than 2.5 ATR, stale news.

**Output:** 5 primary names (max 8) with depth subscription, plus 10–15 watchlist names.

**Setups.** Phase 1 builds E1 and E2, then adds E3 once triage is validated in shadow. Every other setup is backlog and must earn its place through SPRT.

| Setup | Trigger | Stop | Exit |
|---|---|---|---|
| **E1: ORB retest / first pullback** (09:30–11:00) | In-play name, OR15 width 0.25–0.8 ATR, RVOL ≥ 2, relative strength aligned. A 5-min close beyond the OR on ≥ 1.5x volume, then the first retest that holds. | OR midpoint or retest low, ≤ 0.5 ATR | 1R / 2R, trail on VWAP. Time stop 45 min. |
| **E2: VWAP reclaim / reject** (after 10:00) | VWAP sloping in the trade direction, positive relative strength. A dip below VWAP reclaimed within 2 bars on rising volume. | Dip low or VWAP − 0.2 ATR | High of day, then extension. Auto-disable after more than 4 VWAP crosses in 30 min. |
| **E3: News-shock first pullback** | Catalyst score ≥ 7, move ≥ 1 ATR, RVOL ≥ 3. First pullback to VWAP, the 20-EMA or a 38–50% retrace, on volume below 60% of the impulse. | Pullback low − 0.1 ATR (skip if > 0.6 ATR) | 40% off at the impulse high, 30% at 2R, trail the rest. Time stop 20 min. |

**Backlog:** PDH/PDL acceptance; relative-strength divergence; gap-fill fade; results-day play (no new position in the 30 min before the board outcome, wait 3–5 min after); post-lunch range break. Full rules are in research report 03.

**Day-type timing fix.** ORB fires before a 09:45 classification exists. So use the **pre-market prior plus a provisional 09:30 label, at reduced size**, then confirm at 09:45 and 10:30.

### 7.2 Intraday options

| ID | Strategy | Key rules |
|---|---|---|
| **O1** | **Index level-break momentum (long options).** Nifty only, non-expiry days first. Add Sensex once it passes the liquidity whitelist. | Window 09:30–14:15. Day type is trend or breakout; IVP ≤ 70; no event within 30 min; VIX not up more than 8%. Trigger: 5-min close beyond OR or a plan level, on the correct side of VWAP, with futures volume ≥ 1.5x. Strike Δ 0.55–0.65. **Stop on the underlying**, plus a −35% premium catastrophe cap. Size by full repricing (research report 09 §2). 50% off at 1R; trail on 5-min swings; 20-min time stop. Use a debit-spread variant when the expected hold is over 45 min or IVP is above 60. OI is logged, not used as a gate. |
| **O2** | **Expiry-day afternoon iron fly or condor (hedged).** Nifty on Tuesday, Sensex on Thursday. | Entry 12:45–14:00 when the day is range-contained (RV/IV < 0.5), VIX is flat or falling, and spot sits between stable OI walls. 1–2 sets; max loss ≤ ₹8k per set. Margin check must include the extra ELM. Take profit at 50–60% of credit. Close a leg if spot is within 0.2% of its short strike at 14:30. **Shorts flat by 15:00.** Hedge leg placed first and closed last. Any order that would leave a short leg unhedged is vetoed. |
| **O3** | **Cash vs option shadow** (paper only) | Each triggered stock plan on a whitelisted name runs in both cash MIS and an R-matched ITM option. This measures with data when options beat cash. |

- **Deferred:** 0DTE momentum bursts (later, as an O1 variant at 50% size); non-expiry intraday condors; BankNifty monthly; live stock-option news trades.
- **Dropped:** selling after an IV spike; OTM directional buys; gamma scalping; max pain and GEX as signals; FinNifty and Midcap.

**Execution and safety rules:**
- Limit orders only, pegged from mid with a maximum chase.
- Spread filter: reject above about 0.5% of premium for index weeklies, 1% for stocks.
- Strike universe ATM ± 6.
- **Exits modify the resting SL order (cancel-replace).** This avoids a double-exit race that could open a naked short. A veto blocks any option sell whose quantity exceeds the net long position.
- No front-month stock options in expiry week (physical settlement).
- Expiry is detected from the contract master.
- IV and greeks are computed in-house from synchronized mid quotes against a synthetic forward, not taken from vendor greeks.

**Interaction with the existing options-selling agent.** That agent is short volatility. On a crash day, a short strangle and long stock positions lose together. If possible, give this system a read-only view of the other agent's positions for a combined stress test.

### 7.3 Scalping (3–10 min holds) and fast models

**Honest framing:**
- With snapshot feeds and current costs, **1–3 minute scalps are not viable**.
- Target **3–10 minute holds** on in-play Tier A names with stops of ≥ 30–40 bps, plus index-option scalps, which have about 10x better cost per unit of risk.
- Latency is not the binding constraint. These are:
  - friction relative to stop;
  - the 50-key depth-30 cap;
  - having no depth history.

**Engine:** deterministic setup state machines (primary signal) → **LightGBM meta-filter** (take or skip, plus size tier), trained only on depth we record ourselves with *executable* triple-barrier labels → risk → OMS.

**Features (robust on snapshot feeds):**
- order-flow imbalance (OFI) over 10/30/120 s
- distance-weighted depth imbalance, levels ≤ 10
- microprice (large-tick names)
- aggressor ratio inferred from volume deltas
- realized-volatility ratios
- VWAP distance
- distance to levels
- RVOL per minute
- spread regime
- sector relative strength

**Research-grade only:** index lead-lag (feed delays create fake lead-lag), wall persistence, absorption proxies.

**Setup backlog:**
- level breakout with flow
- absorption reversal at a wall
- VWAP reclaim momentum
- opening-drive continuation
- news-shock first pullback
- index-lead catch-up (paper only)

**Execution:**
- Marketable limit for momentum entries.
- Join, then chase once, for reversals.
- **Broker-side SL-limit within 1 s of the fill.** The target is managed in software (no native OCO).
- Measure post-fill adverse moves (markouts) and disable passive entries for a setup if they are bad.

**Phases:**
- **P0** record (weeks 0–2).
- **P1** candle research: kill any setup that is unprofitable at +2 bps of extra slippage.
- **P2** rules-only paper on depth-30 names (week 6+).
- **P3** ML:
  - dense flow model at about 30–40 sessions;
  - pooled meta-filter at 50–100 sessions;
  - weekly retrain with a 5-day shadow challenger;
  - drift alarms (PSI).
- **P4** live micro-size once the gate passes: ≥ 200 paper trades at ≥ +0.15R on conservative fills, PF ≥ 1.3, positive in 2 of 3 time-split thirds.

**On Jev.** Research found it is a real product: TypeSafe AI's "System One" typed-decision model, in early access since mid-Sep 2026. Vendor claims are 70–500 ms latency and typed outputs (choice, score or boolean) with probabilities. No independent benchmarks exist yet. Sources are in report 04.
- **Where it fits:** the `TextDecisionModel` port, for news and filing triage (material? direction? which symbol?). Run it in shadow against Haiku and score both by Brier score.
- **An experiment worth running:** feed it anonymized feature snapshots in shadow alongside LightGBM.
- **Why it is kept out of the numeric hot path:** validation, not latency. A zero-shot model is not calibrated to our data, can't be honestly backtested, and is non-deterministic. If it beats the alternatives on calibrated shadow metrics, it can be promoted to a gate, never to sizing.

### 7.4 MCX commodities

**The operations layer comes first and is mandatory:**
- **`contract_calendar` per expiry:** settlement type, tender start, broker cutoff, roll date, band ladder. The LLM parses MCX circulars and broker bulletins into it; code validates.
  - **GOLDPETAL and GOLDTEN are compulsory delivery:** exit one day before the broker cutoff.
  - **Roll energy contracts at expiry − 6 sessions**, because pre-expiry margin steps from 5% to 25% over the last 5 days.
- **Margin stress multiples:** silver 5x, gold 3x, energy 2x, plus the pre-expiry add-on. In Feb 2026 silver margin rose about 4.8x.
- **Locked-limit handling:** gold bands step 3% → 6% → 9% with a cooling-off. Silver locked at its 9% lower band in Feb 2026. A duty-cut shock means stops cannot fill, so position size is the only protection.
- **Event calendar** ingested from the source schedules (EIA holiday shifts recur), with time-zone conversion. The US daylight-time switch moves the MCX close from 23:30 to 23:55 on 2 Nov 2026.

**Contracts:**
- **CRUDEOILM:** core; 3–5 lots per order intraday, 1 lot positional.
- **GOLDPETAL:** positional only, ≤ 6 lots in one order.
- **GOLDTEN:** 1 lot positional.
- **SILVERMIC:** intraday, 1 lot only, because of lock risk.
- **SILVER100:** positional, 2–3 lots, only if liquid.
- **Avoid:** standard lots, GOLDM/SILVERM, natural gas positional, base metals for now.

**Phase-1 strategies (paper):**
- **C1, daily trend (positional).**
  - Entry: Donchian-20 breakout, EMA50 slope, ADX > 20.
  - Exits: 2.5 ATR initial stop, then a 3 ATR chandelier.
  - No Friday entries and no entries within 6 sessions of expiry.
  - Size = min(stop-risk size, gap-risk size, margin-stress size).
  - Validate on 10+ years of bhavcopy data. Backtests flatter long bullion because of INR depreciation (83 → 95.6) and the duty step (6% → 15%), so check shorts and a USD-denominated series separately.
- **C2, evening session breakout on CRUDEOILM.**
  - Risk ≤ ₹3k; stop ≥ 0.5%.
  - Window opens at max(18:15, event + 15 min).
  - Skip Wednesdays (EIA); 1 trade a day.
  - No international-price filter.
- **C3, EIA protocol.** Flatten and black out from T−10 to T+5. It runs as risk control from day 1; the trading variants stay paper-only.

**Dropped:** MCX scalping; global-lead catch-up and the 09:00 gap fade; EIA fade; options on CRUDEOIL, NATURALGAS and silver. CRUDEOILM options are used only as hedges.

**Data and broker:**
- Free delayed international prices are enough for regime work. Paying for CME live data (about 2% of capital a month) is not justified.
- Self-record MCX ticks, or buy vendor 1-minute history.
- MCX square-off: Upstox 22:50 (US summer time) / 23:25 (winter), Zerodha 23:20 / 23:45. **The system's time stop is 22:40 / 23:15.**
- Daily 2FA means no unattended start. Re-arm overnight stops at 09:00:05. If price has already gone through the stop at the open, send a protected marketable exit.

### 7.5 Swing (exception path)

**Qualification (all must hold):**
- already ≥ +1.5R by 14:30, closing in the top 20% of the day's range on RVOL ≥ 2;
- a multi-day catalyst;
- above rising 20 and 50 DMAs, with the sector above its 20 DMA;
- VIX < 18 and not up more than 10% on the day;
- no binary event in the holding window;
- an explicit invalidation;
- **owner approval on Telegram.**

**Sizing:**

```
shock% = max(2 × P95|overnight gap| over 1y, floor)
         floor: large-cap 5%, mid-cap 7%, small-cap 10%; +2% if geopolitical score ≥ 2
qty = floor(min(0.5% E / (price × shock%), 0.5% E / (entry − stop)))
```

**Portfolio rule:** under a Nifty −4% gap scenario, the beta-adjusted total shock is ≤ the overnight reserve. At most 3 names.

**Rules:**
- **CNC only.** No leverage, no MTF.
- Holding period 1–5 days.
- Exit on a close below the 10 EMA.
- Cut the book by 50% before weekends when the geopolitical score is 2 or higher.
- Alternative: a defined-risk option debit spread.

**Protection:** SL orders on CAS stocks are cancelled at 15:15, and SL orders are not accepted in pre-open. Upstox GTT can't protect a held position. So positions are unprotected from the close to 09:15, and **sizing is the protection**.

---

## 8. Day type and time-of-day rules

**Deterministic classifier.** Inputs:
- OR30 ÷ ATR
- gap ÷ ATR
- Nifty 500 advance/decline ratio
- share of 5-min closes on one side of VWAP
- first-hour volume ratio
- VIX change
- Nifty vs BankNifty vs Midcap divergence
- index option OI shifts

The LLM supplies only a prior, and it may only downgrade the label (for example to `EVENT_WAIT`).

**Labels:** trend up/down · gap-and-go · gap-and-fade · range/rotational · dispersion · high-volatility event · compressed/pre-event. Each label has an allow/block setup matrix and a size multiplier (research report 03 §3). If the day is still unclassified by 10:00, run the top 2 setups at 0.5x.

| Window | Rule |
|---|---|
| 08:30–09:00 | Health checks (token, feed, margin, mapping). Any failure means a paper-only day. |
| 09:00–09:12 | No orders. Read the pre-open indicative price and imbalance, and finalise the in-play list at 09:12. |
| 09:15–09:25 | Observe and build the opening range. No discretionary entries. |
| 09:25–11:30 | Main trend window. All setups allowed, subject to day type. |
| 11:30–13:15 | Lunch chop. No breakouts and no scalps; VWAP and fade setups only. |
| European open (12:30 IST until 25 Oct, then 13:30) | Re-run the day-type classifier. Post-lunch setups from 13:30. |
| 14:40 (CAS) / 14:50 (non-CAS) | No new entries. |
| 15:00 / 15:12 | CAS names flat / non-CAS names flat. |
| Expiry Tuesday | No index-lead scalps after 13:00. Expiry playbook applies (O2). |

---

## 9. LLM layer

**Roster.** The MVP uses only 1 and 2 (in shadow). The others are added when they beat the baseline.

| # | Agent | Model tier | When |
|---|---|---|---|
| 1 | Pre-market Strategist (with tools) | strong (Opus-class) | 08:30–09:05, refreshed at 09:12 |
| 2 | Filings/News Triage | fast (Haiku-class; Jev as challenger) | event-driven, after a rule pre-filter |
| 3 | Materiality Analyst (≤ 4 tool calls) | standard (Sonnet-class), escalating to strong | about 5–10% of items |
| 4 | Plan Writer | standard | per candidate, on events, on plan expiry; ≤ 3 plans per symbol per day |
| 5 | Intraday Re-assessor | fast, escalating to standard | when the delta gate fires, plus a 30-min backstop |
| 6 | Trade Critic | strong, **from a different vendor** | large-risk plans, swing candidates, and trades after 2 losses |
| 7 | Post-market Reviewer | standard per trade (batch) | 15:45–18:00 |
| 8 | Weekly Playbook Tuner | strong (batch) | Saturday. Proposes changes; the owner approves. |

**Principles:**
- **Monotone restriction:** the LLM can only narrow what the system does.
- Plans use level IDs.
- **Numeric grounding.** Every level ID must resolve. Stop < entry < T1 for longs (reverse for shorts). Entry within 1.5 ATR of LTP. Stop inside the setup's ATR band. **Net R:R to T1 ≥ 1.5 after costs.**
- **Prose fact-check.** Every number in the thesis must match a value in the situation report within ±2%.
- Structured outputs. One repair retry, then reject. An agent whose rejection rate exceeds 20% in a day is downgraded to advisory-only.
- **Day type is deterministic.** The LLM supplies a prior or a downgrade.
- **Re-assessment is triggered by a delta gate**, not a fixed 15-minute timer:
  - price moved > 0.5 ATR;
  - a new filing;
  - sector or Nifty moved > 0.4%;
  - plan validity has < 10 min left;
  - price is near the stop or target.
- **Critic protocol:** the critic first states its own stance without seeing the plan. If it disagrees with the plan, the plan is automatically downsized.
- **Context discipline.** Code computes every number; the LLM never sees raw ticks. Every block carries `as_of`, and a plan built on a situation report more than 120 s old is rejected. Stable content goes first so prompt caching works. Example situation report: research report 05 §2.
- **Prompt injection.** Scraped text arrives only as delimited, untrusted data. The triage model has no tools. Outputs must still pass deterministic gates.
- **Record every call** (prompt hash, model, tokens, cost, latency, output) for replay and audit, and keep it at least 5 years.
- **Budget guard with a degrade ladder.** At 80% of budget, strong-model calls drop to the standard model. At 100%, plan writing stops; only triage and exits continue.

**Cost estimates** (report 05; the red team notes these are slightly low):

| Profile | ₹/month |
|---|---|
| Lean | ≈ 9.5k |
| Lean+ (recommended once proven) | ≈ 11–13k |
| Standard | ≈ 23k |

**MVP target during paper: ≤ ₹5k a month.** That covers one pre-market brief plus Haiku-class triage.

**Leakage.** Current Claude models have a June 2026 training cutoff.
- Build the golden set from Jul–Oct 2026 filings: the Q1 FY27 results season, about 500 results plus other filings.
- Pre-cutoff history is fine for testing extraction accuracy, but not for testing prediction.
- The model registry stores each model's cutoff.

**Provider port** with capability flags (structured output, tools, caching, server web search, batch, effort control) and per-route config:

```yaml
llm:
  budget_inr_day: 250
  routes:
    triage:     {primary: anthropic/claude-haiku-5-5, challenger: typesafe/jev, fallback: rules, timeout_s: 8}
    strategist: {primary: anthropic/claude-opus-5-5, effort: high, max_tool_calls: 12}
    planner:    {primary: anthropic/claude-sonnet-5-5, effort: medium, on_fail: no_plan}
    critic:     {primary: openai/<model>, fallback: anthropic/claude-opus-5-5}
    review:     {primary: anthropic/claude-sonnet-5-5, mode: batch}
```

---

## 10. Architecture

**Style:** hexagonal (ports and adapters) around a deterministic, event-driven core, split into a hot plane and a cold plane (§3). Interfaces are sketched in research report 06 §1.

**Ports:**
- Market data: `Clock`, `MarketDataFeed`, `HistoricalData`, `InstrumentMaster`
- Trading: `BrokerExecution`, `PortfolioView`
- Information: `NewsSource`, `FilingsSource`, `FundamentalsSource`, `OptionsAnalytics`
- Models: `LLMProvider`, `TextDecisionModel` (Jev / Haiku / local), `FastModel` (LightGBM, synchronous, p99 < 200 µs)
- Infrastructure: `Notifier`, `EventStore`, `RawRecorder`

**Domain model:**
- **Canonical `InstrumentId`.** Examples: `NSE:EQ:RELIANCE`, `NSE:OPT:NIFTY:2026-10-13:25000:CE`, `MCX:FUT:CRUDEOILM:2026-10-19`. It maps daily to the Upstox `instrument_key` and the Kite token.
- Prices are int64 paise in the hot path.
- `OrderIntent` (strategy, broker-agnostic) is distinct from `Order` (owned by the OMS).
- A normalized order state machine: `PENDING_NEW → SUBMITTED → ACCEPTED → PARTIAL → FILLED`, plus `TRIGGER_PENDING`, `UNKNOWN → reconcile`, the cancel and amend paths, and `REJECTED` and `EXPIRED`.

**One engine, five profiles:**

| Profile | Clock | Feed | Execution |
|---|---|---|---|
| research | — | Parquet bars | vectorized (idea screening only) |
| replay | simulated | recorded raw frames | PaperBroker |
| paper-live | wall | live websocket | PaperBroker |
| shadow | wall | live websocket | PaperBroker + read-only real broker (margin and validation) |
| live | wall | live websocket | Upstox / Kite adapter |

**Look-ahead prevention:**
- Time comes only through `Clock`; `datetime.now` is banned by lint.
- Historical reads must pass `as_of`.
- Bars are emitted only after they close.
- Universe and reference data are point-in-time.
- LLM outputs are replayed from the recording; outputs regenerated later are labelled "contaminated".
- News uses our first-seen timestamp.
- CI gates: replaying a golden day twice must give an identical journal hash, and replaying each live-paper day must reproduce its signals exactly.

**Processes in the MVP:**
- `trader-core`: feed, features, setups, risk, OMS, portfolio and square-off, in one uvloop process.
- `recorder`
- `conductor`: daily lifecycle, token flow, reference data.

**Added later:** `intel-worker` (LLM agents), `api` (UI), and `deadman`, a separate process that flattens positions if the core's heartbeat is lost.

**Storage:** Postgres for append-only order events, fills, plans, journal and LLM calls, plus Parquet and DuckDB for ticks, depth and features. **Not in the MVP:** NATS, Loki, TimescaleDB, ClickHouse.

**OMS details:**
- Idempotent `client_order_id` encoded in the broker `tag`.
- The order is written to a log before it is sent.
- **No automatic resend on timeout:** the order goes to `UNKNOWN`, and the OMS looks it up by tag.
- Reconciliation every 5 s; the broker is the source of truth for positions.
- Naked-position invariant: every position must have stops covering its full quantity.
- An independent `Guardian` holds last-chance caps (max notional, max orders per minute).
- Four kill levels: pause entries → cancel working orders → flatten → lock.

**Technology:**
- Python 3.12 with uvloop.
- msgspec for hot-path events; pydantic for config and LLM I/O.
- numpy and numba for incremental features; polars, DuckDB and pyarrow for research.
- **Thin async broker adapters on httpx**, with our own websocket client. The SDKs serve as reference.
- structlog; pytest plus hypothesis for property tests of the order state machine.
- **No Rust:** internal compute is under 1% of a latency budget dominated by the feed and the broker.
- **Don't adopt NautilusTrader now.** Its v2 migration is in progress and it has no Indian adapters. Copy its patterns instead, and re-evaluate around Q1 2027.

**Plug-and-play mechanics:**
- **Composition root.** One function, `build_app(cfg)`, wires everything.
- **Plugin registry:** decorator registration plus entry points.
- **Capability negotiation:** each strategy declares `requires`, for example `depth>=20`. At startup it is checked against each adapter's `caps`, and the strategy either runs, falls back to a degraded variant, or refuses to start.
- **Adapter conformance suite:** one parametrized test set covering place, amend, cancel, partial fills, rejects, idempotent replay and reconnect. Every adapter (paper, Upstox, Kite) must pass it.
- **Swapping a component is a config change:**

```yaml
profile: paper                         # replay | paper | shadow | live
market_data: {primary: upstox_v3 (analytics_token), secondary: kite?}
historical:  upstox
execution:   {venue: paper, paper: {emulate: zerodha, fill_tier: conservative, books: [prod, baseline, vetoed]}}
llm:         {routes: ...}             # section 9
news:        [nse_filings, bse_filings, web_search: anthropic]
fast_models: {scalp_filter: {type: lightgbm, artifact: meta_v1, shadow_only: true}}
risk:        config/risk.yaml          # hard rules; loosening needs restart + owner sign-off
```

**Repository layout (proposed):**

```
src/trader/{domain,ports,core,marketdata,features,strategies,models,risk,oms,portfolio,intel,adapters,apps,ops}
research/   (notebooks, labelling, training; never imported by src)
tests/      unit · property (OMS FSM) · contract (adapter conformance) · golden_days
config/     base.yaml · profiles/ · strategies/ · risk.yaml · universe.yaml · costs.yaml
deploy/     docker-compose, chrony, grafana
```

---

## 11. Data plan

**Feed subscriptions** (Upstox Plus, 5 connections):

| Connection | Mode | Instruments |
|---|---|---|
| C1 | `full_d30` | ≤ 40–50 focus names plus index futures |
| C2 | `full` | ≤ 200 candidates and F&O underlyings |
| C3 | `ltpc` | Nifty 500, indices and VIX (for breadth) |
| C4 | `option_greeks` | Nifty and Sensex weekly ATM ± 10 strikes |
| C5 | — | Reserve (for the other agent, or a hot reconnect) |

**Bars.** Use the feed's own 1-minute OHLC fields, plus local sub-minute aggregates. Reconcile nightly against broker candles. Bars built only from snapshots miss highs and lows that happen between frames.

**Recorder:**
- **Bronze:** raw protobuf frames with receive time in nanoseconds, zstd-compressed, rotated every 15 min.
- **Silver:** nightly Parquet, partitioned by date and symbol.
- **Gold:** resampled bars and feature sets.
- About 1–2 GB a day compressed. Replicate to object storage daily and run a restore drill.
- Data-quality checks: levels per frame (some users get only 5 levels in d30 mode), crossed books, feed lag, gaps on reconnect.

**Historical data:**
- Upstox 1-minute bars since Jan 2022. **Weight post-Apr 2025 data more heavily**, because of regime breaks:
  - tick-size change (Apr 2025)
  - weekly-expiry consolidation (Nov 2024)
  - STT increase (Apr 2026)
  - closing auction (Aug 2026)
  - pre-open revision (Sep 2026)
- Expired F&O 1-minute data from about Oct 2024, with gaps.
- Kite Connect (₹500/month) as a cross-check and for MCX daily continuous series.

**Filings and news:**
- Poll NSE and BSE every 5–10 s in market hours, and every 30–60 s in the evening (results).
- Rule pre-filter for routine categories.
- Deduplicate by ISIN + subject + attachment hash.
- **Three timestamps:** exchange dissemination, article time, our first-seen time.
- Source tiers T0 (exchanges and regulators) to T3 (social media). T3 never triggers anything on its own.
- No trading on rumours in v1.
- Use XBRL for results numbers. Code computes ratios such as order value ÷ TTM revenue and % of market cap.
- Entity resolution with an alias table.

**Reference data, daily at 07:30:**
- Upstox and Kite masters, built into a canonical mapping.
- Ban list; ASM/GSM/ESM lists; T2T series; price bands.
- Tick size, lot size, freeze quantity.
- Holiday and session calendar; cost tables.
- **If any watchlist symbol fails to map, the system refuses to trade.**

---

## 12. Paper trading and evaluation

**Fill tiers:** optimistic, base and **conservative**. Decide only on conservative, and reject any strategy that is profitable only on the optimistic tier.
- **Marketable orders** walk the depth-30 book seen at arrival, using 70% of displayed size, with a liquidity ledger so the same displayed size can't be consumed twice.
- **Passive limits** fill only on a trade-through or when the queue ahead is used up.
- **Latency** is lognormal, median about 150 ms and p95 about 450 ms, to be calibrated.
- **Broker behaviour is emulated:** the market-protection remainder; SL-limit orders that a gap can skip; the 15:15–15:20 CAS freeze; broker square-off with its fee; fault injection (rejects, feed gaps, reconnects, token expiry).

**Counterfactual books, free in paper:**
- **A:** production.
- **B:** ungated baseline, with no LLM and no day-type filter.
- **C:** trades the LLM proposed and risk vetoed.

Paired daily differences give the **uplift of the LLM and of each filter**.

**Live 1-share probes during the paper phase:**
- 20–40 orders a day, once the live account and static IP exist.
- They calibrate latency, fill probability, market-protection behaviour and rejection codes.
- Paper counts as calibrated when:
  - median live-minus-paper shortfall ≤ 0.03R
  - live/paper passive fill-rate ratio is 0.85–1.15
  - live/paper latency p95 ratio ≤ 1.3

**Statistics.** Per-trade σ is about 1.1R. To prove an edge of 0.15R:
- about 207 trades for a 95% confidence interval;
- about 333 trades for 80% power;
- with SPRT, about 205 trades on average if the edge is real, and about 144 if it is not.

**4–6 weeks of paper proves the plumbing; 8–12 weeks is needed for a go/no-go on 2–3 setups.**

**Go-live gate, paper → live L1 at 25% of R** (all of these):
- ≥ 40 trading days.
- SPRT accepts on the conservative tier, or ≥ 200 trades with a bootstrap 90% CI lower bound above 0.
- Expectancy ≥ +0.10–0.15R, profit factor ≥ 1.25–1.3, max drawdown ≤ 6%.
- Still positive after removing the best 5% of trades, and with +1 tick per side.
- Zero risk breaches and zero unreconciled orders in the last 20 days.

**L1 → L2 → L3:** each step needs ≥ 20 days and ≥ 80 trades, live not significantly worse than its shadow twin, and an average slippage gap ≤ 0.05R.

**Kill criteria:**
- a setup's rolling 50-trade expectancy below −0.1R, or a CUSUM alarm;
- live-minus-paper gap > 0.1R over 30 trades;
- feed stale for more than 5 s with open positions (flatten);
- an unknown reject code or a reconciliation mismatch (halt).

**Discipline:**
- Freeze parameters for each evaluation window.
- Keep a registry of every variant tried, and report the deflated Sharpe ratio.
- No more than one adaptive loop changing at a time.

---

## 13. Broker and account topology (owner decision needed)

**The problem.** Upstox allows **one active API app per user**, and a new token can expire the previous one. Static IP, the order-rate cap, websocket connections, depth-30 slots and REST limits are all per account. If the existing options agent uses the same Upstox account, the new system could **blind it or kill its session**.

**Option A (recommended):**
- **Data** comes from Upstox through the **Analytics Token**, after confirming in writing with Upstox that it doesn't affect the existing app or token.
- **Execution** goes through a **separate Zerodha account** with its own capital:
  - The Personal API is free for orders, at ₹20 per order.
  - Single-leg GTT can protect held positions.
  - Margin, kill switch and order-rate budget are isolated from the other agent.
- Optionally, Kite Connect (₹500/month) adds a second feed and MCX data.

**Option B:** a shared Upstox broker-gateway service owns the app, token, static IP and order-rate budget for both agents. It couples the two agents and requires a combined risk ledger.

**Option C:** a separate Upstox account, for example in a family member's name under the family-IP rule. This is operationally and legally more complex.

**Paper phase:** only option A's data part is needed. No daily login, no static IP.

**Daily login (live only):**
- Upstox: token-request approval on your phone (around 08:00–08:50).
- Kite: manual TOTP login.
- No token by 09:05 means a paper-only day.
- Never store TOTP seeds.

---

## 14. Operations

**Daily lifecycle:**

| Time | Step |
|---|---|
| 07:30 | Reference data and mapping |
| 08:00 | Token request (live only) |
| 08:30 | Pre-market brief |
| 09:12 | In-play list finalised; subscriptions tiered |
| Market hours | Trading |
| 14:40 / 14:50 | Entry cutoffs |
| 15:00 / 15:12 | Flatten |
| 15:45 | End-of-day reconciliation, P&L after charges, journal, review, backups |
| Evening | MCX session until the time stop |

**Hosting:**
- **Paper:** home or any VM. A home connection is better for NSE filings access.
- **Live:** a Mumbai-region VM with an Elastic IP, plus a pre-registered backup IP and a standby VM. chrony time sync with alerts at 50 ms and a halt at 250 ms.

**Security:**
- Secrets in sops/age-encrypted files, never in YAML.
- Telegram: chat-ID allowlist, PIN, **tighten-only commands**, separate bots for alerts and for commands.
- Unsigned broker webhooks are verified by calling the API with the received token.
- Every human override is audit-logged.

**Runbooks:**
- **Broker outage:** rely on exchange-resident stops, the broker's app and its call-and-trade desk. Rehearse it.
- **Special sessions** (Muhurat, DR drills, special pre-open): the system is disabled by default.
- **Corporate actions on ex-dates:** adjust previous close and VWAP anchors.

**Compliance and tax:**
- Retain order and LLM logs for at least 5 years.
- Tag every fill with a tax bucket: SPEC (intraday cash), NONSPEC (F&O and commodities), STCG/BUSINESS (delivery).
- Compute ICAI turnover per bucket, combined across both agents if they share a PAN.

---

## 15. Roadmap

| Phase | When | Build | Exit criterion |
|---|---|---|---|
| **0: Foundations and recorder** | weeks 0–2 | Domain, ports, config, clock; instrument master and canonical mapping; session, holiday and cost tables; Upstox V3 feed on the Analytics Token; **recorder live**; data-quality dashboard | 10 clean recorded sessions; 30 levels confirmed; feed-lag distribution known |
| **1: MVP paper, unattended** | weeks 2–5 | Features; in-play selector; day-type labeller; conservative paper broker; OMS and risk; **E1 + E2**; Telegram alerts and kill switch; daily report; counterfactual books; **LLM pre-market brief + triage in shadow** | A full unattended paper day; replay parity 100% |
| **2: Live plumbing and module expansion** | weeks 5–8 | Live execution adapter on the chosen account, with **1-share probes**; reconciliation; dead-man process. LLM gating A/B test. E3 news-shock. **O1 in paper.** Rules-only scalping paper on depth-30 names. **MCX operations layer plus C1–C3 in paper.** | 2 weeks with zero reconciliation breaks; probes calibrating |
| **3: First live** | weeks 10–14 | Setups that pass SPRT go live at 25% of R. O2 expiry-day in paper, then through its gate. | Gates in §12 |
| **4: Expansion** | months 4–6 | Scalping ML filter (after 60+ recorded sessions); index-option scalps; swing module; MCX live; Jev and Haiku triage champion/challenger | Per-module gates |

---

## 16. Open questions for the owner (with recommended defaults)

1. **Account topology (§13).** Is the existing options agent on the same Upstox account and app? Will you fund a separate Zerodha account for this system's execution? *Default: yes to both; option A.*
2. **Upstox plan details.** Is your brokerage on Plus ₹30 per order (check a contract note)? Does the other agent use any of the 50 depth-30 slots? Is it OK to generate an Analytics Token? *Default: confirm with Upstox first.*
3. **Risk limits.** 2% hard DLL with a 3% catastrophic ceiling; R of 0.5% (0.25% in the first live month); 15% maximum drawdown shutdown. *Default: as proposed.*
4. **Shorts.** Intraday shorts in F&O stocks only? *Default: yes.*
5. **Options in this system.** Long index options (O1) and the hedged expiry-day iron fly (O2), given that the other agent already sells options? *Default: O1 yes; O2 paper first, with a combined-exposure check.*
6. **MCX.** Is positional holding allowed with the gap reserve? Is it OK to trade unattended until 22:40/23:15? Which broker for MCX? *Default: yes, small size; Zerodha if Upstox MCX API trading is off.*
7. **Swing.** CNC only, with your approval for every overnight hold? *Default: yes.*
8. **Monthly operating budget** (LLM + infrastructure + data)? A paid news or consensus feed? *Default: ≤ ₹10k during paper; no paid feeds yet.*
9. **Availability.** Can you approve the token around 08:30 on live days? Approvals are needed only for swing and overnight trades. *Default: yes; otherwise a paper-only day.*
10. **Hosting.** Paper at home, live on a Mumbai VM with a static IP? *Default: yes.*
11. **Jev.** Do you have early access, or did you mean something else? *Default: start with Haiku for triage and add Jev as a shadow challenger.*
12. **Timeline.** 8–12 weeks of paper before live equity; 4–6 months before live scalping? *Default: yes.*
13. **Manual trading** in the execution account? *Default: no. Untagged orders halt new entries.*

---

## 17. Research index

| # | Report | Topic |
|---|---|---|
| 01 | [broker-apis-upstox-zerodha](../research/01-broker-apis-upstox-zerodha.md) | Feeds, orders, history, auth, limits, capability flags |
| 02 | [regulation-margins-costs](../research/02-regulation-margins-costs.md) | SEBI algo rules, F&O structure, margins, cost math, tax |
| 03 | [trading-playbook-and-risk](../research/03-trading-playbook-and-risk.md) | Risk math, universe, day types, setups, swing, time of day |
| 04 | [scalping-engine-fast-models](../research/04-scalping-engine-fast-models.md) | Microstructure features, ML, recorder, execution, Jev |
| 05 | [llm-agent-layer](../research/05-llm-agent-layer.md) | Agents, context, schemas, providers, cost, evaluation |
| 06 | [architecture](../research/06-architecture.md) | Ports, domain model, runtime, OMS, ops, repo layout |
| 07 | [paper-broker-and-evaluation](../research/07-paper-broker-and-evaluation.md) | Fill models, realism, calibration, statistics, gates |
| 08 | [red-team-core-system](../research/08-red-team-core-system.md) | Contradictions, risks, gaps, MVP |
| 09 | [intraday-options-module](../research/09-intraday-options-module.md) | Index and stock options intraday |
| 10 | [red-team-intraday-options](../research/10-red-team-intraday-options.md) | Corrections and build order for options |
| 11 | [mcx-commodities-module](../research/11-mcx-commodities-module.md) | MCX contracts, sessions, playbooks, costs |
| 12 | [red-team-mcx-commodities](../research/12-red-team-mcx-commodities.md) | Corrections and build order for MCX |

*Facts are as of 2026-10-08. Several are tagged medium or low confidence in the research and are marked "verify" here. Recheck them during Phase 0, because rules changed 7 times in the past 8 months.*
