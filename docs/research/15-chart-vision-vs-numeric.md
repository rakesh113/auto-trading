# Chart images vs numbers for the LLM trader: recommendation and experiment design

## 0. Bottom line

- **Numbers are the source of truth. A chart image is an optional view of the same data.** The primary LLM-trader book decides from the numeric situation report, the scenario card and level IDs. No price read off an image can reach the order system: orders accept level IDs only, and code computes every price. [J]
- The studies show what vision models can do with charts. They read broad shape well: trend, choppiness, how stretched price is. They do badly at exact values and at naming candlestick patterns. They also lean toward continuing the past trend and toward going long. That broad shape is exactly what is hard to put compactly into numbers, so a chart could add something. Whether it does with the 2026 Claude models is unknown, so we test it rather than assume it. [J]
- **Image tokens are cheap: about 1,850 tokens per chart, roughly ₹0.35 on Sonnet 5.5. The real cost of the chart arm is the second decision call**, about ₹1.1–1.4k a month. This fits inside ₹5–7k.
- **Decision:**
  - The primary book is numeric-only ("N").
  - The identical prompt plus one chart ("N+V") runs as a paired shadow arm on every trigger moment, scored on simulated "what if we had taken it" outcomes.
  - Pre-market plans get a chart on a random 50% of symbol-days.
  - After about 6 weeks, pre-registered rules decide. If the result is unclear, numbers-only wins.

---

## 1. Evidence

### 1a. Findings from the research

| # | Finding | Source | Conf. |
|---|---|---|---|
| E1 | **Seven commercial vision models forecasting from daily and weekly candlestick charts.** Most did well only in persistent up- or downtrends and were weak in normal markets. They showed clear prediction biases and ignored the forecast horizon the prompt asked for. An XGBoost baseline was the most stable performer. The best vision model was Claude Sonnet 4.5 with thinking. | Hu et al. 2026, ["Do VLMs Truly 'Read' Candlesticks?"](https://arxiv.org/abs/2604.12659) (from the abstract and summaries; I could not read the full text) | M |
| E2 | **Controlled tests of whether models read candles or just follow the trend.** Models weight past trend heavily. Their response to the actual candlestick evidence is zero or in the wrong direction. When a candlestick signal was injected into otherwise matched charts, models ignored it or moved against it. Ordinary chart benchmarks cannot detect this. | Wang 2026, [Martingale Doppelgänger-Eval](https://arxiv.org/pdf/2606.17423) (abstract) | M |
| E3 | **Practitioner test with production gates (April 2026).** 215 calls on Haiku 4.5, Opus 4.7, Sonnet 4.6 and Gemini 3 Flash, with thinking off and n=40 real signals. Pattern naming was correct **1 time in 215**. Direction accuracy was 51–57%, and every 95% confidence interval included 50%. Confidence did not correlate with being right (r ≈ 0). Long bias: Gemini scored 100% on longs and 10% on shorts; Opus 4.7 had a 49-point gap. The author recommends a chart plus numeric features. The author sells a signals product, and the sample is small. | [Antonov gist / Zenodo](https://gist.github.com/roman-rr/c1cd675f7c35b68ae5ac281c30080166) | M on the numbers, L on generalising |
| E4 | **Simple geometry tests.** Vision models averaged about 58% on simple geometric tasks. Counting where two lines cross scored 41–76%. The paper locates the failure in decoding what the encoder sees, not in perception itself. | [Rahmanzadehgervi et al., ACCV 2024](https://openaccess.thecvf.com/content/ACCV2024/papers/Rahmanzadehgervi_Vision_language_models_are_blind_ACCV_2024_paper.pdf) | H |
| E5 | **Plots versus raw number series.** Plotting a time series beat feeding the raw numbers for time-series reasoning: about 140% average improvement and about 99% fewer tokens. Example: GPT-4o zero-shot went from 50.0% to 70.0% on one task. | [Liu et al., NAACL 2025 (TimerBed/VL-Time)](https://arxiv.org/abs/2411.06018) | H (claim), M (exact numbers) |
| E6 | **Text numbers in a trading simulation.** Given plain-text numbers, models fixate on absolute values and miss percentage changes and relationships. Charts improved numerical reasoning and trading in their simulation. | [Agent Trading Arena, EMNLP Findings 2025](https://aclanthology.org/2025.findings-emnlp.294.pdf) | M |
| E7 | **LLM time-series forecasters.** Removing the LLM, or replacing it with a simple attention layer, did not hurt forecasting; usually it improved. | [Tan et al., NeurIPS 2024](https://proceedings.neurips.cc/paper_files/paper/2024/hash/6ed5bf446f59e2c6646d23058c86424b-Abstract.html) | H |
| E8 | **General chart benchmarks.** Real-chart reasoning: GPT-4o 47.1% vs humans 80.5% ([CharXiv](https://arxiv.org/pdf/2406.18521), H). Financial multimodal QA: top models just over 50% ([FinMME, ACL 2025](https://aclanthology.org/2025.acl-long.1426.pdf), M). Chart summaries: 199 hallucinations in 1,083 sentences ([ChartInsighter](https://arxiv.org/pdf/2501.09349), M). | as linked | H/M |
| E9 | **Chart-only vs numeric for stock moves.** A model reading candlestick charts alone did worse than numeric models until its biases were calibrated ([Chen, IJACSA 2025](https://www.thesai.org/Downloads/Volume16No4/Paper_2-Comparing_Vision_Instruct_LLMs_Vision_Based_Deep_Learning.pdf)). Chart plus text beat text alone, by the authors' own figures ([VISTA](https://arxiv.org/pdf/2505.18570)). | as linked | M / L–M |
| E10 | **Anthropic's own claims (vendor-reported).** Opus 5.5 reads charts more accurately than Opus 5 at every effort level; even at low effort it beat Opus 5 at maximum, using about a tenth of the output tokens. For dense charts on Sonnet 5.5, crop/zoom tools help more than raising effort. Claude's vision docs list the limits: approximate spatial reasoning, approximate counting, errors on small images. | claude-api skill (model notes, Oct 2026); [Vision docs](https://platform.claude.com/docs/en/build-with-claude/vision) | M (vendor), H (limits) |

### 1b. What this means for us [J]

1. **Never take a number from the image.** Exact values, counts and where lines cross are the weakest skills (E4, E8).
2. **Never ask the model to name a pattern.** It fails almost completely (E3), and the models do not actually use candlestick evidence (E2).
3. **Broad shape is the only plausible gain:** a clean trend versus overlapping chop, how impulsive the move into a level was, how far price has stretched from its base, clusters of levels, the character of volume. A discretionary trader uses charts for exactly this. Good numeric features capture part of it, but a 125-bar daily history does not compress well.
4. **The main bias to watch is trend-following plus long bias** (E1–E3). A rules book does trend-following for free. If the chart arm's extra profit comes only from trend days, that is not skill. Report results split by day type.
5. **The fair comparison is "good features" versus "good features plus a chart".** Raw numbers versus a chart is a straw man. E5 and E6 beat *raw numeric series*, which our situation report already never shows.
6. **Most studies used 2024–2025 models.** E10 suggests the 5.5 generation is clearly better at charts. That justifies running an experiment, not adopting vision outright.

### 1c. Feeding price data as text

- **Weak:** long raw OHLC dumps. They cost about 8–12 tokens per bar, invite arithmetic errors, and make the model anchor on absolute prices (E6, E7). How numbers split into tokens also matters (Gruver et al., LLMTime, NeurIPS 2023 [H]).
- **Strong:** features code has already computed: basis points, ATR multiples, percentiles, categorical states, level IDs with distances. These are compact, exact and checkable, and they are what the existing situation report convention uses (report 05 §2).
- **New numeric "shape" features for arm N** [J]. These keep the comparison fair, at about 120 tokens:
  - **Efficiency ratio** (net move ÷ total path length, Kaufman) for today and for the last 10 bars.
  - **Overlap:** share of the last 10 bars whose range overlaps the previous bar.
  - Pullback depth in ATR, and number of tests of the trigger level.
  - Volume slope into the trigger.
  - **Swing sequence**, for example `HH HL HH HL LH`.
  - **24-digit text sparkline:** today's 3-min closes scaled into digits 0–9, for example `012334567789887789`. It costs about 24 tokens and gives the exact shape.

---

## 2. Image token cost and latency

**Formula** [H, Vision docs, fetched 9 Oct 2026]:
- Visual tokens = ⌈width ÷ 28⌉ × ⌈height ÷ 28⌉. Each token is one 28×28-pixel patch.
- **High-resolution tier (Claude 4.7 and later): up to 2,576 px on the long edge, up to 4,784 tokens per image.** Larger images are scaled down. Standard tier: 1,568 px and 1,568 tokens.
- Haiku 5.5 falls under "4.7 and later", so I assume it is in the high-resolution tier [M].
- Put images before text. PNG is the right format; heavy JPEG compression damages text in the image.

**Proposed size: 1400×1036 px** (50×37 patches) = **1,850 tokens**. Both dimensions are multiples of 28, so no patch is wasted.

| Model (via OpenRouter) | Input $/MTok | Per chart | 630 charts/month (30/day) |
|---|---|---|---|
| Haiku 5.5 | 0.10 | $0.00019 | $0.12 (≈₹11) |
| Sonnet 5.5 | 2.00 | $0.0037 (≈₹0.35) | $2.33 (≈₹221) |
| Opus 5.5 | 4.00 | $0.0074 | $4.66 (≈₹443) |
| Fable 5.1 | 10.00 | $0.0185 | $11.66 (≈₹1,108) |

- These are before GST and OpenRouter's credit-purchase fee. Prices are from the skill's model table [H] and OpenRouter's listing for Haiku 5.5 [M].
- **OpenRouter billing:** inference is passed through with no markup [M, OpenRouter FAQ]. That images are billed as ordinary input tokens is my inference [M]. **Phase-0 check:** send one 1400×1036 PNG to Haiku and Sonnet and confirm prompt tokens ≈ text + 1,850.
- **Caching:** images can sit in a cached prefix. But each moment's chart is new, so caching only helps the daily panel. Ignore it.
- **Latency** [J, measure in Phase 0]:
  - Extra prompt processing for 1,850 tokens: about 0.2–0.5 s.
  - Upload of about 150 KB as base64: about 0.1–0.3 s.
  - Rendering adds roughly nothing at trigger time if the chart is pre-rendered (see §3).
  - Target p95 from trigger to decision: ≤ 6 s numeric, ≤ 7 s with chart.

---

## 3. Chart design

### 3a. One source of truth

- An immutable `SituationSnapshot` (bars, VWAP series, level registry, scenario card, position, `snapshot_id`, `as_of`) produces **both** the text situation report and the PNG. Both are pure functions of the snapshot.
- The chart header prints `snapshot_id` and `as_of`. The model must echo `snapshot_id`; a mismatch rejects the call.
- Every horizontal line on the chart is a registry object, labelled with **the same ID and value as the text**, for example `L.PDH 1404.5`.
- Code never draws trendlines or patterns. A trendline appears only if it is a registry object with an ID, such as `TL.D1`.
- Each PNG and its SHA-256 hash go to the journal for replay (about 120 KB each).

### 3b. Two templates from one renderer

**Intraday template (1400×1036), used for trigger moments and the post-market review:**
- **Header strip (36 px):** symbol, snapshot_id, as_of (IST), "1 ATR(14d) = ₹24.5", scenario ID and state.
- **Panel A (left, 860×1000), today on 3-min bars:**
  - Bars from 09:15 plus the last 20 bars of the prior day, separated by a gap marker.
  - Session VWAP (solid), ±1σ and ±2σ bands (dashed), opening-range box (shaded).
  - Registry levels.
  - Scenario overlay: trigger zone as a translucent band, and E / S / T1 / T2 lines.
  - Current position's entry and current stop, if one is open.
  - A "now" marker.
  - Volume in the bottom 18%, with a dotted line for the time-of-day average (shows relative volume visually).
  - A thin strip showing relative strength vs Nifty, rebased at 09:15. This shows divergence shape, which charts convey well.
- **Panel B (top right, 540×500):** 15-min bars for 5 sessions, labelled day separators, prior-day high/low.
- **Panel C (bottom right, 540×500):** daily bars for 6 months, 20/50 EMA, 200-DMA if it is in range, daily swing levels, 52-week high marker, earnings-day markers.

**Pre-market template:**
- Daily 9 months as the large panel, weekly 2 years and 15-min 5 sessions as the small panels.
- Same size and same registry labels.

**Styling (fixed for every symbol):**
- White background, up bars #26A69A, down bars #EF5350 (the most common convention).
- Levels coloured **by type, not by side of price**: prior-day levels grey, opening range orange, swing levels purple, round numbers light grey dotted. Stop red, targets green, entry black.
- Labels 13–14 px DejaVu Sans, placed so they do not collide.
- **Fixed scaling in ATR terms:** Panel A's price range is at least ±2.5 daily ATR, so a 0.3% move cannot look like a crash. Thin price-axis ticks.
- **Never drawn:** RSI/MACD panels, pattern labels, profit-or-loss colouring, buy/sell arrows from rules.
- Each 28-px patch covers about 5 candles. The model sees structure, not candle-level micro-patterns, which matches what the evidence says it can do.

### 3c. Rendering on the Windows laptop

- **Plain matplotlib (Agg backend)** with a roughly 150-line custom candle drawer (PolyCollection + LineCollection).
- Runs in a **warm process pool (1–2 workers, spawn start)** so it never blocks the asyncio loop. Matplotlib is not thread-safe.
- Reuse figures or always call `plt.close`, otherwise memory leaks.
- mplfinance is acceptable for a prototype, but it gives less control over labels.
- **Avoid plotly + kaleido.** Kaleido v1 drives a Chrome process, which is slow and fragile on Windows [M]. Browser-based charting libraries are out for the same reason.
- Expected render time 80–250 ms warm [J]. Gate: p95 ≤ 250 ms.
- **Caching:** cache key = (symbol, last_bar_ts, levels_version, plan_version, position_version).
  - Pre-render when a scenario is armed (price within 0.3 ATR of its trigger), and refresh on each 3-min bar close.
  - At the trigger, reuse the cached image, or re-render if the bar has rolled over.

### 3d. Consistency tests

- Property tests: every label drawn equals its registry entry; the snapshot_id round-trips.
- **Perception gate before the experiment (Phase 0, about $0.25):** 50 synthetic snapshots, chart only. The model must answer whether price is above VWAP, the nearest labelled level above and below, and the 15-min trend.
  - Need ≥ 95% on Sonnet 5.5, otherwise fix the chart design or drop vision.
  - Re-run the same 20 charts every night as a canary for drift.

---

## 4. Failure modes and mitigations

| Failure | Mitigation |
|---|---|
| **Model invents levels or prices from the image** | Orders accept level IDs only. Prose fact-check stays at ±2% of report values. Pre-market only: the model may *request* a new level as `{"type":"swing_high","tf":"D","date_range":[…]}`. Code finds the real pivot within 0.5 ATR, gives it an ID, or rejects the request. |
| **Chart and numbers disagree** | One snapshot produces both, with a snapshot_id echo. Prompt rule: "if they conflict, trust the report and set `chart_conflict=true`". Any conflict flag is treated as a renderer bug. |
| **Model misreads the chart** | Both arms must fill a `perception_check` block, which code verifies against the snapshot. **One mismatch halves the size; two veto the trade.** The misread rate is reported per arm. |
| **Trend-following or long bias** | Every symbol gets symmetric long and short scenarios. Results split by day type and direction. **Monthly mirror audit** [J], inspired by E2: invert 60 past moments (flip the chart vertically, negate the numeric features, swap support and resistance) and check that decisions flip long↔short. A gap of more than 10 points fails. |
| **Anchoring on salient visuals** (one huge candle, autoscale making small moves look big) | Fixed ATR-based scaling, fixed bar counts, minimal overlays, a "1 ATR = ₹x" scale note on the chart. |
| **Treating decision noise as a modality effect** | Temperature cannot be set to 0 on Haiku or Sonnet 5.5 (the skill docs say non-default sampling returns an error). Add a **repeat arm N′**: arm N re-run on 15% of moments, to measure the noise floor. |
| **Cost blow-up** | Exactly one image per decision call. No images left in conversation history. Pre-market `get_chart` tool capped at 3 calls per plan. Image tokens tracked separately. Budget degrade order: the chart arm drops to 50% sampling, then 25%, before anything else is cut. |

---

## 5. Decision and experiment design

**Primary book: N.** It sees the situation report, the shape features from §1c and the scenario card. The decision model is whatever the team picks; I assume Sonnet 5.5 at low effort. Position management is numeric-only.

**Arms, all on the same trigger moments:**

| Arm | What it sees | Coverage | ≈ Cost/month incl. GST and fees |
|---|---|---|---|
| N (primary, executes in its own paper book) | numbers | 100% | (core budget) |
| **N+V** (its own paper book in the arena) | the same prompt plus one 1400×1036 chart | 100% | ₹1.1–1.4k |
| N′ (noise floor) | a repeat of N | random 15% | ₹150 |
| Optional: Haiku-N / Haiku-N+V | the same, on Haiku 5.5 | 100% | ≈ ₹130 total; tests whether a cheap model plus chart is good enough |
| Pre-market plans | chart on a random 50% of symbol-days, balanced by gap direction | about 12 symbols/day | ≈ ₹60 |

- Duplicate Sonnet decision call: about $0.0142 for text plus $0.0037 for the image, 630 a month, about $11.3.
- Total spend on vision is about ₹1.6–1.9k a month at 30 moments/day. That leaves ₹3.5–5k inside the ₹5–7k budget for the plan writer, triage and reviews. The moment rate of 30/day is my assumption.

**Scoring: a ledger of simulated outcomes.** Comparing book P&L directly is noisy and depends on the order of trades, so score each decision instead.
- For each moment *m*, the conservative paper broker simulates on recorded ticks the scenario's default trade (entry tactic, stop ID, targets, time stop), net of costs. Call the result R_m. An ADJUST decision is simulated with its own settings.
- Value of an arm's decision: V = 0 for PASS, and size_mult × R for TAKE or ADJUST.
- **Primary metric:** Δ_m = V(N+V) − V(N), averaged over **moments where the two arms' decisions differ (discordant moments)**.
- Confidence intervals by bootstrap that resamples whole days (10k resamples).
- **The same ledger also gives each arm's selection skill against "take every trigger"** and against the rules-only control. That is the core question for the whole LLM-trader idea.

**Sample size.**
- Assume the outcome of a trade varies with a standard deviation of about 1.1R [J].
- Rule of thumb for 80% power at α=0.05: n ≈ (2.8 × σ ÷ μ)², where μ is the true improvement per discordant moment.
- If μ = 0.25R: about **150 discordant moments**. If μ = 0.15R: about 420.
- At roughly 20% discordance on 30 moments a day, that is about 6 a day, so **the first decision lands at about 25 trading days (5–6 weeks), and the final one by 12 weeks.**

**Pre-registered rules:**
- **Early stop at 300 paired moments (about 10 days).** Compare how often N+V disagrees with N against how often N disagrees with its own repeat N′. If the excess disagreement is under 5 points, the chart is not changing decisions. Kill the arm and save the money.
- **Switch to N+V as the primary for trigger decisions** only if all of these hold:
  - ≥ 150 discordant moments and ≥ 25 trading days;
  - mean Δ ≥ +0.10R per discordant moment, with the lower bound of the one-sided 90% interval above 0;
  - the gain is not confined to trend days;
  - misread rate < 5%;
  - long/short gap not more than 10 points worse than N;
  - hallucinated-number rate no higher than N's;
  - p95 latency ≤ 7 s.
- **Drop vision for trigger decisions** if Δ ≤ 0 at 150 discordant moments, or if the upper confidence bound is below +0.05R at 300.
- **Unclear at 300:** stay numeric. Ties go to the simpler option.
- **Pre-market:** make the chart the default if, after 300 symbol-days, chart-planned scenarios beat non-chart ones by ≥ +0.1R in simulated take-all outcome (interval excluding 0). Second check: whether the day's actual high and low fell within 0.25 ATR of plan levels more often.
- **Month 2, only if N+V is promising:** add an Opus 5.5 low-effort vision arm on 25% of moments to test the vendor claim in E10.
- **Optional head start:** replay about 600 sampled moments from Jul–Sep 2026, after the models' training cutoff, through both arms. One-off cost about ₹1.8k. The replay has no depth data, so treat it as an early signal only.

**Output schema shared by both arms** (vision-only behaviour lives in the prompt):
```json
{"snapshot_id":"S-…","decision":"TAKE|PASS|ADJUST","direction":"LONG|SHORT",
 "entry_tactic":"BREAKOUT_STOP|PULLBACK_VWAP|RETEST_LEVEL","stop_ref":"L.ORL15",
 "target_refs":["L.R1"],"size_mult":0.5,"p_t1_before_stop":0.46,
 "structure":{"trend_quality":4,"extension_atr":"0.5-1","overlap":"clean","approach":"impulsive"},
 "perception_check":{"ltp_vs_vwap":"above","nearest_above":"L.ORH15","nearest_below":"L.VWAP","trend_15m":"up"},
 "chart_conflict":false,"thesis":"≤40 words, numbers only from SITREP","invalidation":"L.VWAP"}
```

**Prompt addition for N+V:** "The image renders the same snapshot. Use it only for structure: trend quality, extension, overlap, how price approached the level, level clusters, volume character. Never read prices from it. Cite only report fields and level IDs. Do not name chart patterns. If the chart and the report differ, trust the report and set `chart_conflict`."

---

## 6. Other uses of vision

- **Scanned filing PDFs: yes, as a fallback.**
  - Order of preference: XBRL results data first (NSE/BSE publish results in XBRL [M; confirm]), then the PDF's text layer (pymupdf).
  - Only when the text layer is missing or garbled (characters per page below a threshold): render pages 1–4 at ≤ 1,568 px and send them to Haiku 5.5. About 2–3k tokens per page, roughly ₹0.03.
  - Extracted numbers must reconcile (segments add up to the total, quarter-on-quarter maths checks) before use.
- **Option-chain heatmaps: no, for the LLM.** The chain is natively a table. A ±10-strike text table (OI, change in OI, IV) costs about 400 tokens and is exact. A heatmap adds misread risk and gives nothing the model needs. It is fine on the owner's dashboard.
- **Owner-facing: yes, high value, near zero cost.** Send the exact PNG the LLM saw with each decision to Telegram, along with the thesis. The owner can label "would I take this?". This builds trust and creates a dataset of his own discretionary calls for calibration.
- **Post-market review: yes.** The intraday chart plus fill markers, in batch on Sonnet, about ₹30 a month. It is advisory only.
- **Scalping and the expiry-day iron fly: no vision.** Index options and MCX use the underlying's chart only, never an option-premium chart.

---

## Top 5 recommendations

1. **The primary LLM trader is numeric-first.** Only level IDs can reach the order system, so no number taken from an image can turn into an order. Add the code-computed shape features (efficiency ratio, overlap, swing sequence, 24-digit sparkline) so the numeric arm is strong.
2. **Build one renderer driven by the snapshot:** matplotlib Agg in a warm process pool, two templates at 1400×1036 (1,850 tokens), registry-ID labels, scaling fixed in ATR terms, pre-rendered when a scenario is armed, PNG and hash journalled. Pass the perception gate (≥ 95%) before spending on the experiment.
3. **Run the paired N vs N+V experiment on 100% of trigger moments** with simulated-outcome scoring and the N′ noise-floor arm. Randomise the pre-market chart 50/50. Kill early if the chart barely changes decisions; decide at about 6 weeks with the pre-registered thresholds. Ties go to numbers.
4. **Measure the known weaknesses directly:** a `perception_check` in every call, the monthly mirror audit for long and trend bias, and results split by day type. The literature says these are exactly where vision models fail.
5. **Use vision elsewhere only where it is cheap and clearly useful:** owner alerts, post-market review, and the XBRL → text → Haiku-vision fallback for scanned filings. Skip option-chain heatmaps.

## Risks and unknowns

- **The evidence mostly covers older models.** The 5.5-generation chart gains (E10) are vendor-reported. Haiku 5.5's chart quality is unmeasured.
- **Regime risk.** 6–12 weeks around Diwali may be dominated by trend days, which flatter vision (E1). Results must be split by day type, and that cuts power.
- **No temperature control,** so decision noise could hide a small effect. The N′ arm only measures the noise; it does not remove it. Majority-of-3 voting later would triple cost.
- **The simulated outcomes are only as good as the paper broker's fill model.** Relative comparisons hold up; absolute R does not.
- **Unverified on OpenRouter:** image billing, `cache_control` pass-through with images, and image-payload latency. All go into Phase 0.
- **Laptop performance:** matplotlib render time and memory, and spawn cost on Windows, are not yet measured.
- **Multiple comparisons across many arena arms.** Pre-register the primary metric for each comparison.
- **Leakage:** historical replays must use only post-June-2026 data.
- **If daily trigger moments go above about 60,** the chart arm's cost doubles. Sample it at 50%.