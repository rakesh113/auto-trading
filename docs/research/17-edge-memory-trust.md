# Making the LLM trader good enough to rely on: memory, information edges, decision protocol, regime, trust UX, and three new ideas

**Role:** creative AI-trading architect. **Date:** 2026-10-09. **Status:** design only. No files were changed.
**Tags:** [H]/[M]/[L] mark verified facts by confidence. [J] marks my own judgement.

---

## 0. Thesis: where a durable LLM-trader edge comes from

The LLM's edge is not reading price patterns. In the most public live test, Alpha Arena S1 (Oct–Nov 2025, $10k per model, crypto perpetuals), 4 of 6 frontier models lost money: Claude Sonnet 4.5 −30.8%, GPT-5 −62.7%. The organiser noted that each model showed persistent "personality" biases across many prompt versions, and that LLMs handle numeric time series poorly ([Forklog](https://forklog.com/en/four-out-of-six-ai-models-suffer-losses-in-trading-tournament/), [GNcrypto](https://www.gncrypto.news/news/qwen-wins-alpha-arena-season-1-with-22-percent-returns/) [M]). FINSABER tested about 20 years and 100+ symbols and found that reported LLM-strategy advantages mostly disappear. The strategies were too conservative in bull markets and too aggressive in bear markets. The authors' advice is to prioritise regime detection and risk control over framework complexity ([arXiv 2505.07078](https://arxiv.org/html/2505.07078v2) [H]).

**So the edge has to come from six places [J]:**
1. **Selectivity and abstention:** right stock, right day, and many days with no trade.
2. **Catalyst interpretation scaled to company size.**
3. **Combining many weak signals** that rules cannot combine.
4. **Memory of its own base rates.**
5. **Knowing when a thesis has broken.**
6. **Machine discipline.**

The design below aims at exactly these six. Code measures and corrects the LLM's biases.

---

## 1. Memory and learning

### 1.1 Case library: every decision moment, including passes
```
Case/1 { case_id, ts, book_id, model_id, prompt_ver, playbook_ver, mode_tag,
  moment: SCENARIO_TRIGGER|SCENARIO_NEAR|SCAN_HIT|NEWS|POSITION_EVENT,
  situation: { symbol, sector, mcap_bucket, day_type, regime_vec, catalyst{cat, mat, age_min, priced_in},
               features[24] (z-scored, code-computed), plan_scenario_id, plan_prob, chart_ref? },
  decision:  { action, tactic_id, p_t1_before_stop, exp_R, size_tier, thesis, against_case, invalidation[] },
  outcome:   { filled, R_net, MFE_R, MAE_R, mins_in_trade, exit_reason },
  counterfactual: { R_if_default_tactic }        # computed for every PASS and every rejected TAKE
  postmortem: { error_type: THESIS_WRONG|TIMING|EXECUTION|VARIANCE|RULE_BREAK|GOOD_PASS|MISSED_WINNER,
                process_grade A–F (independent of outcome), lesson_candidate? } }
```
**Scoring passes is the key move [J].** Each PASS gets a shadow outcome: what the default tactic for that scenario would have made. This has two effects:
- Labelled data grows about 3–5×, because there are many more moments than trades.
- Abstention skill becomes directly measurable. "Pass quality" is the mean counterfactual R of passes, and it should be ≤ 0.

### 1.2 Retrieval at decision time (computed by code, ≤ 1k tokens)
- **Filters:** moment type, mode, direction and day-type group.
- **Similarity:** weighted kNN on the 24 z-scored features, for example:
  - gap/ATR, RVOL percentile, RS vs Nifty and vs sector, distance to VWAP and to the trigger in ATR
  - OR width/ATR, trend efficiency, time bucket, VIX level and change, breadth
  - OI quadrant, materiality, catalyst age, spread percentile
- **Results:** top 3 by MMR, so the cases differ from each other. At least one of the 3 is a loser if any loser exists in the top 10.
- **Base rates:** shown only when n ≥ 15, with a 60-session half-life (report 05 §9 [H]). They are **shrunk toward a skeptical prior of 0R** (k₀ = 10), and a 90% CI is printed.
- **Embeddings are secondary.** They are used only to compare the text of catalysts.
  - Recommended: local `bge-small`/`e5-small` on CPU. It costs nothing, takes about 10 ms, and needs no network.
  - Fallback: OpenRouter lists embedding models at roughly $0.004–$0.15 per million tokens ([OpenRouter](https://openrouter.ai/compare/perplexity/pplx-embed-v1-0.6b/openai/text-embedding-ada-002), [Bifrost tracker](https://www.getmaxim.ai/bifrost/llm-cost-calculator/provider/openrouter/model/qwen3-embedding-8b) [M]). At about 0.5M tokens a day that is under $0.01 a day.
  - Storage: SQLite plus numpy. Fewer than 50k cases need no vector database.

### 1.3 Lessons stored as testable filters, not prose [J]
FinMem-style layered memory improves results in papers ([arXiv 2311.13743](https://arxiv.org/abs/2311.13743) [H]), but prose memories drift. Here, every lesson must be a condition that code can evaluate:
```yaml
- id: L014
  when: {mode: MOMENTUM, time_after: "13:30", rvol_pctl_lt: 70}
  effect: {cap_tier: S, require_tactic: PULLBACK}      # code enforces; restrict-only
  text: "Afternoon momentum without volume fades; pullback entries only, small."
  evidence: {n: 31, dR: +0.22, ci90: [0.04, 0.40], holdout_n: 9, holdout_dR: +0.15}
  status: PROBATION   scope_regime: [RANGE, DISPERSION]   added: 2026-11-14  review_by: 2026-12-12
```
- **How lessons are applied:** code evaluates `when` and labels the context "Applies: L014", so the LLM does not have to remember lessons. Code enforces `effect`.
- **Size limits:** at most 25 machine lessons plus 5 free-text notes, about 1.5k tokens in total. The playbook is versioned in git.
- **Daily (EOD):** a Sonnet post-mortem per trade and per notable pass produces lesson *candidates*.
- **Weekly (Saturday, Opus batch):** Opus clusters the candidates. Code then backtests each candidate as a filter over the case library, including scored passes.
- **Promotion criteria:**
  - n ≥ 20 affected cases;
  - the 90% CI of ΔR is above 0 on the 8-week fit window;
  - the same sign on a 2-week holdout;
  - then 10 sessions of **targeted shadow**: the main book's decision is re-run with the new playbook only on the moments where the lesson applies (about $0.05–0.10 a day).
- **Anti-drift rules:**
  - Never learn from a single trade.
  - At most 3 promotions a week.
  - Lessons are scoped by regime, so a trending week cannot rewrite range-day behaviour.
  - Parameters are frozen for each evaluation window.
  - The system prompt and risk constitution are immutable without the owner.

**Weekly personality audit**, which follows from the Alpha Arena finding:
- long/short ratio vs breadth
- trades per day
- chase distance (entry minus trigger, in ATR)
- average hold time
- share of off-plan trades
- calibration drift

Each is compared with the control book.

| Change | Automatic | Owner one-tap on Telegram (with an evidence card) | Never |
|---|---|---|---|
| Logging cases, retrieval, base rates, monthly calibration refit | ✓ | | |
| Lesson candidates; probation in targeted shadow | ✓ | | |
| Retiring a *permissive* lesson; tightening caps | ✓ (risk-reducing) | | |
| Promoting a lesson to production; retiring a *restrictive* lesson | | ✓ | |
| System prompt, mode cards, tactic menu, model swap, enabling a book live | | ✓ | |
| Risk limits, sizing math, stops | | | ✓ (code only) |

---

## 2. Specialist personas vs one generalist

**Recommendation: one trader brain with "mode cards", plus mode tags for attribution [J].**
- **Statistical power:** about 205 trades per setup are needed for an SPRT decision (design doc §12, report 07 [H]). Four persona books at 1–2 trades a day would take 5–10 months *each* to prove anything.
- **Budget:** four Sonnet personas cost about four times as much in decision calls.
- **How mode cards work:** code picks a mode card (≤ 300 tokens) for each moment from the moment type and the regime. The cards are CATALYST (second-leg continuation after news), MOMENTUM, FADE and INDEX-OPT. The decision is tagged with the mode, so you get per-mode expectancy for free.
- **When to split:** a mode becomes its own book only once its tagged stats show an edge and budget allows.
- **Exception: index options are a separate book from day 1.** The instrument, risk bucket and time windows all differ, and there are only 1–3 decisions a day, so it is cheap.
- **What the arena compares instead:** *approaches* (control, discretionary LLM, LLM veto, model tier, vision, owner twin), not personas.

---

## 3. Information edges at low cost

| Source | When available | Intraday value | Presentation to the LLM |
|---|---|---|---|
| NSE/BSE Reg 30 filings | Real time (scraped) | **H** | **Catalyst card** (≤ 150 tokens): category, order value ÷ trailing-12-month revenue, % of market cap, **value ÷ 20-day average turnover** [J: catches small caps where a ₹200 cr order dwarfs ₹20 cr of daily turnover], reaction since t0, pre-t0 drift, priced-in share |
| Results (XBRL, parsed deterministically, report 05 [M]) | Event | **H** in season | **Results card** with consensus *proxies* (below) |
| RVOL, RS, sector rotation | Live | **H** (selection) | Sector RS heatmap over 15 min and the day; rank within sector |
| F&O OI buildup; option-chain shifts | Live (feed) | **H** index, **M** stocks | **Flow card**: OI quadrant, writing or migration at the top-3 strikes, PCR change, ATM IV percentile |
| India VIX, breadth | Live | **H** (regime) | Market card |
| GIFT Nifty, US futures, Brent, USDINR, Asia | Pre-market | **M** (day prior) | 08:30 game-plan input only |
| Block deals: windows 08:45–09:00 (reference: previous close) and 14:05–14:20 (reference: 13:45–14:00 VWAP); minimum ₹25 cr; ±3% band; effective Dec 2025 ([NSE circular CMTR71394](https://nsearchives.nseindia.com/content/circulars/CMTR71394.pdf), [Business Standard](https://www.business-standard.com/markets/news/sebi-eases-block-deal-norms-introduces-same-day-settlement-125100801173_1.html) [H-M]) | Window, then details after market close | **M** | Scanner flag: "block window volume spike"; a discount above 3% means supply (report 03 [M]) |
| Bulk deals, FII/DII cash, participant-wise OI | End of day ([BSE participant reports](https://bseindia.com/markets/Derivatives/DeriReports/DeriMarketDisclosures_pg.aspx) [M]; NSE release time unverified) | L intraday | Game-plan context only |
| Promoter pledge invocation (SAST), PIT insider trades | Disclosure lag of days [M] | L intraday, M swing | Avoid-list and swing bias |
| Corporate actions, F&O ban, ASM/GSM, index rebalances | Calendar | Hygiene | Hard filters; level adjustment; "avoid into close" flags |

**Consensus proxies, since there is no paid feed [J]:**
1. **Surprise vs the company's own trend:** actual minus a blend of the 4-quarter YoY trend and the same quarter last year, in percentage points, for revenue and EBITDA margin.
2. **Options-implied move:** ATM straddle ÷ spot the day before results, then the first-5-minute reaction ÷ implied move. This tells the LLM whether *the market* treats the result as a surprise.
3. **Pre-results drift:** 10-day abnormal return, which shows expectations already in the price.
4. **Peer read-across:** median surprise among sector peers that have already reported this season.
5. **Stored guidance text** from last quarter.

The first 3–5 minutes of abnormal return and volume is itself the best consensus estimate, which matches report 03's "wait 3–5 min" [M].

---

## 4. Better decisions than a single call

### 4.1 Decision call (one call; the schema order forces skepticism)
```
SYSTEM (cached 1h): constitution (code owns size/stops; PASS is the default; never widen a stop or add to a loser)
  + mode card + playbook vN
CONTEXT: market card (cached per 15 min) → game-plan excerpt for SYMBOL (the IF-THEN + its 08:50 probability)
  → MOMENT ("S2: close > L.ORH15 with RVOL p90, 10:41:05") → sitrep → catalyst/flow cards
  → precedents (code) → book state (takes 1/4, day −0.4R) → tactics menu
  (T1 stop-limit break, T2 pullback to L.VWAP, T3 retest of L.ORH15, PASS)

Decision/1 { sitrep_as_of,
  plan_alignment: AS_PLANNED|MODIFIED|CONTRADICTS, new_info_ids[],      # 1. what changed since the plan?
  against_case (≤40w), premortem: "it's 13:00 and this lost 1R because…",  # 2. skeptic first
  base_rate_view: AGREES|DISAGREES|NO_DATA,                              # 3. anchor
  action: TAKE|PASS|WAIT_FOR{tactic, expiry_min}, direction, tactic_id,  # 4. decide
  stop_ref, target_ref (level IDs ± ATR), p_t1_before_stop, exp_R, size_tier_request: S|M|L,
  thesis (≤3 lines), invalidation[{LEVEL|EVENT|TIME, ref}], mode_tag }
```
**Code enforces five rules on this output:**
- **Rationalisation guard:** `CONTRADICTS` or `MODIFIED` must cite a `new_info_id` that arrived after the plan. Otherwise the decision is auto-rejected. If p_t1 jumps more than 0.25 above the morning probability with no new info, it is flagged.
- **Final size** = min(the request; the calibration cap; a cap of M when precedent n < 15; a cap of S when the decision contradicts the plan; the regime multiplier; the drawdown ladder).
  - Confidence has no effect on size until there are ≥ 100 resolved decisions and an isotonic calibration map (report 05 §8 [H]).
  - The tiers are S/M/L = 0.5/0.75/1.0× the current R.
- **Pre-clearance at NEAR, which removes latency [J]:** when price comes within 0.3 ATR of a trigger, the LLM is called *before* the trigger. It returns a conditional TAKE valid for 10 min, with guard conditions. Code then fires instantly on the trigger if the guards still hold. A Sonnet call takes 5–15 s, which would otherwise be too slow for a breakout.
- **Chase guard:** the context states the entry distance beyond the trigger, in ATR.
- **Scarcity:** a cap of 4 TAKEs a day per book. Scarcity buys selectivity. A borderline p (0.45–0.55) means PASS.

**Devil's advocate:** only for size tier L, for swing holds, and after 2 losses. It is a blind-first second opinion (report 05 protocol) from Opus or another vendor's model on OpenRouter, about 2 calls a day.

**Position management:** `Manage/1 {HOLD|TIGHTEN(level_ref)|PARTIAL(33|50)|EXIT, thesis_status: INTACT|WEAKENED|BROKEN, evidence_ids[]}`.
- Haiku handles management first and escalates to Sonnet on WEAKENED.
- Changes can only tighten.
- The hard stops stay at the broker.

---

## 5. Regime awareness and "don't trade today"

The deterministic day-type classifier from design doc §8 decides which modes are allowed:

| State | Modes allowed | Max LLM takes | Size |
|---|---|---|---|
| Trend / gap-and-go | MOMENTUM, CATALYST, INDEX-OPT buys | 4 | 1.0 |
| Dispersion | CATALYST, stock-specific MOMENTUM | 4 | 1.0 |
| Gap-and-fade / range | FADE, CATALYST; index iron fly only on expiry days | 3 | 0.75 |
| Compressed / pre-event | CATALYST only | 2 | 0.5 |
| High-vol event | CATALYST A+ only, after 10:30 | 1 | 0.5 |
| **SIT-OUT** | Manage open positions only | 0 | 0 |

**SIT-OUT triggers [J]:**
- VIX +8% at the open together with a headline-driven gap ≥ 1 ATR. For scale, the 8 Jul 2026 headline shock moved VIX +26% (report 03 F13 [M]).
- A binary event in session (RBI, Budget), until 30 min after it.
- A feed or data-quality fault.
- Drawdown ladder at stage 2 or worse.
- The rolling 20-day Brier score worse than climatology.

**Tradeability score (0–100) at 09:40**, produced by the LLM and code together:
- It is **scored against the control book's daily P&L**, which serves as the ground truth for "was today good for systematic setups".
- This gives a clean and cheap test of whether "don't trade" judgement adds value.
- Below 35: one A+ catalyst trade at most.
- Current context: FIIs have been net sellers for 15 months and Nifty is near a six-month low (report 03 F13 [M]). The audit should watch for a long bias.

---

## 6. Trust-building UX (mostly code-formatted, so close to zero LLM cost)

| Item | When | How it is produced | Cost |
|---|---|---|---|
| **Morning game plan:** 3-line market read, day prior, tradeability, 5 names × IF-THEN with probabilities, avoid list, risk mode | 08:55 | Templated from the GamePlan JSON | ₹0 extra |
| **"Watching" board:** each scenario ARMED / NEAR / TRIGGERED / EXPIRED; pushes only on changes; `/watch` on request | Live | Code | ₹0 |
| **Trade card:** thesis, against-case and invalidation as 3 lines; ₹ risk and R; a **chart PNG rendered by code** (5-min candles, VWAP, levels labelled with their IDs) | Each trade | Decision fields plus mplfinance | ₹0 |
| **EOD journal:** plan vs what happened, each decision graded on process, lesson candidates, tomorrow's watchlist | 16:00 | Sonnet | about ₹14 |
| **`/why RELIANCE 10:40`** | On demand | Looks up the decision log *and the scanner state* (many "skips" were the eyes, not the brain: "in-play score 41 < 55, no scenario armed"). Haiku must quote the logged fields and must not re-derive the reasoning. | about ₹0.3 per question |
| **Weekly arena report:** equity curves, expectancy ± CI, **SPRT progress bars**, PF, max DD, pass quality, calibration curve, ₹ LLM per trade, **P&L net of LLM cost**, Gate-1 checklist | Saturday | Code tables plus a 1-paragraph Opus commentary | about ₹30 |
| **Owner controls:** `/pause`, `/flat`, `/risk down` | Any time | Risk-reducing only | ₹0 |

---

## 7. Arena, chart images, and three new ideas

**Shared eyes, paired books [J].** Every LLM book decides on the *same* moments, so comparisons are paired. That needs about 380 paired decisions to resolve 0.1R (report 05 §8 [H]), instead of independent samples.

**Phase-1 books:**
- **B0:** rules-only control.
- **B1:** Sonnet trader with full discretion.
- **B2:** rules propose, Haiku vetoes.
- **B3:** Haiku trader, running the same prompt as B1.
- **B3v:** B3 plus one chart image.
- **IDX:** the index-options book.

**Chart images (decided).**
- **Numeric-first for the LLM.** Code already turns what a chart shows into numbers and labels, such as "15m HH/HL ×3" and the level table. Multimodal models still struggle with fine-grained reading of candlestick geometry ([arXiv 2607.15414](https://arxiv.org/pdf/2607.15414), which cites MME-Finance and FinChart-Bench [M]). Charts combined with numbers can help forecasting ([VISTA, arXiv 2505.18570](https://arxiv.org/html/2505.18570v1) [M]), but the evidence on actual trading returns is thin.
- **The test is nearly free.** An image is about 1k tokens, roughly $0.0001 on Haiku.
- **Promotion rule:** B3v must beat B3 by ≥ 0.1R over about 380 paired decisions. If it does, B1 gets images too.
- **Charts always go to the owner.**

**Novel idea A: Owner Twin ("keep your edge, remove your leaks").**
- **Inputs:** the owner's broker tradebook CSV, 6–24 months.
- **Rebuild:** the situation at each entry is rebuilt from historical candles (no depth).
- **Opus batch outputs (one-time, about $5–15):**
  - an **Owner Style Card** (≤ 800 tokens);
  - 8 exemplar trades;
  - a **Leak list**: conditions with negative expectancy, such as after 2 losses, averaging down, late entries, or a weak sector. Code enforces the leak list as filters.
- **Book B4:** a twin with the leaks filtered out, from week 3.
- **Why it matters:** it is the most persuasive benchmark of all, "can the machine trade like me minus my mistakes?", and it builds trust because the owner recognises the decisions.
- **Risks:** a small sample; past regimes differ; his data goes to a US-hosted model (anonymise it).

**Novel idea B: Scenario markets.**
- **What:** the game plan pre-commits **20–40 binary propositions** that code can resolve:
  - "S1 triggers before 11:30"
  - "if triggered, T1 before stop"
  - "Nifty closes above PDC"
  - "TREND label by 10:30"
- **Scoring:** code resolves them at EOD. Brier and log score are measured against climatology taken from B0's base rates.
- **Why:** about 600 forecasts a month gives **a skill signal in 2–4 weeks instead of 4+ months**. It feeds the calibration map and the rationalisation guard.
- **Cheap model comparison:** Haiku answers the same propositions for about $0.005 a day, which shows whether Sonnet or Opus earns its cost.
- **Cost:** about 1k extra output tokens a day.

**Novel idea C: Replay dojo.**
- **What:** recorded post-cutoff days (after 1 Jul 2026; model cutoff June 2026 [H]) replayed through the full engine. Symbols and dates are anonymised, because company names distort LLM judgements more than look-ahead does (Glasserman & Lin, [arXiv 2309.17322](https://arxiv.org/abs/2309.17322) [H]).
- **Holdout:** 30% of recorded days are sealed so that no human or prompt author ever looks at them.
- **Uses:** prompt regression (flip rate < 10%) and rehearsing new playbooks or models before they reach the arena. It is **not** used to prove an edge.
- **Budget:** about $4 a month (Haiku days, plus a couple of Sonnet days).

---

## 8. Budget (Haiku $0.10/$0.50, Sonnet $2/$10, Opus $4/$20 per million tokens; Batch −50%) (report 05 [H])

| Item | Model | Calls/day | $/day |
|---|---|---|---|
| Game plan + scenario probabilities (≤ 8 tool calls) | Opus 5.5 | 1 | 0.50 |
| 09:12 pre-open refresh | Sonnet | 1 | 0.05 |
| Filings triage, after the rule pre-filter | Haiku | ~400 | 0.08 |
| Materiality | Haiku → Sonnet | ~6 escalations | 0.24 |
| B1 decisions, low effort, max 1.5k output, 1h cache | Sonnet | ~25 (code cap 40) | 0.63 |
| B1 position management | Haiku → Sonnet | 40 + 8 | 0.20 |
| B2, B3 and B3v | Haiku | ~75 | 0.11 |
| Devil's advocate | Opus | ~2 | 0.12 |
| EOD journal and post-mortems (per-trade via batch) | Sonnet | — | 0.15 |
| Telegram Q&A | Haiku | ~10 | 0.03 |
| **Daily total** | | | **≈ 2.11** |

**Monthly total:** 21 × 2.11 = $44, plus weekly Opus batch $6.5, plus replay $4, ≈ **$55 a month**, plus a one-time $10 for the Owner Twin.

**Landed cost in rupees:** $55 × ₹95, plus OpenRouter's 5.5% credit fee ([TrueFoundry](https://www.truefoundry.com/blog/openrouter-pricing) [M]) and about 3.5% card forex markup [L], comes to **≈ ₹5.7k**. If 18% GST also applies, it is about ₹6.7k [L, verify].

**Guards:**
- A hard monthly cap of $62.
- A daily soft cap of $2.50.
- Degrade ladder: devil's advocate moves to Sonnet, then B1 moves to Haiku, then the game plan moves to Sonnet.
- Buy credits in top-ups of $50 or more, because of the $0.80 minimum fee.

---

## Top 5 recommendations

1. **Run the paired arena from day 1 on shared eyes:** B0 control, B1 Sonnet trader, B2 Haiku veto, B3 / B3v Haiku numeric vs vision, and IDX. Add the Owner Twin in week 3. That is about ₹5.7–6.7k a month. A book goes live only after Gate 1 on conservative fills, net of its LLM cost.
2. **Build a case library that scores passes**, with precedents computed by code (numeric kNN, a skeptical 0R prior, local embeddings) and **lessons stored as code-checkable filters** that pass a holdout and targeted shadow before promotion. The LLM never edits its own prompt, and automatic changes may only reduce risk.
3. **Use the skeptic-first `Decision/1` schema** with a plan-alignment rationalisation guard, pre-clearance at NEAR, PASS as the default, a cap of 4 takes a day, and size tiers that unlock only after calibration.
4. **Run scenario markets and a tradeability score**, scored daily against outcomes and against the control book's P&L. This gives a fast, statistically powered skill signal and a measured "don't trade today" edge, with SIT-OUT days as a regime.
5. **Make trust UX a by-product of structured outputs:** the morning plan, the 3-line trade card with a code-rendered chart, `/why` answered from logs (including scanner state), and a weekly arena report with SPRT progress and P&L net of LLM cost.

## Risks and unknowns

- **The discretionary LLM may not beat the control book after costs.** FINSABER and Alpha Arena both show fragility [H/M]. The proof takes 10–20 weeks per book, and a lucky streak could build false trust before SPRT decides.
- **Budget tails:** thinking tokens on Opus cannot be disabled; cache-write churn; whether GST applies and how much the card forex markup is [L]. The day-1 telemetry must check $/call against the table above.
- **Researcher leakage in replay**, and a future model with a later cutoff silently contaminating the golden set. Pin model IDs in OpenRouter routes and re-cut the sets whenever a model changes.
- **Owner Twin:** sample size, regime mismatch, and privacy of his trade data. If his history is negative overall, the twin becomes a "what not to do" benchmark.
- **Data:** NSE scraping reliability and terms of use [M]; the release time of participant-wise OI is unverified; consensus proxies are not true consensus estimates.
- **Lesson-filter overfitting** if many candidates are tested. Keep a registry of everything tried and report deflated statistics (design doc §12).