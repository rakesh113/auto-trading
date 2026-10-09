# The AI Trader: decision layer and arena (design v1)

**Status:** design, 2026-10-09. It is part of the system design v0.3 ([`trading-system-design.md`](trading-system-design.md)), which it extends. Where the two differ on how trades are decided, this document wins.
**Owner decision (9 Oct 2026):** the LLM is the actual discretionary trader, not a filter on fixed rule strategies. Several approaches run side by side in paper and are compared. The initial LLM budget is ₹5–7k a month. Whether to use chart images was delegated to us.
**Research behind it:** reports 13–18 in [`docs/research/`](../research/): trader decision process, cost and latency, chart vision, arena evaluation, edge and trust, and a red-team review. Where they disagreed, this document follows the red team's rulings.

---

## 0. The decisions in one page

| # | Decision | Why |
|---|---|---|
| A1 | **The LLM is the trader.** It plans the day, decides at each moment, and manages its open positions. Code is its eyes (watchers and scanners that create decision moments), its hands (precise entry tactics and order handling) and its seatbelt (risk, stops, flatten times). | Owner decision. Judgment, not chart patterns, is where a discretionary edge lives. |
| A2 | **Plan the trade, trade the plan.** An Opus pre-market game plan writes IF-THEN scenarios per stock. Code watches them at no cost. Decisions are made **as price approaches a trigger**, so execution is instant when it fires. | Removes LLM latency from entries. A 20-second think on a breakout guarantees a bad fill. |
| A3 | **The question that decides everything is selection skill.** At every moment the LLM must score the setup (`p_win`, `exp_R`), even when it passes. The primary metric is the correlation between those scores and what actually happened (the information coefficient, IC). | It is the only thing an 8–12 week paper run can answer honestly. Profitability takes longer. |
| A4 | **Two paid LLM books; everything else is computed for free.** L is the LLM trader. V is the same calls plus a chart, on probation. A counterfactual engine re-simulates every moment, which yields the rules control, the veto book, the management ablation and placebos at zero LLM cost. | Fits ₹5–7k a month, and keeps the comparisons paired and statistically strong. |
| A5 | **Charts are not the default:** numbers are the source of truth and no price can ever be read off an image. A chart twin (V) runs on every moment after passing a perception test, with an early stop and a pre-registered keep/drop rule. Ties go to numbers. Owners always get the chart. | Evidence: vision models read broad shape but misread values, cannot name patterns, and lean long/trend. Worth testing, not assuming. |
| A6 | **Models:** Opus 5.5 for the plan; Sonnet 5.5 at low effort for decisions; Haiku 5.5 for triage, routine management and a shadow decider. All through OpenRouter. | Depth where latency doesn't matter; speed and cost where it does. Haiku shows whether Sonnet is worth 20× the price. |
| A7 | **Discipline lives in code, never in the prompt.** Code computes the checklist (chasing, room, friction, index alignment). The LLM cannot raise size, widen stops, or exceed 4 equity entries a day. Prompts are P&L-blind: the LLM sees risk capacity, not rupees won or lost. | LLMs absorb framing and drift toward revenge or paralysis. Code doesn't. |
| A8 | **Season 1 is frozen:** no learning loop in the prompt, no prompt edits mid-season. Every case (including passes) is logged; lessons are tested offline and enter only as a new "trader identity" at a season boundary. | Every change resets the track record. A drifting prompt can never be evaluated. |
| A9 | **Pre-registered kill and success criteria.** Week 8 decides kill-or-continue; week 12, tiny live probes; "rely on it instead of manual trading" needs at least 6 months of evidence. | Honest timelines protect the owner's capital and trust. |
| A10 | **Season 1 scope:** the LLM trades intraday equity, plus Nifty index-option moments as an exploratory sub-book. MCX and swing stay rule-based (with an LLM veto for swing holds) until equity is proven. | Too few option, MCX and swing decisions to judge an LLM there within a season. |

---

## 1. Why this design, and what the evidence says

- **Public results are sobering.**
  - In Alpha Arena season 1 (Oct–Nov 2025, real money, crypto perpetuals), 4 of 6 frontier models lost money. Each showed persistent "personality" biases (report 17, M).
  - FINSABER tested LLM strategies across about 20 years and 100+ symbols; most reported advantages disappeared. They were too conservative in bull markets and too aggressive in bear markets (report 17, H).
- **So the edge cannot be "the LLM reads price patterns".** It has to come from six places:
  1. **Selectivity and abstention:** right stock, right day, and many days with no trade.
  2. **Catalyst interpretation scaled to company size:** a ₹500 cr order is about 10% of a ₹5,000 cr company and noise for a ₹2L cr one.
  3. **Combining many weak signals** that fixed rules cannot combine.
  4. **Knowing its own base rates,** and adjusting them for today's context.
  5. **Recognising a broken thesis** early.
  6. **Machine discipline:** no tilt, no revenge, no fatigue.
- **The base-rate trap is the most likely way this fails** (report 18). The eyes are rule triggers that on their own have roughly zero or negative expectancy. The LLM adds value only if it ranks them well. Taking the top 15% of triggers with average outcome −0.05R and spread σ ≈ 1.2R:

  ```
  E[R | taken] ≈ −0.05 + 1.87 × ρ        (ρ = correlation between the LLM's score and the outcome)
  ρ ≈ 0.11  →  +0.15R per trade      ρ ≈ 0.13  →  +0.20R per trade
  ```

  A correlation of 0.11–0.13 is a high bar for intraday outcomes. That is why selection IC is the primary, pre-registered metric.

---

## 2. The trader's day

| IST | Step | Who | Output |
|---|---|---|---|
| Previous evening | Results calendar, FII/DII, participant OI, bulk/block deals, after-hours filings | Code | Candidate pool |
| 07:45–08:30 | Global cues, filings since 15:30, in-play score, dossiers per candidate (numbers, cards, levels) | Code | Dossiers |
| **08:30–09:05** | **Pre-market game plan** (no tool loop; code pre-assembles everything) | **Opus 5.5**, medium effort | `MarketThesis`, 5–8 `GamePlan`s, avoid list, tradeability prior, 20–40 scenario propositions |
| 09:08–09:12 | Compare pre-open indicative price and futures imbalance with plan assumptions | Code | Scenarios marked valid or invalid |
| 09:15–09:24 | Observe; build opening range, drive, RVOL, breadth. No entries. | Code | — |
| **09:24** | **Open read:** confirm, kill or re-rank scenarios; approve arming | Sonnet 5.5 | Updated plans |
| 09:25–11:30 | **Prime window:** decision moments, entries, management | Sonnet / Haiku | `TradeDecision`, `PositionUpdate` |
| 09:40 | Tradeability score (§8) | Code + plan | Daily risk posture |
| 11:30–13:30 | Lunch: bar raised to A+; range and VWAP-reversion tactics only | — | — |
| **12:15** | **Midday re-plan** | Sonnet 5.5 | Refreshed scenarios |
| European open (12:30 IST until 25 Oct, then 13:30) | Day-type classifier re-run | Code | Afternoon posture |
| 14:30 | Swing checkpoint: code gates, then the Trade Critic for any candidate | Code + Sonnet | Hold or flat |
| 14:40 / 15:00 / 15:12 | No new entries / closing-auction names flat / others flat | Code | — |
| 15:45–17:00 | Review of trades **and passes** with counterfactual outcomes; journal; scenario propositions scored | Batch (Sonnet) + code | Daily debrief, leaderboard |

**Special days:**
- **Expiry days** (Nifty and Sensex, from the contract master; 9 Nov 2026 is a Monday):
  - pin zones at the max-OI strikes go into the plan;
  - no heavyweight breakout scenarios after 13:00;
  - the iron-fly YES/NO checkpoint is at 12:45.
- **A focus stock's own results day:**
  - the plan carries a pre-written results tree ("if EBITDA beats our proxy by ≥ 5% and margin rises → continuation scenarios; if it misses → short scenarios");
  - no position in the 30 minutes before the outcome;
  - the first decision comes 3–5 minutes after the filing.
- **Event days** (RBI, Budget, overnight US CPI/FOMC):
  - `EVENT_WAIT` until 15 minutes after the event;
  - size capped at M.
- **Results season (now):** more catalyst moments, so the budget reserve is spent here.

---

## 3. The game plan

The pre-market call returns one `MarketThesis` and up to 8 `GamePlan`s. **Every price is a level ID** from code's level registry (`L.PDH`, `L.ORH15`, `L.VWAP`, `L.W52H`, `L.RND1400`, …). Code resolves IDs to prices.

```yaml
MarketThesis:
  narrative: "≤120 words"
  day_type_probs: {TREND_UP: .2, TREND_DN: .3, RANGE: .4, VOLATILE: .1}
  sector_lead: [PSE, DEFENCE]     sector_lag: [IT]
  flip_condition: "Nifty reclaims L.PDH with A/D > 1.5"
  posture: {max_long_beta: 1.0, max_short_beta: 1.0}
  tradeability_prior: 0-100

GamePlan:
  symbol: BEL
  bias: LONG_ONLY | SHORT_ONLY | BOTH | AVOID
  why: "₹2,410 cr order = 9.8% of TTM revenue; pre-open gap +1.1 ATR"
  levels: [L.PDH, L.W52H, L.ORH15, L.VWAP, L.GAPFILL]
  scenarios:
    - id: S1
      name: base-top acceptance
      mode: APPROACH            # ARMED | APPROACH | CONFIRM (§5)
      window: ["09:30", "10:45"]
      if:   [{m: close, tf: 5m, op: ">", ref: L.ORH15}, {m: rvol, op: ">=", v: 2},
             {m: nifty_ret_open, op: ">", v: -0.4}]
      then: {tactic: T2_BREAK_RETEST, stop: {ref: L.ORMID}, size: M,
             targets: [{ref: L.RND420, pct: 40}, {r: 2.5, pct: 30}, {trail: VWAP_5M_CLOSE, pct: 30}]}
      kill_if: [{m: nifty_vs_vwap_atr, op: "<", v: -0.3}]
      p_trigger: 0.45
      p_t1_if_triggered: 0.55
    - id: S3
      name: priced in
      if: [{m: open_gap_atr, op: ">", v: 1.9}]
      then: AVOID
  not_worth_watching_if: "opens > +1.9 ATR or OR15 > 1 ATR"
```

- Each plan must say **what would make the stock not worth watching today.**
- The avoid list covers:
  - results due before the outcome;
  - F&O ban;
  - ASM/GSM;
  - spread above the tier limit;
  - moves already larger than 2.5 ATR.
- **Scenario propositions** ("scenario markets"):
  - The plan also pre-commits 20–40 binary statements that code can resolve, each with a probability. Examples: "S1 triggers before 11:30", "if it triggers, T1 is hit before the stop", "Nifty closes above PDC", "a trend label appears by 10:30".
  - Code scores them at the close against climatology (base rates from the rules control).
  - **Why:** about 600 forecasts a month give a skill signal in 2–4 weeks instead of 4+ months.
- **Regime comes only from code features.** The plan never hard-codes a market view (such as "default short") into standing prose; each day's thesis is written fresh from that day's data.

---

## 4. The eyes: decision moments

Code creates moments. The LLM never polls the market.

| Source | Trigger | What the LLM decides | Deadline |
|---|---|---|---|
| **Scenario: approach** | Price within 0.3 ATR of a scenario trigger, or 1 of its 2 conditions true | Pre-clear: arm or not, within what bounds | Before the trigger (typically 2–10 min) |
| **Scenario: trigger** (CONFIRM scenarios only) | The `if` becomes true | Take, pass or adjust within bounds | min(45 s, price leaves the zone) |
| **Rule library** | A rule tactic fires on the deterministic in-play top 15 (§6, tactic menu) | Take or pass. This also feeds the rules-only and veto books. | 45 s |
| **Scanner** | Unplanned level test with RVOL ≥ 1.5; failed breakout; first VWAP test after a trend leg; relative-strength divergence ≥ 0.4% in 15 min; 1-min volume > 5× normal; futures OI ±3% in 15 min | New scenario, take or ignore | 60 s |
| **News** | Filing or news with triage materiality ≥ 6 | New in-play? Thesis change? Exit? | 60–120 s (results: wait 3–5 min) |
| **Index regime** | Day-type flips, Nifty breaks OR/PDH/PDL, VIX +8% | Book-level: tighten, disarm, flip bias | 60 s |
| **Checkpoints** | 09:24, 12:15 | Re-plan | 2 min |

**Filters before waking the LLM:**
- focus and watch names only;
- the window is allowed for the current day type;
- one open moment per symbol;
- a 10-minute cooldown after a PASS unless new information arrives;
- a friction pre-check;
- de-duplication by fingerprint (symbol, scenario, trigger type, side, 0.2-ATR price bucket, 3-minute bucket);
- book capacity.

**Caps:**
- **40 entry-side LLM calls a day** (hard cap).
- If rule-library triggers exceed what fits, a *random* sample goes to the LLM, so the veto book stays unbiased. The rest are marked "unasked" and still scored by the counterfactual engine (§12).

**Bursts.** When two or more moments are open within 60 seconds (common from 09:25 to 09:45), code sends **one "rank and take at most k of N" call** instead of separate yes/no calls. It is cheaper, and LLMs judge relatively better than they calibrate absolutely. Each candidate still gets its own scores.

---

## 5. Entry modes and the tactic menu

| Mode | When | How |
|---|---|---|
| **ARMED** | A scenario approved in the plan or refresh within the last 30 minutes that still passes code's validity checks | Code enters within 200 ms of the trigger, inside pre-approved bounds (max entry, max stop distance, size, expiry). The LLM gets a post-fill review within 90 s: it may exit or tighten, never widen. |
| **APPROACH** (default) | Price nearing a trigger | One call *before* the trigger. If approved, the order is armed with a **10-minute expiry**. LLM latency is hidden. |
| **CONFIRM** | Setups that only resolve on a bar close (reversals, fades, VWAP reclaims), unplanned moments, news | Code holds the trigger for one call. A late answer counts as PASS. **Chase guard:** if price has moved more than 0.25× the stop distance past the trigger, convert to a 3-minute retest limit or skip. |

**Auto-disarm.** Armed scenarios are disarmed when:
- the day type flips against them;
- Nifty moves more than 0.4% against them;
- VIX rises more than 8%;
- a filing lands on the symbol;
- the window closes;
- a discipline flag fires;
- the LLM provider is down.

**If OpenRouter fails, the system fails closed:** no new arms or entries; open positions stay protected by broker-side stops and code.

**Tactic menu** (code executes precisely; level IDs resolve to prices):

| ID | Logic | Default mode |
|---|---|---|
| T1 PULLBACK_LIMIT | Resting limit in a zone (VWAP, level, 5m EMA20 ± band); cancel if price runs 0.5 ATR away | CONFIRM |
| T2 BREAK_RETEST | 5m close beyond a level on ≥ 1.5× volume, then a limit near the level on the retest | APPROACH / ARMED |
| T3 OR_ACCEPTANCE | Two 5m closes beyond OR15/OR30, holding 3 minutes; marketable limit capped at 0.1 ATR | ARMED |
| T4 FAILED_BREAK_RECLAIM | Break ≥ 0.15 ATR, reclaimed within 2 bars; stop beyond the failed extreme | CONFIRM |
| T5 MOMENTUM_CHASE_CAPPED | Marketable limit, chase ≤ min(0.15 ATR, 8 bps) | **ARMED only** |
| T6 VWAP_RECLAIM_REJECT | Cross back within 2 bars on rising volume; enter on the first 1m pullback that holds | CONFIRM |
| T7 OPENING_DRIVE_PULLBACK | After 09:25, a 38–50% retrace of the opening drive on volume below 60% of the impulse | CONFIRM |
| T8 RANGE_EDGE_FADE | Range days only; limit at the range edge | CONFIRM |
| T9 SCALE_IN_2 | Half at the top of the zone, half at the bottom; one stop sized on the blend | CONFIRM |

- The same tactics, run on the deterministic in-play list with default parameters, form the **rules-only control book R**.
- **Index options** use the same tactics on Nifty levels; code converts the signal into the option order (strike by delta, size by repricing; main design §7.2).
- **Paper realism for resting limits** (T1, T2, T8, T9): a fill counts only when price trades **at least one tick through** the limit, with the queue model. Results are always reported by tactic family (marketable vs resting), because resting-limit fills are the biggest paper-to-live gap.

---

## 6. The decision call

### 6.1 What the LLM sees: the situation report

Code computes every number. The LLM never sees raw ticks. The report is about 900–1,200 tokens and is P&L-blind (illustrative values):

```
#SITREP M-1012-0947-BEL-S1 snapshot S-77f3 as_of 09:47:12 trigger APPROACH S1 (ltp 0.08 ATR below L.ORH15)
MARKET NIFTY 22,742 -0.21% vwap -0.1ATR | daytype prov RANGE .55 TREND_DN .30 | A/D 0.82 | VIX 14.1 +2.4%
  sector NIFTY_PSE +0.9% (rank 1/14) | defence basket +1.6% | expiry: no
STOCK BEL ltp 412.6 ATR14 9.8 (2.4%) tier A | closing-auction yes | ban no
 LEVELS id:px(dATR) ORH15 413.4(+.08) PDH 408.9(-.38) VWAP 409.7(-.30) ORMID 409.3 ORL15 405.2(-.76)
        RND420 420(+.76) W52H 421.0(+.86) GAPFILL 401.6(-1.12)
 STRUCTURE daily uptrend, above rising 20/50 DMA; 6-week base 388-418; today = base-top test
  60m HH/HL since 01-Oct | 5m swings HH HL HH HL | efficiency(today) 0.62 | overlap(10 bars) 30%
  sparkline(3m closes, 0-9): 0123345677898877899
  opening drive +1.9%, pullback 38% to 408.6 on volume 0.45x impulse
 VOLUME RVOL15 3.4 (p96) | VWAP +1σ 413.9 +2σ 417.6 | profile VAH 412.8 POC 410.1
 RS vs NIFTY 30m +1.6% | vs sector +0.7%
CATALYST 08:12 NSE filing "orders ₹2,410 cr" materiality 74 | 9.8% TTM revenue | 3.1% order book | 12x 20d turnover
  since t0 +2.9% (1.2 ATR) | typical move for this class 1.8 ATR → 66% realised | priced_in .55 | pre-t0 drift none
FLOW futures OI +4.1% with price up (long buildup) | call OI wall 420 (2.1x) | puts building 400
  depth top5 bid/ask 1.6 | spread 3 bps
PLAN S1 base-top acceptance → T2, stop ORMID, size M, T: RND420 40% / 2.5R 30% / trail VWAP_5M 30%, window to 10:45
  bounds: entry ≤ ORH15 + 0.15 ATR; stop ≤ 0.45 ATR | plan p_trigger .45, p_t1 .55
  BASE RATE (walk-forward, rule library, conservative fills): n=184 win 47% exp +0.27R (shrunk +0.18R)
CHECKLIST (code) catalyst ✓ | location ✓ stop 0.42 ATR | index NEUTRAL | priced_in 0.55 (<0.70 ✓) | chasing no
  room to RND420 1.55R, to W52H 1.8R | friction 0.11R | blended-target gate 1.78R ✓ | window prime ✓
BOOK open 1 position (risk 0.25R) | open-risk capacity 2.75R | entries 2/4 | size cap L | flags: none
ASK: pre-clear S1 (ARM with bounds) or PASS. Score the setup in every case.
```

**Deliberately excluded:**
- **Rupee P&L and streak narrative.** The LLM sees risk capacity and size caps, not "down ₹14k today"; code enforces the streak rules.
- **Precedent cases and lessons, in season 1** (§13).

**Shape features** (efficiency ratio, overlap, swing sequence, a 24-digit sparkline) give the numeric book the "gestalt" a chart would show. That makes the chart test fair: good features against good features plus a chart.

### 6.2 What the LLM returns

The field order forces skepticism before the decision.

```jsonc
TradeDecision/1 {
  "moment_id": "M-1012-0947-BEL-S1", "snapshot_id": "S-77f3",       // must echo
  "plan_alignment": "AS_PLANNED|MODIFIED|CONTRADICTS|UNPLANNED",
  "new_info_ids": ["N-0812-BEL"],                                    // required for MODIFIED/CONTRADICTS
  "against_case": "≤40 words: the best reason this loses",
  "setup_verdict": {                                                  // ALWAYS filled, even on PASS
     "take_on_empty_book": true, "grade": "A_PLUS|A|B|X",
     "p_win": 0.55, "exp_R": 0.35 },
  "action": "ARM|TAKE|WAIT_FOR|PASS",                                // portfolio-aware
  "pass_reason": "NO_EDGE|CHASING|INDEX_AGAINST|PRICED_IN|POOR_LOCATION|EVENT_RISK|ROOM|BOOK|OTHER",
  "direction": "LONG|SHORT",
  "instrument": "CASH_MIS|INDEX_OPT_LONG|INDEX_DEBIT_SPREAD|IRON_FLY_EXPIRY|STOCK_OPT_ITM",
  "tactic": {"id": "T2", "params": {"max_entry": {"ref": "L.ORH15", "off_atr": 0.15}}},
  "wait_for": [ /* condition DSL for WAIT_FOR / ARM */ ],
  "stop": {"ref": "L.ORMID", "off_atr": -0.05},
  "targets": [{"ref": "L.RND420", "pct": 40}, {"r": 2.5, "pct": 30}, {"trail": "VWAP_5M_CLOSE", "pct": 30}],
  "time_stop_min": 45,
  "size_request": "S|M|L",                                           // 0.5 / 0.75 / 1.0 × current R
  "mode_tag": "CATALYST|MOMENTUM|FADE|INDEX",
  "invalidations": [{"m": "close", "tf": "5m", "op": "<", "ref": "L.VWAP", "hard": true}],
  "thesis": "≤3 lines; every number must come from the sitrep",
  "expires_at": "09:57"
}
```

**Two fields make the arena work:**
- **`setup_verdict`** answers "would you take this on an empty book?" It is filled on **every** moment, including passes. It drives the information coefficient, the veto book and the meta-labeler.
- **`action`** accounts for the current portfolio.

### 6.3 What code enforces on the answer

1. **Schema:** strict JSON through OpenRouter, then Pydantic validation and semantic checks. One repair attempt, then PASS.
   - Semantic checks: level IDs resolve; stop, entry and targets correctly ordered; the snapshot ID is echoed.
2. **Numeric grounding:** every number in `thesis` must match a sitrep value within ±2%.
3. **Rationalisation guard:** `MODIFIED` or `CONTRADICTS` must cite information that arrived *after* the plan, otherwise the decision is rejected. A jump in `p_win` of more than 0.25 above the plan's probability with no new information is flagged.
4. **Checklist veto:** code's own checklist (location, friction, chasing, room, blended-target gate) overrides any LLM claim. A failed location or friction check makes the trade impossible.
5. **Final size** = the minimum of:
   - the request;
   - **M** until ≥ 100 resolved decisions exist *and* confidence is calibrated (isotonic map);
   - **M** when the base rate has n < 15;
   - **S** when the decision is UNPLANNED or CONTRADICTS the plan;
   - the day-type multiplier;
   - the drawdown ladder;
   - any discipline flag.

   Size can only go down from the request, never up.
6. **Scarcity:** at most **4 equity entries a day**. A `p_win` between 0.45 and 0.55 means PASS.
7. **Refusals** (`stop_reason: refusal`) and timeouts are treated as PASS.

---

## 7. Position management

**Events that trigger an LLM call** (at most **3 LLM calls per trade**):
- **Post-fill review of an ARMED entry** (Sonnet, within 90 s): it may exit or tighten.
- **A soft invalidation turns true**, or news, an index regime shift or a sector reversal (Sonnet).
- **Time stop minus 5 minutes with less than 0.5R of favourable excursion** (Haiku): exit, or extend once by at most 15 minutes.

**Handled by code without an LLM call:**
- **Hard invalidation or stop:** code exits.
- **Planned partial at T1:** runs automatically.
- **+1R:** code moves the stop to structure.
- **Price approaching the stop:** the hard stop does its job. Asking the LLM near the stop invites flinching.

**Rules (code-enforced):**
1. Never widen or remove a stop; never average down.
2. **Breakeven only after ≥ +1R and a new 5-minute higher low above entry** (lower high for shorts). Premature breakeven stops are the classic way winners become scratches.
3. 33–40% off at T1; at most 2 discretionary partials; at least 30% always runs on the trail.
4. The trail style is chosen at entry and can only switch to a tighter one:
   - `STRUCT_5M` (default)
   - `VWAP_5M_CLOSE`
   - `EMA9_5M`
   - `CHANDELIER_2ATR`
5. HOLD is the default answer. A non-HOLD answer must cite the event and the metric that changed.
6. **Management alpha is measured, not assumed.** The LD book keeps L's entries but uses default exits. If L − LD is not positive after 100 trades, management goes back to code.

---

## 8. Discipline, regime and "don't trade today"

**Checklist tiers** (code computes; shown in the sitrep):

| Check | Pass condition |
|---|---|
| Catalyst or relative strength | Materiality ≥ 6, or RS vs Nifty over 30 min ≥ +0.5% (−0.5% for shorts) |
| Location / defined risk | Stop at a level ≤ 0.6 ATR away; friction ≤ 0.15R |
| Day type supports the setup | Per the allow matrix |
| Index with me | Nifty and sector on my side of VWAP, or catalyst ≥ 7 with size ≤ S |
| Not priced in | Realised share of the class's typical move < 70% (above that: pullback tactics only) |
| Not chasing | Entry ≤ 0.3 ATR beyond trigger, < 1.5 ATR from VWAP, day range < 1.2× ATR14, fewer than 4 consecutive same-direction 5m bars |
| Room | ≥ 2R to the first opposing level, or the blended target clears the gate |
| Known edge | A setup class with a base rate; if n ≥ 20 and expectancy < 0, then PASS unless an override reason is logged |

**Anti-pattern detectors** (code; they become flags and are enforced):

| Pattern | Detector → action |
|---|---|
| Revenge | Same symbol and direction within 20 min of a stop → blocked unless it is a new scenario at size S |
| Loss streak | 2 losses in a row → 20-min cooldown, next trade needs grade ≥ A. 3 losses → A+ only at S. Daily lock per main design §6. |
| Euphoria | Day ≥ +1.5% → size capped at M, at most 2 more trades. A 50% give-back from a peak ≥ +1% → stop for the day |
| Overtrading | More than 4 entries, or more than 2 per symbol → blocked. Take rate above 45% → raise the bar |
| FOMO | Move > 2.5 ATR from the open in the trade's direction → only T1/T7 tactics |
| Overconfidence | Weekly Brier score on `p_win`; shrink toward the base rate if miscalibrated |

**Regime states** (from the deterministic day-type classifier):

| State | Modes allowed | Max LLM entries | Size |
|---|---|---|---|
| Trend / gap-and-go | MOMENTUM, CATALYST, INDEX buys | 4 | 1.0 |
| Dispersion | CATALYST, stock-specific MOMENTUM | 4 | 1.0 |
| Gap-and-fade / range | FADE, CATALYST; iron fly only on expiry days | 3 | 0.75 |
| Compressed / pre-event | CATALYST only | 2 | 0.5 |
| High-volatility event | CATALYST A+ only, after 10:30 | 1 | 0.5 |
| **SIT-OUT** | Manage open positions only | 0 | 0 |

**SIT-OUT triggers:**
- VIX +8% at the open together with a headline-driven gap ≥ 1 ATR;
- a binary event in session, until 30 minutes after it;
- a feed or data-quality fault;
- the drawdown ladder at stage 2 or worse.

**Tradeability score (0–100) at 09:40.** It is scored every day against the rules control book's P&L, which is the ground truth for "was today good for systematic setups". This directly measures whether "don't trade today" judgement adds value. Below 35: at most one A+ catalyst trade.

**Mode cards.** One brain, four modes: CATALYST, MOMENTUM, FADE and INDEX. Code picks a ≤ 300-token mode card per moment from the moment type and regime, and every decision carries a mode tag. Per-mode results come for free. A mode becomes its own book only once its tagged results show an edge.

**Weekly personality audit.** Each item is compared with the control book:
- long/short ratio vs breadth;
- trades per day;
- chase distance;
- average hold time;
- share of unplanned trades;
- calibration drift.

**Monthly mirror audit.** Invert 60 past moments: negate the numeric features, swap support and resistance (and flip the chart, for V). Decisions should flip long ↔ short. A gap of more than 10 points means a directional bias that must be fixed.

---

## 9. Information cards (the edges available cheaply)

| Card | Contents | Value |
|---|---|---|
| **Catalyst** (≤ 150 tokens) | Category; order value ÷ TTM revenue; % of market cap; **value ÷ 20-day turnover** (catches small caps where a ₹200 cr order dwarfs ₹20 cr of daily trading); reaction since t0; pre-t0 drift; realised share of typical move | High |
| **Results** | Parsed from XBRL by code. With no paid consensus feed, four proxies stand in: **surprise vs the company's own trend** (4-quarter trend blended with the same quarter last year); **options-implied move** (ATM straddle ÷ spot the day before, then the first-5-minute reaction ÷ implied move); **10-day pre-results drift**; **peer read-across** (median surprise of sector peers already reported). The first 3–5 minutes of abnormal return is itself the market's verdict. | High in season |
| **Flow** | OI quadrant; writing or migration at the top-3 strikes; PCR change; ATM IV percentile; block-window volume spikes (08:45–09:00, 14:05–14:20) | High for the index, medium for stocks |
| **Market** | Nifty, Bank Nifty, sector heatmap and ranks, VIX, A/D breadth, GIFT/US/Brent/USDINR context (pre-market) | High (regime) |

**Hygiene filters** (code; never shown as signals): corporate actions, F&O ban, ASM/GSM, index rebalances ("avoid into the close"), promoter pledge invocations (avoid list).

---

## 10. Charts: the decision

**What the evidence says** (report 15):
- **Vision models handle broad shape well:** trend vs chop, extension, how impulsive the approach was.
- **They are weak on:**
  - exact values and line crossings (about 58% on simple geometry tasks);
  - naming candlestick patterns (1 correct in 215 in one practitioner test);
  - actually using candlestick evidence (controlled tests show they mostly follow the past trend);
  - they show long and trend bias.
- Charts beat *raw* number series, but our numeric report is not raw.
- **The 5.5-generation models** are vendor-reported to read charts much better. That justifies a test, not adoption.

**Decision:**
1. **The primary book L decides from numbers.** No price from an image can reach the order system, because orders accept level IDs only.
2. **The chart twin V:**
   - **What it is:** the identical Sonnet call plus one 1400×1036 composite chart, on 100% of moments.
   - **When it starts:** only after a **perception gate**. On 50 synthetic snapshots, chart only, the model must answer whether price is above VWAP, which labelled levels are nearest above and below, and the 15-min trend, with ≥ 95% correct.
   - **Early stop at about 300 paired moments:** if V disagrees with L less than 5 points more often than L disagrees with its own repeat (the noise floor N′), the chart isn't changing decisions. V is stopped and the money saved.
   - **Keep rule:**
     - ≥ 150 moments where V and L disagree;
     - V − LD ≥ +0.10R per disagreement, with the one-sided 90% bound above 0 (Holm-corrected);
     - the gain is not confined to trend days;
     - misread rate < 5%;
     - long/short gap no worse than L's.
   - **Drop rule:** Δ ≤ 0 at 150 disagreements, or the upper bound below +0.05R at 300. **Unclear results go to numbers.**
3. **Pre-market plan:** a chart on a random 50% of symbol-days (about ₹70 a month), for a slower test of the plan's quality.
4. **Owner:** every trade card on Telegram carries the exact chart PNG.
5. **Never:** reading prices from images, naming patterns, option-chain heatmaps for the LLM (a ±10-strike table is exact and costs about 400 tokens).

**Chart spec** (one renderer, one source of truth):
- **Source of truth:** an immutable `SituationSnapshot` produces both the text report and the PNG. The chart header prints the `snapshot_id`, which the model must echo.
- **Panel A, 3-minute bars today plus the last 20 bars of the prior day:**
  - VWAP with ±1σ/±2σ bands;
  - opening-range box;
  - level lines labelled with **the same IDs and values as the text**;
  - the scenario's trigger zone and entry/stop/target lines;
  - volume against its time-of-day average;
  - a relative-strength strip vs Nifty.
- **Panel B:** 15-minute bars, 5 sessions.
- **Panel C:** daily bars, 6 months, with 20/50 EMA and the 52-week high.
- **Style:** fixed ATR-based price scale (a 0.3% move cannot look like a crash), white background, levels coloured by type. No oscillators, no pattern labels, no buy/sell arrows.
- **Cost:** 1400×1036 = 50 × 37 patches = **1,850 image tokens**, about ₹0.44 on Sonnet.
- **Rendering:** matplotlib (Agg) in a warm process pool on the Windows laptop, target p95 ≤ 250 ms, pre-rendered when a scenario is approached. PNG and hash go to the journal.
- **Every V decision includes a `perception_check`** that code verifies against the snapshot. One mismatch halves the size; two veto the trade.

---

## 11. Models, cost and latency

**Prices** (per million tokens; Anthropic list prices, passed through by OpenRouter with no markup; report 14 and report 18 corrections):

| Model | Input | Cache read | Output | Notes |
|---|---|---|---|---|
| Opus 5.5 | $4 | $0.20 | $20 | Thinking cannot be disabled; default effort medium |
| Sonnet 5.5 | $2 | $0.10 | $10 | Thinking on by default (default effort high); run at `effort: low` |
| Haiku 5.5 | $0.10 | $0.01 | $0.50 | Prompts must stay under 100k tokens (5× price above). Reasoning can be turned off. |

- **Temperature cannot be set** on the 5.5 models, so non-determinism is measured, not removed (repeat arm N′).
- **Landed rupee rate for budgeting: ₹118 per dollar** until the first invoice shows whether 18% GST applies (₹95 × OpenRouter's 5.5% credit fee × GST buffer).

**Routing and monthly cost (21 trading days, ₹118/$):**

| Line | Model, calls/day | ₹/month |
|---|---|---|
| Pre-market plan + scenario propositions (+ chart on 50% of names) | Opus 5.5, 1 call, no tool loop | ~960 |
| Open read 09:24 + midday re-plan 12:15 | Sonnet 5.5 low, 2 | ~210 |
| Filing and news triage (after the rule pre-filter) | Haiku 5.5, reasoning off, ~400 | ~220 |
| Materiality analysis | Haiku → Sonnet escalation, ~10 + 3 | ~270 |
| **L decisions** (6k cached + 3k fresh in, ~900 out) | Sonnet 5.5 low, ≤ 40 | **~1,550** |
| Prompt cache writes (1-hour TTL) | — | ~400 |
| Hk shadow decider (all moments) / N′ repeat probes (10%) | Haiku 40 / Sonnet 4 | ~60 / ~155 |
| Position management | Haiku 12 + Sonnet 2 | ~75 |
| EOD review and post-mortems | OpenRouter Batch (text only, about 50% off) | ~150 |
| `/why`, swing critic and small calls | Haiku / Sonnet | ~60 |
| **Subtotal without V** | | **≈ 4,100** |
| **V chart twin** (if it passes the perception gate and the early stop) | Sonnet + chart, ≤ 40 | **+ ~1,900** |
| **Total with V, plus 10% contingency** | | **≈ 6,600** |

**Sensitivity:** if Sonnet's real output is about 2k tokens instead of 900, add about ₹2.2k a month. V is then cut first.

**Phase-0 gates through OpenRouter, before arena day 1:**
1. Cached tokens > 0 on the decision route (prompt caching passes through).
2. Sonnet `effort: low` gives p90 output ≤ 1.2k tokens.
3. Strict JSON schema works with < 1% failures.
4. Billed image tokens ≈ ⌈w/28⌉ × ⌈h/28⌉.
5. p50/p95 latency measured over 200 calls per route from the laptop. Design target: decision p95 ≤ 20 s.
6. Flip-rate baseline: 50 moments × 3 repeats.
7. The first invoice shows whether GST is charged.
8. The counterfactual engine reproduces paper fills within 0.02R.

**Latency:**

| Call | p50 | p95 | Timeout | On timeout |
|---|---|---|---|---|
| Triage (Haiku) | ~2 s | 4 s | 6 s | 1 retry; the symbol stays blacked out |
| Approach decision (Sonnet) | 6–10 s | 15–20 s | 25 s | Nothing armed; on the trigger, the CONFIRM path or skip |
| Confirm decision | 3–8 s | 10–15 s | min(45 s, zone exit) | PASS |
| Management | 2–7 s | 12 s | 15 s | Broker stop stays; plan default applies |
| Pre-market plan | 1–3 min | 6 min | done by 09:05 | Fall back to Sonnet, else a rules-only day for LLM books |

**Pinning.** Decision routes pin the model ID and set `allow_fallbacks: false`. A different model never makes entry decisions, because that would contaminate the comparison. Management may fall back from Sonnet to Haiku to code.

**Budget governance:**
- **Caps:** monthly hard cap ₹7,000; daily soft cap ≈ remaining budget ÷ remaining trading days; per-route sub-budgets; separate OpenRouter keys (live, research/replay, batch) with credit limits; keep a balance of ≥ $15 (low balances add latency).
- **Degrade ladder:**
  1. Stop V.
  2. Cap moments at 30.
  3. Heads-up calls move to Haiku.
  4. Haiku becomes the primary decider.
  5. LLM entries stop; the rules book continues.
- **Telemetry on every call:** route, book, model and provider served, prompt version, tokens by type, ₹ cost, latency, schema result, moment ID.
- **Dashboard:** ₹ per decision, ₹ per trade, LLM cost as % of each book's gross P&L, and **value-add ROI** = (LLM book − control book) ÷ LLM cost.

---

## 12. The arena

### 12.1 The Counterfactual Outcome Engine (COE)

- **What it does:** every moment is re-simulated by the **same conservative paper-exchange code**, replayed on the recorded ticks and depth. The simulated entry time includes the deciding call's measured latency.
- **What it produces:** an after-cost outcome for *every* action at that moment, including actions nobody took:
  - `y_default`: the moment's own tactic with the default bracket (half out at 1R, the rest trailed on the 5-minute swing, 45-minute time stop);
  - one outcome per tactic on the menu.
- **Why it matters:** passes get scored, derived books cost nothing, and comparisons are paired on the same moments.
- **Checks:**
  - **Conformance:** COE re-simulation of actual paper trades must match the paper fills within a median of 0.02R.
  - **Sensitivity:** pass values are also reported under a second default bracket.

### 12.2 The books

| Book | Definition | LLM cost | What it answers |
|---|---|---|---|
| **L** | The LLM trader: plan, decisions, management | paid | The product |
| **V** | L's decision calls plus a chart; default exits (probation, §10) | paid | Value of charts (V − LD) |
| **Hk** | Haiku 5.5 deciding the same moments in shadow | ~₹60 | Is Sonnet worth 20×? |
| **R** | Rules control: every rule-library trigger on the **deterministic** in-play top 15, default bracket | free | The raw value of the setups (the baseline) |
| **S** | The plan's scenarios traded mechanically when they trigger | free | Value of the game plan (S − R) |
| **H** | R's triggers where L's `setup_verdict` said take | free | **Value of the LLM's vetoes** (H − R) |
| **LD** | L's entries with default exits | free | Value of LLM management (L − LD) |
| **E** | Take at full size when L and V agree, half when only L takes | free (once V runs) | Agreement as conviction |
| **P1** | R's triggers with random passes at L's pass rate | free | Null distribution; checks that the gates are strict enough |
| **IDX** | L's Nifty index-option decisions, tagged separately | small | Exploratory; no verdict before month 4 |
| **OWN** (optional) | The owner's blind take/pass taps on Telegram, at most 10 a day, on the same moments | free | "Would I have done better?" |

**Later:** **M**, a meta-labeler on L's decisions.
- **Model:** logistic regression after ≥ 300 labelled moments; LightGBM after ≥ 1,000.
- **Features:** only those available at decision time, `p_win` among them.
- **Use:** it can only drop or downsize trades.
- **Gate:** out-of-sample AUC ≥ 0.56 on ≥ 600 moments, and M − L ≥ 0.

**Capital per book:** each book trades a **full virtual ₹10L at a fixed R of 0.25%** (no compounding), with its own risk engine and liquidity ledger. Results are reported in R. Splitting the capital between books would change friction, minimum stops and concurrency, so the books would no longer be comparable.

**The value ladder:** R → S (plan) → LD (judgement at the moment) → L (management) → M (meta-filter). Each step is a paired difference with a confidence interval. LLM spend on any step that adds nothing is cut.

### 12.3 Pre-registered questions and statistics

**Primary questions** (Holm correction, 5% family-wise):
1. **Selection IC of L > 0:** day-clustered Spearman correlation between `setup_verdict.exp_R` and `y_default`, across every moment L was asked about.
2. **L > 0 in absolute terms:** net expectancy after trading costs **and** LLM cost. "L beats R" alone is meaningless if R loses.
3. **H − R > 0:** the vetoes add value.
4. **V − LD > 0:** charts add value (only if V survives its early stop).
5. **L − LD > 0:** management adds value.

**Exploratory:** S − R, Hk vs L, E, M − L, IDX, scenario-proposition Brier skill, tradeability-score skill.

**Methods:**
- Day-clustered paired bootstrap with CUPED (index/sector return as covariate) for relative questions.
- SPRT on net R per trade for absolute edge (H0 = 0, H1 = +0.15R), with σ estimated from the data and inflated for within-day clustering.
- Anytime-valid confidence sequences on the leaderboard, so it can be watched daily without inflating false positives.
- At graduation: Deflated Sharpe ratio using the full trial registry, and Hansen's SPA test against R.

**Why discipline matters here.** With 8 zero-edge books at 240 trades each, there is a **36–38% chance one passes a typical gate by luck** (report 16 simulation). Defences:
- the five pre-registered questions;
- the placebo book;
- a fresh confirmation window before any live money;
- live risk allocated on the lower confidence bound.

**How long things take** (about 4 L trades and 25–40 moments a day, σ ≈ 1.3R):

| Question | Needed | Time |
|---|---|---|
| Selection IC (SE ≈ 0.046 at 1,000 moments) | ~1,000 scored moments | **~8 weeks** |
| Value of vetoes (H − R) | ~260 passed triggers | 6–10 weeks |
| Value of management (L − LD) | 100–220 trade pairs | 5–11 weeks |
| Value of charts (V − LD) | 150–250 disagreements | 6–13 weeks |
| L's absolute edge, if it is +0.25R | median ~220 trades | ~11–16 weeks |
| L's absolute edge, if it is +0.15R | median ~410 trades | ~20 weeks |

**Drawdown gates are stated in R, not %.** A genuinely good book (+0.15R, σ ≈ 1.3R) has a median maximum drawdown of about 12.6R over 250 trades, and a 90th percentile of 20R. The paper gate is **max drawdown ≤ 20R**, about 5% at R = 0.25%.

---

## 13. Memory and learning

**Season 1 (the first 8–12 weeks) is frozen.**
- **Logged:** every case, with its situation snapshot, decision, outcome and the counterfactual outcome of passes.
- **Shown to the LLM:** base rates computed **walk-forward** from the rule library (only data before the moment, shrunk toward 0R).
- **Not shown:** no precedent retrieval, no lessons, no prompt edits.

**Case library:**
- One SQLite row per moment, plus snapshot references.
- Post-mortems classify each error as THESIS_WRONG, TIMING, EXECUTION, VARIANCE, RULE_BREAK, GOOD_PASS or MISSED_WINNER, with a process grade that is independent of the outcome.

**Lessons are code-checkable filters, not prose:**

```yaml
- id: L014
  when:   {mode: MOMENTUM, time_after: "13:30", rvol_pctl_lt: 70}
  effect: {cap_size: S, require_tactic: T1_PULLBACK_LIMIT}     # restrict-only, code-enforced
  text:   "Afternoon momentum without volume fades; pullback entries only, small."
  evidence: {n: 31, dR: +0.22, ci90: [0.04, 0.40], holdout_n: 9, holdout_dR: +0.15}
  status: CANDIDATE
```

**Lesson lifecycle:**
- **Weekly:** candidates are generated (Opus batch), backtested over the case library, then tested as **overnight batch challengers on moments after they were proposed**.
- **Season boundary:** promotion only, as a new trader identity, with the **owner's one-tap approval**.
- **Anti-drift rules:** never learn from a single trade; lessons are scoped by regime; the risk constitution is immutable.

**Precedent retrieval (season 2 onward, once n ≥ 300):**
- **Method:** weighted nearest neighbours on about 24 code-computed features, with at least one loser among the 3 shown.
- **Text similarity of catalysts:** a local small embedding model on the CPU.

**Replay dojo:**
- **Source:** recorded post-cutoff days (after the models' June 2026 training cutoff), anonymised (symbols and dates masked), with 30% of days sealed.
- **Use:** prompt regression (flip rate < 10%) and rehearsing new identities. **Never** used as proof of edge.

---

## 14. Trader identity and seasons

**Trader identity** = a hash of:
- model ID and provider;
- prompt template;
- context builder;
- tactic menu;
- chart renderer;
- meta-model;
- risk config.

It gets a readable name, for example `L-Son55-P1`.

**Change classes:**
- **Class 0** (logging, UI): no fork; replaying 5 days must give identical prompt hashes.
- **Class 1** (any prompt, model, context or tactic change): a **new identity with a new track record**.
- **Class 2** (risk, fill or cost models): applied to every book, and every book is re-scored through the COE.

**Seasons:**
- **Length:** 4 weeks. Forks happen only at boundaries, at most one per lineage per season.
- **Paperwork:** each fork has a written hypothesis and is entered in the trial registry.
- **Scoring:** a fork is **never scored on the moments that inspired it**.

**Exclusions:** days with laptop or feed gaps, special sessions (Muhurat on 8 Nov) and provider outages are excluded from *all* books alike.

**Regime coverage before any graduation:**
- ≥ 10 trend days and ≥ 10 range days;
- ≥ 1 results-season month;
- ≥ 3 high-VIX days;
- results reported per regime.

---

## 15. What the owner sees

Most of this is formatted by code from the structured outputs, so it costs almost nothing.

| Item | When | Content |
|---|---|---|
| **Morning game plan** | 08:55 | 3-line market read, day-type prior, tradeability, 5 names × IF-THEN with probabilities, avoid list, risk mode |
| **Watching board** | Live, push on change | Each scenario ARMED / APPROACHING / TRIGGERED / EXPIRED; `/watch` on request |
| **Trade card** | Each trade | Thesis, against-case and invalidation (3 lines), size in R, the chart PNG |
| **Owner taps** | Up to 10 moments a day | Blind take/pass with the chart, 60-second window. Builds the OWN book on the same moments. |
| **Daily journal and leaderboard** | 15:45–16:00 | Plan vs what happened; each decision graded on process; arena leaderboard (net R, expectancy with confidence sequence, SPRT progress, drawdown in R, LLM ₹, net after LLM cost); best 3 vetoes and worst 3 misses |
| **`/why RELIANCE 10:40`** | On demand | Answered from the decision log **and the scanner state**. Often the answer is "the eyes never woke the brain". Haiku quotes the logged fields; it does not re-derive the reasoning. |
| **Weekly arena report** | Saturday | Equity curves in R with bands, calibration plot, regime-coverage meter, value ladder, personality audit, trust meter (progress toward each gate) |
| **Owner controls** | Any time | `/pause`, `/flat`, `/risk down`: risk-reducing only |

**Owner baseline (optional, recommended).** Exporting 12 months of the owner's own broker tradebook sets the honest bar for "instead of my manual trading": net R per month and drawdown. Later, the same data can train an **Owner Twin** persona: the owner's style minus his measured leaks. It is an exploratory book; the data is anonymised before any LLM sees it.

---

## 16. Pre-registered kill and success criteria

**Week-8 checkpoint** (needs ≥ 35 sessions, ≥ 1,000 scored moments, ≥ 120 L trades):

| ID | Test | Kill if |
|---|---|---|
| K1 Selection | Spearman IC of L's `exp_R` vs `y_default` (day-clustered) | Point estimate < 0.03, **or** 90% upper bound < 0.08. Then the LLM-as-selector idea is dead for intraday equity. |
| K2 Veto | Mean `y_default` of R triggers L passed vs those it took (≥ 150 vetoes) | Passed triggers do no worse than taken ones |
| K3 Absolute | L net per trade after trading costs and LLM ₹ | Below −0.10R at ≥ 150 trades, or drawdown > 15R |
| K4 Plan (week 4) | S − R, and the propositions' Brier skill vs climatology | Both ≤ 0: replace the Opus plan with a deterministic watchlist (saves ~₹1k a month) |
| K5 Management | L − LD at ≥ 100 trades | Mean < 0 and the 80% interval excludes +0.05R: exits go back to code |
| K6 Model tier | Hk's IC vs L's IC | Hk ≥ L − 0.02 with ≥ 85% agreement: Haiku becomes primary (saves ~₹1.5k), and the savings buy more moments or an Opus second opinion |
| K7 Operations | Flip rate, schema failures, latency, cost | Flips > 20%, schema failures > 3%, p95 > 25 s, or > ₹7k a month for 2 months after the degrade ladder |
| K-final | SPRT on L's net R (H1 +0.15R), at 16–20 weeks | Reject: stop the LLM-trader approach for intraday equity |

**Success milestones:**

| Milestone | Criteria | Unlocks |
|---|---|---|
| **S1 "promising"** (weeks 8–12) | IC ≥ 0.10 with 90% lower bound > 0; L net ≥ +0.05R per trade after LLM cost over ≥ 150 trades; H − R > 0; no placebo passes any gate; flip rate < 15% | Tiny live L0 probes on the owner's live account |
| **S2 "rely on it"** | ≥ 6 months forward and ≥ 400 trades; ≥ 3 months live; anytime-valid 95% lower bound > 0 after LLM cost; live-vs-paper gap ≤ 0.05R per trade; drawdown ≤ 20R; positive on both trend-day and range-day subsets; **net R per month ≥ the owner's own manual record, with a smaller drawdown** | Replacing manual discretionary trading, at full risk |

**What happens after the week-8 verdict:**

| Evidence | Then |
|---|---|
| IC ≥ 0.10 and L ≥ 0 | Add the meta-labeler (after 600 moments), the index-options LLM book, lesson forks and precedent retrieval, and the Owner Twin |
| V passes | Fork L into a numbers-plus-chart identity at the season boundary |
| Hk ≈ L | Haiku becomes primary; spend the savings on more moments |
| Equity proven | Only then, LLM books for MCX and swing |

---

## 17. Build order (next implementation steps)

1. **Phase-0 gates** (§11): small scripts against OpenRouter: caching, effort, strict JSON, image billing, latency over 200 calls, flip-rate baseline.
2. **Conservative paper exchange and the COE:** re-simulates any action on recorded data, plus the conformance test.
3. **Snapshot and sitrep builder:**
   - level registry with IDs;
   - shape features;
   - catalyst, results, flow and market cards;
   - walk-forward base rates from the rule library on historical candles.
4. **Moment engine:**
   - scenario watchers (condition DSL);
   - rule-library detectors for T1–T9;
   - scanners;
   - de-duplication, caps and burst grouping;
   - the deterministic in-play top 15.
5. **Brain routes:**
   - plan (Opus), open read and re-plan, decisions (Sonnet), management, triage (Haiku), EOD (batch);
   - validators, rationalisation guard, size rules;
   - budget governor and telemetry.
6. **Arena ledger:**
   - moment table and book states for R, S, H, L, LD, P1, Hk, IDX;
   - daily leaderboard, IC, SPRT, Holm;
   - trial registry and identity hashing.
7. **Telegram:** morning plan, watching board, trade cards with chart, owner taps, daily journal, weekly report, `/why`.
8. **Chart renderer**, then the perception gate, then V and E.
9. **Season tooling:** replay dojo (anonymised post-cutoff days), lesson-candidate pipeline, season-boundary forks.

**Arena day 1** is when items 1–7 work end to end for a full unattended paper day.
- **Week 2:** perception gate and V early-stop decision.
- **Week 4:** plan check (K4).
- **Week 8:** kill or continue.
- **Week 12:** go/no-go for live L0 probes.

---

## 18. Risks and open items

- **OpenRouter pass-through is unverified** for effort control, 1-hour cache TTL, image billing, Batch support for Anthropic models, and GST. These are Phase-0 gates; the budget assumes the worst-case exchange rate until then.
- **The IC threshold assumes rough normality.** Real R outcomes are skewed, so the correlation actually needed may be higher.
- **The default bracket drives `y_default`.** A second bracket is used as a sensitivity check.
- **Regime concentration.** The first season covers results season and a market near six-month lows, so a verdict may not generalise. Graduation requires regime coverage.
- **Vendor model updates** under a pinned slug, or deprecations, force an identity fork.
- **The laptop is the single machine.** Any day it is off or loses the feed is lost evidence for every book.
- **Live constraints already in force** (main design §4, §13) apply when going live: static IP for order APIs, daily 2FA, market-order protection, 10 orders/s. ARMED orders therefore use marketable limits with our own price caps.
