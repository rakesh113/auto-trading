# LLM Trader Decision Process: "Plan the trade, trade the plan"

**Role:** senior NSE intraday discretionary trader and agent designer. **Tags:** facts carry (source, H/M/L confidence); my judgment carries [J].

## 0. Design stance

1. **Most of a good day is decided before 09:15.** That means picking which 5–8 names to trade, which side, at which levels, and what would prove me wrong. The most valuable LLM call is therefore the pre-market plan, not the intraday click. [J]
2. **Latency must never decide P&L.** There are two ways to get there. The LLM can decide *before* the trigger (a heads-up call that produces an armed order). Or the entry tactic can rest at a level price comes back to. A 20-second think on a momentum chase guarantees a bad fill. [J]
3. **The LLM adjusts a base rate.** Code gives it the scenario's history ("n=184, win 47%, +0.27R net"). The LLM says why today is better or worse. Pros work this way, and it makes every decision measurable. [J]
4. **The default is PASS.** A pro takes 3–6 trades from about 30 looks, so the target take rate is 15–30%. [J]
5. **Hard rules stay in code** (sizing, daily lock, stops, flatten times). The LLM is never given a control that can widen risk.

**Budget frame.** ₹5–7k a month ÷ 21 days ÷ ₹95 = **$2.5–3.5 a day (₹240–330)**.
- Prices (claude-api reference cached 2026-10-06, H), per million tokens:
  - Opus 5.5: $4 in / $20 out, cache read $0.20
  - Sonnet 5.5: $2 / $10, cache read $0.20
  - Haiku 5.5: $0.10 / $0.50
  - Fable 5.1: $10 / $50
- Routing that follows from this:
  - **Opus for the pre-market plan.** Depth matters there and latency does not.
  - **Sonnet 5.5 for decision moments.** About ₹1.6 per call: 6k cached + 2k fresh input, about 1.2k output including thinking.
  - **Haiku for triage and routine management.**
  - **Fable stays out of the initial budget.**

---

## 1. The trader's day as an agent loop

| IST | Step | LLM output | Model, ≈₹/day |
|---|---|---|---|
| T-1 18:30–20:00 | Batch prep from tomorrow's results calendar, FII/DII provisional figures, participant-wise OI, bulk/block deals and after-hours filings | `WatchlistSeed`: about 25 names, each with a reason | Sonnet batch (−50%), 8 |
| 07:45–08:30 | **Code only:** GIFT Nifty, US close, Brent, USDINR, story clusters, filings since 15:30, in-play score | — | 0 |
| 08:30–09:05 | **Strategist** (≤10 tool calls) | `MarketThesis`, `DayTypePrior`, 5–8 `GamePlan`s, `AvoidList`, `ChartContext` | Opus 5.5 high, 55 |
| 09:08–09:14 | **Code only:** compare the pre-open IEP and futures imbalance with the plan's assumptions | Scenarios marked VALID/INVALID (for example, gap larger than the plan's maximum) | 0 |
| 09:15–09:24 | **Observe; no entries.** Code builds the opening drive, OR, RVOL and breadth | — | 0 |
| **09:24** | **Open read**: one call covering all names | Confirm, kill or re-rank scenarios; approve arming | Sonnet, 4 |
| 09:25–11:30 | **Prime window** | `TradeDecision`, `PositionUpdate` | Sonnet / Haiku |
| 11:30–13:15 | **Lunch.** Bar raised to A+; range and VWAP-reversion tactics only; **12:15 re-plan** | Refreshed plans and post-lunch scenarios | Sonnet, 4 |
| 12:30 (13:30 after the EU clock change on 25 Oct) | European open: day type re-run | Afternoon bias; names marked "done" | Sonnet, 4 |
| 14:30 | Swing checkpoint (gates in code, plus the Critic) | Hold or flat | Sonnet, 2 |
| 14:40 / 15:00 / 15:12 | No new entries / CAS names flat / non-CAS names flat (design §4, M) | — | 0 |
| 15:45–17:00 | Batch review of trades **and passes**, with shadow outcomes | `DailyDebrief`, ≤3 lessons | batch, 30 |
| 16:45 | **MCX evening plan** (§8) | — | Sonnet, 5 |

**`MarketThesis`** contains:
- A narrative of at most 120 words.
- Day-type probabilities.
- Sector lead and lag.
- A "flip condition", for example "Nifty reclaims L.PDH with A/D > 1.5".
- Book posture: maximum long and short beta.

Today's tape fits a short-default stance. Nifty is near a 6-month low after 8 down weeks, and FIIs have been net sellers for 15 months (research 03 F13, M). So shorts in weak sectors are the default, and **longs need a stock-specific catalyst**.

**`GamePlan` per stock** (sketch):
```yaml
symbol: BEL   bias: LONG_ONLY   why: "₹2,410cr order = 9.8% TTM rev; IEP gap +1.1 ATR"
levels: [L.PDH, L.W52H, L.ORH15, L.VWAP, L.GAPFILL]
scenarios:
 - id: S1  name: base-top acceptance  mode: ARMED  window: [09:30, 10:45]
   if:  [{m: close, tf: 5m, op: ">", ref: L.ORH15}, {m: rvol, op: ">=", v: 2}, {m: nifty_ret_open, op: ">", v: -0.4}]
   then: {tactic: BREAK_RETEST, stop: {ref: L.ORMID}, tier: A, targets: [L.R_RND:40, 2.5R:30, trail VWAP_5M:30]}
   kill_if: [{m: nifty_vs_vwap_atr, op: "<", v: -0.3}]
 - id: S2  failed break, reclaim of L.PDH (FAILED_BREAK_RECLAIM, CONFIRM)
 - id: S3  "do nothing": open > +1.9 ATR and OR15 > 1 ATR → priced in, AVOID
```
Every plan also states **"what makes this stock not worth watching today"**. The `AvoidList` covers results due today before the outcome, F&O ban, ASM/GSM, spread above the tier limit, and moves already larger than 2.5 ATR.

**Special days**

| Day | What changes |
|---|---|
| **Nifty weekly expiry** (Tuesday) and **Sensex** (Thursday) | Dates come from the contract master; holiday shifts apply, such as Mon 9 Nov (research 09, H). Plans include pin zones at the max-OI strikes. No heavyweight breakout scenarios after 13:00. Option buys roll to the next weekly. A 12:45 iron-fly checkpoint answers YES/NO. |
| **Monthly expiry** (last Tuesday; stock F&O) | No fresh positions in high-OI F&O stocks after 14:00. Rollover percentage goes into the thesis. No front-month stock options in expiry week. |
| **A focus stock's own results** | The plan holds a **pre-written results tree**: IF EBITDA vs consensus ≥ +5% and margin up → continuation scenarios; IF a miss → short scenarios. No position in the 30 minutes before the outcome. The first decision comes at least 3–5 minutes after the filing (research 03 S7, M). |
| **Event days** (RBI 10:00, Budget, overnight US CPI/FOMC) | `EVENT_WAIT` until the event + 15 minutes. Tier capped at B. Option buys only after the IV move. |
| **Flow days** (index rebalance, MSCI/FTSE; block windows 08:45–09:00 and 14:05–14:20, [SEBI Oct 2025](https://www.business-standard.com/amp/article/pti-stories/sebi-revises-block-deal-norms-min-order-size-hiked-to-rs10-cr-117102601023_1.html), M) | Never fade closing flows. A block deal in a focus name counts as a moment. |
| **Results season (now)** | Materiality escalations double; the budget reserve is spent here. |

---

## 2. Decision moments

| # | Trigger (code-detected) | LLM decides | Deadline | Per day (5–8 names + index) |
|---|---|---|---|---|
| M1 | A scenario `if` becomes true | ARMED: post-fill check only. CONFIRM: take, pass or adjust within bounds | min(30 s, price leaves zone ±0.25 ATR) | 6–10 |
| M2 | **Heads-up:** price within 0.3 ATR of a trigger, or 1 of 2 conditions true | Pre-decide: arm or not, and the bounds | Before the trigger, typically 2–10 min | 8–12 |
| M3 | Unplanned level test (PDH/PDL, OR, weekly level, round number) with RVOL ≥ 1.5 | Write a new scenario or ignore | 60 s | 3–5 |
| M4 | Breakout failure: break ≥ 0.15 ATR, then a 5-min close back inside within 2 bars | Trapped-trader reversal? | 30 s | 2–4 |
| M5 | First VWAP test after a trend leg; reclaim or reject on rising volume | Continuation entry? | 45 s | 3–5 |
| M6 | RS divergence: stock vs Nifty or sector ≥ 0.4% over 15 min; or the leader stalls | Promote or demote; add a scenario | 2 min | 2–3 |
| M7 | Filing or news with triage materiality ≥ 6 | New in-play? Thesis change? Exit? | 60–120 s (results: wait 3–5 min first) | 1–3 (results season 3–6) |
| M8 | Volume or OI shock: 1-min volume > 5× average; futures OI ±3% in 15 min | Who is trapped? Act or watch | 60 s | 1–3 |
| M9 | Index regime shift: day-type label flips, Nifty breaks OR or PDH/PDL, VIX +8% | Book level: tighten, flatten, flip bias, disarm | 60 s | 1–2 |
| M10 | Position events (§5) | `PositionUpdate` | 30–60 s | 15–25 |
| M11 | Checkpoints: 09:24, 12:15, European open, 14:30 | Re-plan | 2 min | 4 |

**Code filters before waking the LLM:**
- Focus or watch names only.
- The window must be allowed for the current day type.
- One open moment per symbol.
- A 10-minute cooldown after a PASS, unless new information arrives.
- A friction pre-check.
- Book capacity: at most 8 entries a day and 3R of open risk.

The result is about 80–120 raw candidates, which become **25–40 entry-side calls, 15–25 management calls and 4 checkpoints, roughly 50–65 calls a day.** [J]

---

## 3. The decision contract

```jsonc
// TradeDecision (structured output; numeric bounds validated in code)
{ "moment_id": "M-1012-0947-BEL-S1",
  "action": "TAKE|ARM|WAIT_FOR|PASS",
  "pass_reason": "NO_EDGE|CHASING|INDEX_AGAINST|PRICED_IN|POOR_LOCATION|EVENT_RISK|ROOM<2R|BOOK|OTHER",
  "direction": "LONG|SHORT",
  "instrument": {"kind": "CASH_MIS|INDEX_OPT_LONG|INDEX_DEBIT_SPREAD|IRON_FLY_EXPIRY|STOCK_OPT_ITM|MCX_FUT", "underlying": "NSE:BEL"},
  "tactic": {"id": "BREAK_RETEST", "params": {"max_entry": {"ref": "L.ORH15", "off_atr": 0.15}, "cancel_after_bars_5m": 3}},
  "wait_for": [ /* condition DSL, for WAIT_FOR / ARM */ ],
  "stop":   {"ref": "L.ORMID", "off_atr": -0.05},          // or {"struct": "RETEST_LOW"|"SWING_5M_LAST"}
  "targets": [{"ref": "L.R_RND", "pct": 40}, {"r": 2.5, "pct": 30}, {"trail": "VWAP_5M_CLOSE", "pct": 30}],
  "horizon": {"time_stop_min": 45, "flat_by": "11:30"},
  "size_tier": "A_PLUS|A|B|PROBE",                          // 1.0 / 0.75 / 0.5 / 0.25 × R
  "setup_class": "CATALYST_CONTINUATION|OPENING_DRIVE_PULLBACK|TRAPPED_FAILED_BREAK|RS_LEADER_TREND|VWAP_REVERSION_RANGE|RESULTS_SECOND_LEG",
  "base_rate": {"n": 184, "exp_r": 0.27}, "my_p_t1": 0.55, "adjust_reasons": ["sector rank 1", "long buildup"],
  "checklist": {"catalyst_or_rs": true, "defined_risk_location": true, "index_with_me": "NEUTRAL",
                "priced_in": 0.55, "chasing": false, "room_r": 1.55, "time_window_prime": true},
  "invalidations": [{"m": "close", "tf": "5m", "op": "<", "ref": "L.VWAP", "hard": true},
                    {"m": "rs_nifty_15m", "op": "<", "v": 0, "hard": false}],
  "thesis": "≤300 chars; numbers must match sitrep ±2%",
  "change_my_mind": "Nifty loses VWAP by 0.3 ATR or 5m close back under L.PDH",
  "expires_at": "10:05" }
```
**Condition DSL**
- Shape: `{m, tf?, op: < <= > >= crosses_up crosses_dn, ref (level ID) | v, off_atr?, for_bars?}`.
- Metrics: `ltp`, `close`, `vwap_dist_atr`, `rvol`, `rs_nifty_15m`, `rs_sector_15m`, `nifty_ret_open`, `nifty_vs_vwap_atr`, `vix_chg`, `depth_imb_top5`, `oi_chg_15m`, `time`, `pnl_r`, `mfe_r`, `bars_since_entry`.
- Code evaluates every condition. A **hard** invalidation exits automatically; a **soft** one wakes the LLM.

**Code overrides and rejections**
- Code recomputes the objective checklist items: chasing, room, friction, index state.
- If the LLM claims something code contradicts, the decision is rejected.
- The size tier can only be lowered, by the day-type multiplier, the drawdown ladder or cooldowns. It is never raised.

```jsonc
// PositionUpdate
{ "position_id": "...", "event_id": "E-+1R", "action": "HOLD|TIGHTEN_STOP|PARTIAL|EXIT|ADD_PLANNED|EXTEND_TIME_ONCE",
  "new_stop": {"ref": "L.SWL5_1"}, "partial_pct": 33, "thesis_status": "INTACT|WEAKENING|BROKEN",
  "evidence": "rs_nifty_15m +1.2→-0.1; Nifty lost VWAP", "reason": "≤200 chars" }
```

**Entry tactics menu** (code executes precisely; level IDs resolve to prices)

| ID | Logic | Latency tolerance | Default mode |
|---|---|---|---|
| T1 PULLBACK_LIMIT | Resting limit in a zone (VWAP, level, 5m EMA20 ± band); cancel if price runs 0.5 ATR away or time expires | High | CONFIRM |
| T2 BREAK_RETEST | 5m close beyond the level on ≥ 1.5× volume, then a limit at the level + 0.05–0.1 ATR on the retest; the 1m close must hold | Medium | ARMED / heads-up |
| T3 OR_ACCEPTANCE | Two 5m closes beyond OR15/OR30 and 3 minutes holding beyond; marketable limit, cap 0.1 ATR | Low | ARMED |
| T4 FAILED_BREAK_RECLAIM | Break ≥ 0.15 ATR, reclaim within 2 bars; stop beyond the failed extreme | Medium | CONFIRM |
| T5 MOMENTUM_CHASE_CAPPED | Marketable limit, chase ≤ min(0.15 ATR, 8 bps), own slicer | None | **ARMED only** |
| T6 VWAP_RECLAIM_REJECT | Cross back within 2 bars on rising volume; enter on the first 1m pullback hold | Medium | CONFIRM |
| T7 OPENING_DRIVE_PULLBACK | After 09:25, a 38–50% retrace of the opening drive on volume below 60% of the impulse | High | CONFIRM |
| T8 RANGE_EDGE_FADE | Day type RANGE only, lunch allowed; limit at the range edge | High | CONFIRM |
| T9 SCALE_IN_2 | 50% at the zone top, 50% at the bottom, one stop sized on the blend | High | CONFIRM |

Index options use the same tactics on the Nifty level. Code converts the signal into the option order.

---

## 4. Situation report at a decision moment (example, about 900 tokens, illustrative values)

```
#SITREP M-1012-0947-BEL-S1 as_of 09:47:12 trigger HEADS_UP S1 (ltp 0.08ATR below L.ORH15) deadline 09:52|ltp>ORH15+0.3ATR
MARKET NIFTY 22,742 -0.21% vwap_dist -0.1ATR | daytype prov RANGE .55 TREND_DN .30 | A/D 0.82 | VIX 14.1 +2.4%
  sector NIFTY_PSE +0.9% (1/14) | defence basket +1.6% | next Nifty expiry Tue 13-Oct (not today)
STOCK BEL ltp 412.6 ATR14 9.8 (2.4%) TierA CAS yes ban no
 LEVELS id:px(dATR) ORH15 413.4(+.08) PDH 408.9(-.38) VWAP 409.7(-.30) ORMID 409.3 ORL15 405.2(-.76)
        R_RND 420(+.76) W52H 421.0(+.86) GAPFILL 401.6(-1.12)
 DAILY uptrend >rising 20/50DMA; 6-wk base 388-418; today = base-top test   CHARTCTX base_breakout, no overhead <W52H
 60m HH/HL since 01-Oct | 5m opening drive +1.9%, pullback 38% to 408.6 on vol .45x impulse, 3 rising bars
 VWAP +1σ 413.9 +2σ 417.6 | RVOL15 3.4 | RS vs NIFTY 30m +1.6%, vs sector +0.7% | profile VAH 412.8 POC 410.1
CATALYST 08:12 NSE filing "orders ₹2,410cr" materiality 74 | 9.8% TTM rev, 3.1% order book
  since t0 +2.9% (1.2ATR); class median move 1.8ATR → 66% realised; priced_in .55; no other news 5d
FLOW fut OI +4.1% w/ price↑ (long buildup) | call OI wall 420 (2.1x), puts building 400 | ask refills ×3 at 413.4
  depth10s top5 bid/ask 1.6, spread 3bps
PLAN S1 base-top acceptance → BREAK_RETEST, stop ORMID, tier A, T: R_RND 40% / 2.5R 30% / trail VWAP_5M 30%, tstop 45m
  bounds: entry ≤ ORH15+0.15ATR; stop ≤ 0.45ATR
  BASE RATE backtest 2024-26 (in-play, gap .5-1.5ATR, OR break, RVOL≥3, conservative fills): n=184 win 47% exp +0.27R
COSTS stop 4.2/sh (102bps) friction_R 0.11 | room: R_RND 1.55R, W52H 1.8R | blended-target gate 1.78R
BOOK open 1 (SBIN short, stop trailed, risk .25R) | open risk .25R/3R | entries 2/8 | tier cap A+ | coach flags: none
  LESSON (debrief 02-Oct): "base-top breaks with round number <1ATR away stalled 3/4 — scale 40% at round"
PRECEDENTS kNN k=5: +1.8R, +2.4R, +0.9R (continuation); -1R, -0.4R (stalled at W52H)
ASK: ARM | TAKE | WAIT_FOR | PASS. Answer the checklist. Adjust only within bounds.
```

**Deliberately excluded: rupee P&L and the streak narrative.** [J] The LLM sees *risk state* (open risk, tier cap, coach flags) but not "down ₹14k today". LLMs absorb framing and drift toward risk-seeking or paralysis, and the ideal is P&L-indifferent execution. Code enforces the streak rules. A P&L-visible variant can be tested in the arena later.

**Chart images: decision**
- **Evidence:**
  - A 2026 benchmark found that most VLMs predict well only in persistent up- or downtrends and poorly in ordinary conditions ([arXiv 2604.12659](https://arxiv.org/pdf/2604.12659), M).
  - Feeding chart images straight to an LLM underperformed numeric approaches unless the outputs were calibrated afterwards ([IJACSA 2025](https://www.thesai.org/Downloads/Volume16No4/Paper_2-Comparing_Vision_Instruct_LLMs_Vision_Based_Deep_Learning.pdf), M).
  - In my experience, a chart's value is the *gestalt*: base, extension, overhead supply. That lives in the daily and 60-minute charts, not in the 5-minute trigger. [J]
- **Recommendation:**
  1. **Numeric-first for every decision call.** Code writes a structure digest (swing sequence, base, extension, profile) that is precise, cacheable and testable.
  2. **Vision once per name pre-market.** One 1280×720 two-panel image (6-month daily plus 15-day 60-minute, with level-ID lines) goes to Opus, which returns `ChartContext` tags. At about 1 token per 28×28 patch, each image is ~1.2k tokens (claude-api cost guide, M), so 8 images cost about ₹4 a day.
  3. **Arena book V** runs the same decider plus a 5-minute intraday image on a 50% sample of moments. It is paired against the numeric book on identical moments and promoted only if it adds ≥ +0.05R per decision after 150 paired moments.
  4. **Render spec:** mplfinance, white background, candles plus volume, VWAP and bands, labelled level lines, last bar marked, no oscillators.

---

## 5. Position management by the LLM

**Events that trigger a management call**
- **ARMED fill:** post-fill review within 90 s (Sonnet). It may EXIT or tighten.
- **+1R MFE:** Haiku decides whether to move the stop to structure.
- **Soft invalidation true:** Sonnet.
- **News, index regime shift or sector reversal:** Sonnet.
- **Time stop T−5 min with MFE < 0.5R:** Haiku; exit, or extend once by at most 15 minutes.
- **11:30 lunch transition and 14:30:** one batched call covering all positions.

**What does not trigger a call**
- **Stop approach.** The hard stop does its job, and asking the LLM near the stop invites flinching.
- **T1 hit.** The planned partial runs automatically.
- **Hard invalidation.** Code exits.

**Rules (code-enforced)**
1. Never widen or remove a stop; never average down.
2. **Breakeven only after ≥ +1R *and* a new 5-minute higher low above entry** (lower high for shorts). Before that, the stop moves to structure. Premature breakeven stops are the classic way a retail trader turns winners into scratches. [J]
3. Partials: 33–40% at the planned T1, at most 2 discretionary partials, and at least 30% always runs on the trail.
4. The trail style is chosen at entry and can only switch to a tighter one:
   - `STRUCT_5M` (default)
   - `VWAP_5M_CLOSE` (trend-day leader)
   - `EMA9_5M` (news momentum)
   - `CHANDELIER_2ATR`
5. Adds only via `ADD_PLANNED`: once, at ≥ +1R, with the stop at or above breakeven so total risk stays ≤ the original R.
6. **Against micromanaging:**
   - At most 1 discretionary call per position per 10 minutes.
   - HOLD is the default.
   - Any non-HOLD answer must cite an event ID and the changed metric.
   - Journal "management alpha" (actual minus a plan-only counterfactual). If it is negative after 40 trades, management is restricted to hard invalidations and time stops.

---

## 6. Discipline guardrails

**Tier criteria** (code computes the numbers; the LLM must agree or the decision is rejected):

| Check | Pass condition |
|---|---|
| Catalyst or RS | Materiality ≥ 6, or RS vs Nifty over 30 min ≥ +0.5% (−0.5% for shorts) |
| Location / defined risk | Stop at a level ≤ 0.6 ATR away, friction_R ≤ 0.15 |
| Day type supports the setup class | Per the allow matrix |
| **Index with me?** | Nifty and sector on my side of VWAP, or catalyst ≥ 7 with tier ≤ B |
| **Priced in?** | Realised share of the class's expected move < 70% (above that: pullback tactics only) |
| **Am I chasing?** | Entry ≤ 0.3 ATR beyond the trigger, < 1.5 ATR from VWAP, day range < 1.2× ATR14, fewer than 4 consecutive same-direction 5m bars |
| Room | ≥ 2R to the first opposing level, or the blended target clears the gate |
| **What is my edge?** | `setup_class` from the taxonomy, plus a base rate. If n ≥ 20 and expectancy < 0, then PASS unless an override reason is given (logged and audited) |

- **A+** needs all eight checks.
- **A** needs seven, including location and index.
- **B** needs six, including location.
- Failing location or friction means the trade cannot be taken.
- An unplanned trade (no scenario ID) is capped at B.

**Anti-pattern detectors (code; outputs become coach flags in the sitrep and are enforced)**

| Pattern | Detector → action |
|---|---|
| Revenge | Re-entry, same symbol and direction, within 20 minutes of a stop → blocked unless it is a new scenario at tier ≤ B |
| Loss streak | 2 losses in a row → 20-minute cooldown, next trade must be ≥ A plus a Critic check. 3 losses or −1.25% on the day → A+ only at 0.5×. −2% → lock (hard) |
| Euphoria | Day ≥ +1.5% → tier capped at A, at most 2 more trades. Give-back of 50% from a peak ≥ +1% → stop for the day |
| Overtrading | More than 8 entries a day or more than 2 per symbol → blocked. Daily take rate > 45% → raise the bar |
| FOMO | Move > 2.5 ATR from the open in the trade's direction → only T1/T7 tactics |
| Overconfidence | Weekly Brier score on `my_p_t1`. Shrink confidence toward the base rate if it is miscalibrated |

---

## 7. Instant execution while the LLM thinks for 10–40 s

| Mode | When | Mechanics |
|---|---|---|
| **ARMED** | T2, T3, T5, and index breaks: scenarios approved in the plan or by a heads-up call | Code fires within 200 ms of the trigger, inside the pre-approved bounds (max entry, max stop distance, tier, expiry). The LLM gets a post-fill review: it may exit or tighten, never widen. |
| **HEADS-UP → ARMED** | A precondition is met a few minutes before the trigger | A Sonnet call answers "if it triggers within N minutes, do you want it, and within what bounds?" The answer is armed with an expiry of 10–15 minutes. This hides the latency. |
| **CONFIRM** | T1, T4, T6, T7, T8 (price comes to a level), unplanned moments, news | Code holds the trigger; one call with deadline min(45 s, price leaves the zone). A late answer counts as PASS. If price drifts > 0.15 ATR during the think, the decision auto-converts to PULLBACK_LIMIT or PASS. |
| **WATCH** | Interesting but no plan | Haiku note; queued for the next checkpoint |

**Auto-disarm.** An armed scenario is disarmed if:
- the day type flips against it;
- Nifty moves more than 0.4% against it;
- VIX rises more than 8%;
- a new filing arrives on the symbol;
- its window closes;
- a coach flag fires; or
- the LLM provider is down.

**If OpenRouter fails, the system fails closed:** no new arms or entries. Positions stay protected by stops held at the broker and by code.

---

## 8. Options and MCX: one brain, different expressions

**Choosing the instrument.** The LLM picks the *expression*; code picks the strike and size.

1. **Stock view → CASH_MIS.**
   - Why: futures cost about 2.1 bps more per round trip. Stock options see IV pop 5–15 points and spreads of 1–3% on news (research 10, M).
   - Exception: binary gap or halt risk on a whitelisted name. Then use an ITM option (Δ 0.65–0.75) or a debit spread.
   - Never in expiry week. Never long premium within 3 sessions before results.
2. **Index view → hold ≤ 90 minutes (≤ 60 on expiry day): long weekly option, Δ 0.55–0.65.**
   - Nifty; Sensex only on Wednesday/Thursday.
   - Expected hold > 45 minutes or IVP > 60 → debit spread. Theta erases the option advantage over futures after about 1.5–2 hours, about 1 hour on expiry day (research 10, M).
   - Index triggers (OR acceptance, PDH/PDL break, VWAP reclaim on a trend day, breadth thrust with A/D > 2) are mostly **ARMED**, because Nifty breaks run.
3. **Range view → expiry-day iron fly/condor only, 12:45–14:00.**
   - 1 set, max loss ≤ 1R.
   - The LLM answers YES/NO plus a wing preference.
   - Code checks RV/IV, VIX, OI walls and margin including ELM.
4. **Stops sit on the underlying's level IDs**, plus a −35% premium catastrophe cap (−50% on expiry day). Code R-matches by full repricing.

**MCX evening plan (16:45, Sonnet; Opus on EIA Wednesdays if the budget allows)**
- **Inputs:**
  - MCX day-session range (L.DSH/L.DSL), the European range, Brent/WTI, USDINR, DXY, OPEC and geopolitical items, contract-calendar and margin flags.
  - **US data at 08:30 ET = 18:00 IST now and 19:00 IST after US DST ends on 1 Nov.**
  - **EIA (Wednesday 10:30 ET) = 20:00 IST now and 21:00 IST after 1 Nov.**
  - US cash open at 19:00 IST (20:00 after 1 Nov). (Time-zone arithmetic, H.)
- **Output:**
  - 1–2 CRUDEOILM scenarios. The window opens at max(18:15, event + 15 minutes).
  - EIA blackout from T−10 to T+5.
  - One intraday trade, ₹3k risk, no Wednesday breakouts.
  - Time stop 22:40 (23:15 after the US clock change).
  - Review of the C1 positional trade. The C1 entry is rule-based; the LLM only vetoes for event or gap risk, or a clash with the overnight reserve.
- Same `TradeDecision` schema, with `MCX_FUT`.

---

## 9. Arena hook and budget

**Paired evaluation.** Every moment goes to every book, and each book's decision gets a conservative shadow fill. Books are then compared **per moment** (paired), which carries far more statistical power than comparing equity curves:
- **B0:** rules-only control; takes every trigger with plan defaults.
- **B1:** LLM trader, numeric (primary).
- **B2:** B1 plus a chart image.
- **B3:** rules propose, Haiku vetoes.
- **B4 (optional):** no-plan reactive LLM, to price the value of prep.

PASSes are scored as avoided losses or missed gains.

| Item | Calls/day | ₹/day |
|---|---|---|
| Strategist, plans and chart context (Opus) | 1 loop | 55 |
| Checkpoints (Sonnet) | 4 | 14 |
| B1 decisions and heads-ups (Sonnet medium) | 30–40 | 55–65 |
| Management (Haiku 70% / Sonnet 30%) | 15–25 | 10 |
| Triage (Haiku, about 400 items) and materiality (Sonnet, 10–20) | — | 35–55 |
| B2 vision (50% sample) / B3 veto | 15–20 / 35 | 35 / 4 |
| Batch review | — | 30 |
| MCX | 6–10 | 15–20 |
| **Total** | | **≈ ₹250–290/day → ₹5.3–6.1k/month**, plus a weekly Opus batch tuner (≈ ₹400) |

**Degrade ladder at 80% of the monthly budget:**
1. Turn off B2.
2. Move heads-up calls to Haiku.
3. Merge the checkpoints.
4. Stop Opus escalation of materiality.

---

## Top 5 recommendations

1. **Put the Opus pre-market `GamePlan` at the center.** Every trade traces to a scenario ID or is tagged "unplanned" and capped at B. Track planned vs unplanned expectancy from day 1.
2. **Remove latency structurally.** Heads-up calls lead to ARMED orders with bounds and auto-disarm. CONFIRM is used only for tactics that rest at a level. Momentum chases happen only when armed.
3. **Decide as base rate plus adjustment.** Backtested scenario statistics, kNN precedents and a calibrated `my_p_t1` go into every decision. Shadow-fill every PASS, and judge books with paired, moment-level comparisons.
4. **Numeric-first; vision where it belongs.** Use vision for pre-market chart context, and as arena book V on half the moments. Promote it only on paired evidence (≥ +0.05R per decision after 150 moments).
5. **Keep discipline in code, prompts P&L-blind, and management event-driven.** HOLD is the default, no breakeven stop before structure, and "management alpha" is measured so a micromanaging LLM loses that authority automatically.

## Risks and unknowns

- **No honest backtest of the LLM's decisions.** Model training data runs to a June 2026 cutoff, so pre-cutoff history leaks. Evidence comes only from forward paper trading: about 100–170 trades a month means 2–3 months per book. Paired moments shorten this.
- **Sonnet 5.5 latency and variance through OpenRouter is unmeasured.** My 8–20 s guess for an 8k-token prompt needs a Phase-0 measurement. Adaptive-thinking token use is variable; cap it with effort and `max_tokens`, and monitor ₹ per decision.
- **The LLM may over-pass** (safety-tuned caution) **or rationalize.** Watch the take rate, calibration (Brier score) and pass shadow outcomes.
- **Base-rate tables come from candle backtests** with conservative fills and no depth history, so precedents for intraday microstructure are weak at first.
- **Regime concentration.** Results season and a market near 6-month lows may not generalize, so promote books only across at least 2 regimes.
- **Vision evidence comes from longer horizons.** Nothing published covers intraday VLM reading of Indian charts.
- **Facts rated M need re-checking in Phase 0:** CAS timings and the cancellation of SL orders at 15:15, the pre-open changes, the block-deal windows and Upstox square-off times.
- **Filings may contain prompt injection.** They arrive as delimited data, triage has no tools, and every output still passes the deterministic gates.

**Sources:** [arXiv 2604.12659](https://arxiv.org/pdf/2604.12659) · [IJACSA 2025 vision LLM vs numeric](https://www.thesai.org/Downloads/Volume16No4/Paper_2-Comparing_Vision_Instruct_LLMs_Vision_Based_Deep_Learning.pdf) · [SEBI block-deal framework (Business Standard)](https://www.business-standard.com/amp/article/pti-stories/sebi-revises-block-deal-norms-min-order-size-hiked-to-rs10-cr-117102601023_1.html) · [5paisa block-deal revamp](https://www.5paisa.com/index.php/news/sebi-revamps-block-deal-norms-sets-rs25-crore-minimum-trade-size). Internal sources: `/home/user/auto-trading/docs/design/trading-system-design.md`, `/home/user/auto-trading/docs/research/03-trading-playbook-and-risk.md`, `/home/user/auto-trading/docs/research/09-intraday-options-module.md`, `/home/user/auto-trading/docs/research/10-red-team-intraday-options.md`, `/home/user/auto-trading/docs/research/05-llm-agent-layer.md`. Model prices come from the claude-api reference (cached 2026-10-06).