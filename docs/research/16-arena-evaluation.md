# Arena design: how to compare the trading "brains" fairly

**Legend:**
- **[H/M/L]** means a fact checked against a source, at high, medium or low confidence.
- **[J]** means my own judgment.
- **[S]** means a Monte Carlo simulation I ran in this session. Per-trade R outcomes were drawn from a mix of stop-outs at about −1R and skewed wins, with σ ≈ 1.3–1.6R. The script is [`scripts/arena_monte_carlo.py`](scripts/arena_monte_carlo.py).

---

## 0. Bottom line

1. **Build the arena around shared decision moments, not separate books.** Each decision moment is scored by a **Counterfactual Outcome Engine (COE)**: the same conservative PaperExchange code, replayed on the recorded ticks and depth. The COE gives every action at a moment an outcome after costs, including actions nobody took. With it, 7 of the 9 books cost nothing extra in LLM spend, and most comparisons are paired on the same moment. That makes them several times faster than comparing whole books day by day. [J]
2. **Only two things cost LLM money live:** the champion LLM trader (L) and its chart twin (V). Challengers (Opus as decider, Haiku as decider, new prompt versions) re-decide the recorded moments overnight through OpenRouter's Batch API, which is about 50% off. Total: about **₹5.5k a month**.
3. **The statistics are sobering.** The design doc's "205 trades" assumes σ = 1.1R and independent trades. With a realistic σ ≈ 1.3R and trades clustered within a day (design effect 1.4), a sequential test (SPRT) needs:
   - a median of **about 220 trades if the true edge is +0.25R** (80th percentile 330) [S];
   - **about 410 trades if the edge is +0.15R** [S].

   At about 4 L trades a day, that is about 11 weeks if L is strong and about 20 weeks if its edge is modest. Questions about relative value resolve faster, in 6–12 weeks, because they are paired: what the vetoes save, what charts add, what position management adds.
4. **The biggest risk is promoting a "lucky book."** Take 8 books with zero real edge, correlated at ρ = 0.3, with 240 trades each. **There is a 36–38% chance that at least one of them passes a typical gate** (mean ≥ 0.10R, profit factor ≥ 1.25, 90% lower bound > 0). The best of the 8 shows a median annualised Sharpe of about 2.4 [S]. The defences:
   - pre-registered primary questions with a Holm correction;
   - placebo books;
   - a fresh confirmation window before any live money;
   - shrinkage in capital allocation.
5. **Charts:** the champion trader works from numbers. Charts get a fair, cheap trial through the V twin, with a pre-registered rule for keeping or dropping them (§6). [J]

---

## 1. How the arena works

### 1.1 Decision moments, policies and the Counterfactual Outcome Engine

A **decision moment** has these fields: `{moment_id, ts, symbol, side, source ∈ SCENARIO|RULE|SCANNER|NEWS, canonical_tactic, default_bracket, snapshot_hash}`.
- Code creates the moments:
  - the watchers on L's game-plan scenarios;
  - the shared rule tactic library running on the deterministic in-play top 15;
  - the scanners (RVOL, depth imbalance, filings).
- **Every rule trigger in the shared universe is sent to L.** This is what lets the H book be derived for free.
- There is a hard cap of 45 moments a day. Moments over the cap are scored by the COE but marked "unasked."

**The COE.** It runs the PaperExchange (conservative fill tier) on the recorded stream. Entry time is the moment time, plus the deciding call's measured LLM latency, plus execution latency.
- It produces net R after costs, MAE, MFE and holding time.
- It computes `y_default` for **every** moment, plus an outcome for every tactic on the menu.

**Default bracket**, used for passes and for derived books: the moment's own tactic and structural stop, half the position out at 1R, the rest trailed on the 5-minute swing, a 45-minute time stop, and flat by 14:55 (closing-auction stocks). [J]

**Conformance check:** the COE's re-simulation of L's actual paper trades must match the paper fills within a median of 0.02R.

### 1.2 The decision call separates "verdict" from "action"

```json
{"moment_id":"…",
 "setup_verdict":{"take":true,"grade":"A|B|C|X","p_win":0.58,"exp_R":0.4},
 "action":"TAKE|PASS|WAIT",
 "tactic":"RETEST_HOLD|PULLBACK_VWAP|BREAK_STOPLIMIT|MARKETABLE_NOW",
 "stop_ref":"L.ORL15-0.1ATR","target_ref":["1R:50%","TRAIL_5M"],
 "size_mult":0.5|0.75|1.0,
 "thesis":"≤40 words","invalidation":"≤20 words",
 "pass_reason":"NO_EDGE|EXTENDED|CHOP|NEWS_RISK|PORTFOLIO|LATE|LIQUIDITY"}
```

- **`setup_verdict` ignores the portfolio:** "would you take this on an empty book?" That keeps the derived books clean even when L passes only because it is already full.
- **`action` takes the portfolio into account.**
- **`WAIT`** can re-arm the watcher once, which creates a new moment. For scoring, a WAIT counts as a pass at the original moment.
- **Prompt outline:** a cached prefix holds the role, the playbook, the tactic menu with each tactic's failure modes, and the risk rules L cannot change. The variable part holds the moment card, the scenario it came from, the level-ID table, a tape summary, and the book's state (open risk, remaining loss limit for the day). The instruction is: "Decide only from the data given; cite level IDs, not prices."

### 1.3 The books

| Book | Definition | Moments | Extra LLM cost | What it measures |
|---|---|---|---|---|
| **R** Rules control | Every rule trigger on the in-play top 15, filtered by day type and friction, traded with the default bracket | RULE | 0 | Baseline: the raw value of the setups |
| **S** Scripted plan | L's pre-market scenarios traded mechanically when they trigger | SCENARIO | 0 | Value of the game plan |
| **H** Rules propose, LLM approves | R's trades where `setup_verdict.take` is true | RULE | 0 | **Value of vetoes** |
| **L** LLM trader (champion) | Everything: plan, moment calls, management | all | paid | The product |
| **LD** | L's entries with deterministic default exits | all | 0 | Management ablation (L minus LD) |
| **M** | L with the meta-labeler filtering trades and downsizing them (§3) | all | 0 | Learned filter on L's decisions |
| **V** Vision twin | Duplicate of L's decision call with 2 charts added; default exits | equity | ≈₹1.2k/month | **Value of charts** (V minus LD) |
| **E** Consensus | Take at 1.0x when L and V agree, 0.5x when only L takes, skip otherwise | all | 0 | Agreement as conviction |
| **P1/P2** Placebos | R's triggers with random passes at L's pass rate (P1), or with a random side (P2) | RULE | 0 | Null distribution; checks whether the gates are strict enough |
| **OWN** (optional) | The owner's own trades and quick take/pass taps on Telegram (§7) | — | 0 | "Would I have done better?" |

Each step of the **value ladder** below is a paired difference with a confidence interval:

**R → S** (plan) **→ LD** (judgement at the moment) **→ L** (management) **→ M** (meta-filter)

If a step adds nothing, its LLM spend is cut. For example, if management calls add no value, exits go back to code.

### 1.4 Capital and risk for each book

- **Each book trades a full virtual ₹10L.** Each has its own instance of the risk engine with identical config, its own OMS ledger, and **its own liquidity ledger**, so books never use up each other's displayed depth. Fill tier, costs and flatten times are the same for all.
- **R is fixed at 0.25% (₹2,500), the size of the first live stage (L1), with no compounding.** Results are reported in R, with rupee views at 0.25% and 0.5%.
- **Why not split the ₹10L between books:** a split changes friction relative to R, the minimum stop and the concurrency limits. The books would no longer be comparable or deployable as they stand.
- **Derived books still respect path-dependent risk rules.** They are replayed in time order with their own risk state: daily lock, open-risk cap, streak rules.
- **LLM latency counts against the LLM books.** It is a real cost.

### 1.5 Monthly budget

- **Assumed rates:** ₹95 per USD, plus OpenRouter's 5.5% credit-purchase fee [M] ([amnic](https://amnic.com/blogs/openrouter-pricing), [truefoundry](https://www.truefoundry.com/blog/openrouter-pricing)), plus an 18% buffer for GST and forex [L]. That makes about ₹118 per dollar.
- **Prices** are from research report 05 [H]:

| Model | Input $/MTok | Output $/MTok |
|---|---|---|
| Sonnet 5.5 | 2 | 10 |
| Opus 5.5 | 4 | 20 |
| Haiku 5.5 | 0.10 | 0.50 |

| Line item | Model | Calls a day | $ per call | $ a day |
|---|---|---|---|---|
| Game plan and scenario cards (with tools) | Opus 5.5 | 1 | ~0.45 | 0.45 |
| 12:30 re-plan | Sonnet 5.5 | 1 | 0.08 | 0.08 |
| Filing and news triage (after a rule pre-filter) | Haiku 5.5 | ~400 | 0.0004 | 0.16 |
| L decision moments (2.5k cached + 3.5k variable tokens in, 750 out) | Sonnet 5.5 | 30 | 0.015 | 0.45 |
| V twin (same call plus 2 charts) | Sonnet 5.5 | 25 | 0.020 | 0.50 |
| Position management (escalates to Sonnet on thesis risk) | Haiku 5.5 | 30 + 6 escalations | 0.001 / 0.008 | 0.08 |
| Repeat-call probes for flip rate (5% of calls) | Sonnet 5.5 | 2 | 0.015 | 0.03 |
| Post-market review | Sonnet 5.5, OpenRouter Batch | 1 | 0.10 | 0.10 |
| **Core subtotal** | | | | **1.85 ≈ ₹4.6k a month** |
| Overnight challengers on recorded moments (Batch, 50% off, text only [M] — [OpenRouter batch](https://openrouter.ai/docs/batch-quickstart)) | Haiku on every moment; Opus every other day | | | 0.38 ≈ ₹0.95k |
| **Total** | | | | **≈ ₹5.5k a month**, hard cap ₹7k |

**Order of cuts if the budget runs out:** challengers first, then V (once its question is answered), then the game plan moves from Opus to Sonnet.

**LLM cost as a hurdle:** ₹5.5k a month at R = ₹2,500 is about 2.2R a month, or **about 0.026R per L trade**. That is small next to the statistical hurdle.

---

## 2. Fair comparison

### 2.1 Three levels of pairing

1. **Per moment** (same moment, different action): H vs R, V vs LD, M vs L, challengers vs LD, OWN vs LD.
   - Only moments where the two books disagree carry information.
   - The difference at moment *i* is `s_i·y_i`, where `s_i` is +1 or −1 depending on which book took the trade.
2. **Per trade** (same entry, different exit): L vs LD. Because the entries are identical, the variance of the difference is low (σ_d ≈ 0.6R [J]).
3. **Per day** (different moments): L vs R, S vs R, any book vs OWN. This is the weakest level. With a daily difference σ of about 3R, detecting 0.5R a day would take about 220 days [J]. **Use it for display, not for decisions.**

### 2.2 Metrics

**Primary:**
- Net expectancy per trade, in R, after trading costs.
- Net R per day after the LLM cost allocated to the book.

**Secondary:**
- profit factor;
- maximum drawdown in R and in %;
- daily Sharpe and Sortino;
- hit rate and average win/loss;
- MAE/MFE;
- exposure-adjusted return: R earned per R-hour at risk (this does not penalise a book that trades less);
- slippage against arrival price;
- LLM ₹ per trade;
- calibration of `p_win`: Brier score and expected calibration error over 5 buckets, needing about 30–50 decisions per bucket;
- **pass value:** `PV = −Σ y_default(passed)`, shown as a percentile within the P1 placebo distribution (1,000 random pass sets drawn at L's pass rate).

### 2.3 Statistical tests

**Absolute edge, per book and module:**
- An SPRT on net R per trade: H0 μ = 0 against H1 μ = +0.15R.
- σ is estimated from the data after 30 trades, and the variance is inflated by a design effect measured from clustering within days. Accept at 2.77, reject at −1.56.
- **Futility rule:** after 150 trades, stop or fork if the 80% upper bound is below +0.10R.
- For display, use **anytime-valid 95% confidence sequences** [H] (Howard et al., *Annals of Statistics* 2021). They let the owner look at the leaderboard every day without inflating false positives.

**Relative edge:**
- A day-clustered paired bootstrap (10k resamples, BCa intervals) on the per-moment and per-trade differences.
- **Variance reduction with CUPED** [H] (Deng et al. 2013), using the beta-adjusted index and sector return over each trade's window as the covariate. [J: expect 10–25% less variance]

**Multiple comparisons:**
- **Five pre-registered primary questions with a Holm correction (family-wise error 5%):**
  1. L > 0
  2. L − R > 0
  3. H − R > 0
  4. V − LD > 0
  5. M − L > 0
- Everything else is exploratory.
- **Leaderboard:** a Model Confidence Set at 90% [H] (Hansen, Lunde and Nason 2011).
- **At graduation:**
  - Hansen's SPA test, best book vs R [H];
  - the Deflated Sharpe Ratio [H] (Bailey and López de Prado 2014), with N = every identity in the trial registry.
  - For scale: with 8 zero-edge identities over 60 days, the expected best annualised Sharpe from luck alone is about 2.9 [S/analytic: E[max of 8 standard normals] ≈ 1.42 × daily standard error 0.129 × √252].

### 2.4 Sample sizes and timeline (assuming ~4 L trades/day, 25–30 moments/day, σ ≈ 1.3R)

| Question | Unit | Effect | Needed | Time |
|---|---|---|---|---|
| L's absolute edge | trade | +0.25R | median ~220 (80th percentile 330) [S] | ~11 weeks (up to 16) |
| L's absolute edge | trade | +0.15R | median ~410 (80th percentile 690) [S] | ~20 weeks |
| Value of vetoes (passed trades average −0.2R) | passed R trigger | −0.2R | ~260 | 6–10 weeks |
| Value of management | trade pair | +0.15R / +0.10R | 99 / 223 | 5 / 11 weeks |
| Value of charts (V vs LD) | disagreement moment | +0.3R | 120–250 (82% power at 250) [S] | 6–13 weeks at 15% disagreement |
| Meta-labeler ranking | out-of-sample moment | AUC 0.58 | ~600 | ~5 weeks after warm-up |

**Calendar:**

| Date (2026–27) | Milestone |
|---|---|
| ~26 Oct 2026 | Arena starts, during results season (good in-play coverage) |
| Late Nov | Kill-check on V's disagreement rate; first Haiku-vs-Sonnet reading |
| December | Value of vetoes, value of management, meta-labeler in shadow |
| Mid-January 2027 | SPRT verdict on L-equity **if** its edge is about 0.25R. L0 probes can overlap once the live account exists |
| March 2027 | Verdict if the edge is about 0.15R |

---

## 3. A meta-labeler on the LLM's own decisions

- **Population: every moment L was asked about, taken or passed,** each labelled with `y_default`. That removes selection bias and gives about 25–30 labels a day, against about 4 if only taken trades counted.
- **Label:** `y = 1` if `y_default > +0.1R`. A second model regresses E[R].
- **Features: at most 12, each available at decision time:**
  - `p_win`, grade and tactic;
  - moment source and time bucket;
  - **the live day-type state** (never the label assigned after the close);
  - RVOL normalised for time of day;
  - gap %, distance from VWAP in ATR, OR15 width in ATR, stop distance in ATR, friction in R;
  - sector relative strength, Nifty's 15-minute trend, India VIX percentile;
  - top-5 depth imbalance and spread;
  - trades taken today and R realised today;
  - whether V agrees, and whether the rule agrees.
- **Excluded:** anything after the decision time, MAE/MFE, the rationale text, and z-scores fitted outside the training fold.
- **Models:**
  - First, L2-regularised logistic regression, once there are at least 300 labels with at least 100 in the minority class (about 2 weeks of data).
  - LightGBM once there are at least 1,000 labels: depth ≤ 3, ≤ 8 leaves, at least 40 samples per leaf, a monotone constraint on `p_win`, and isotonic calibration on the last 20% of the training window.
- **Walk-forward:** retrain weekly on an expanding window with a 1-day embargo. Purge swing labels by their holding window. Use grouped-by-day CV for tuning, inside the training window only. [H: López de Prado, *Advances in Financial ML*, 2018, chapters 3 and 7]
- **How the M book uses it:**
  - Drop a trade when E[R] < 0.
  - Size by tercile of calibrated `p_win`: 0.5x, 0.75x or 1.0x.
  - **The meta-labeler only ever narrows.** It never sizes up and never overrides a pass. A version that can "rescue" passes is a separate identity, allowed only after 2,000 or more moments.
- **Gate before M can matter:**
  - out-of-sample AUC ≥ 0.56, with the 90% interval above 0.5, on at least 600 moments;
  - the top-minus-bottom tercile spread is ≥ 0.25R;
  - on the trades L actually took, the dropped trades averaged less than the kept ones;
  - M − L ≥ 0.
- **Reset** whenever L's identity forks.
- **Never size from raw `p_win`.** Verbalised LLM confidence tends to be compressed and overconfident [M] (Xiong et al., ICLR 2024).
- **Side benefit:** the feature importances show where L is weak (for example, "midday takes lose"), which feeds the next prompt fork.

---

## 4. Live allocation and graduation

**Allocate risk (R level and share of the daily loss limit), not capital.**
- Live, only one book may trade a given symbol and side at a time; overlapping signals are merged.
- The global risk engine has the final say.

**Skeptical prior for each book and module:** μ ~ N(0, 0.10R). That is worth n₀ = σ²/τ² ≈ 170 trades. The posterior mean is x̄·n/(n+n₀). For example:
- 100 trades at +0.30R shrink to +0.11R;
- 400 trades at +0.20R shrink to +0.14R.

**Real money is allocated pessimistically, on the lower confidence bound:**
- **L1:** the posterior probability that μ > 0 is at least 0.95.
- **L2:** at least 0.975, and at least 80 live trades.
- **L3:** at least 0.99, and at least 160 live trades.
- Weights are proportional to max(0, 10th percentile of μ) / σ²_daily.
- Weights are capped at quarter-Kelly and by the module caps.
- Books whose daily P&L correlation exceeds 0.6 are treated as one bet.

**Paper and LLM budget use optimism instead:** Thompson sampling decides which challenger identities get overnight replay slots and which gets the live-paper slot next season. [J: optimism is cheap in paper; pessimism protects capital]

**Gates:**
- **Paper → L0, discovery phase:**
  - the book's primary question passes after the Holm correction;
  - regime coverage is met (§5);
  - Deflated Sharpe ≥ 0.95;
  - profit factor ≥ 1.2;
  - still positive after removing the best 5% of trades, and with +1 tick per side;
  - **maximum drawdown ≤ 20R**;
  - zero risk breaches in 20 days.
- **Confirmation window:** the next 25 days or 100 or more trades. It must show mean > 0 on one pre-specified test at α = 0.10, with nothing changed during the window.
- **L0 → L3:** the design doc's calibration and step criteria, plus the posterior thresholds above.

**The 6% drawdown gate in the design doc needs fixing.** A book with a true +0.15R edge (σ ≈ 1.3R) has a maximum drawdown over 250 trades of a median 12.6R, a 90th percentile of 20R and a 95th percentile of 23R [S].
- At 0.5% R, a 6% gate (12R) would **reject a genuinely good book about half the time.**
- State drawdown gates in R instead, and also require the drawdown to be within the 95th percentile of the book's own block-bootstrapped drawdown distribution.

**Demotion:**
- A live drawdown of 12R from the book's peak moves it down one level; 20R sends it back to paper.
- A rolling 50-trade expectancy below −0.1R, or a CUSUM alarm, sends it back to paper.
- A gap between live and its paper twin above 0.1R over 30 trades freezes scaling.
- The portfolio drawdown ladder at 5/10/15/20/25% stays on top of all this.

---

## 5. Guarding against self-deception

**Trader identity** = a hash of:
- model ID and the pinned provider;
- prompt template;
- context builder;
- tool set;
- tactic menu;
- chart renderer;
- meta-model;
- risk config.

Each identity also gets a readable name, for example `L-Son55-P3`.

**Classes of change:**
- **Class 0, no fork:** logging or UI changes. Replaying 5 days of snapshots must give identical prompt hashes.
- **Class 1, fork with a new track record:** any change to the prompt bytes, model, tools, context or tactic menu.
- **Class 2, global:** changes to risk, fill or cost models. They apply to every book, and every book is re-scored through the COE.

**Freeze windows:**
- Changes happen only at the boundaries of 4-week "seasons."
- At most one fork per lineage per season.
- Every fork comes with a written hypothesis and is entered in the trial registry, which supplies N for the Deflated Sharpe Ratio.
- **A fork is never scored on the moments that inspired it.** It starts as an overnight challenger on moments after its fork date, and is promoted only when it beats its parent on the moments where they disagree.

**Placebo books:** if P1 or P2 ever passes the discovery gate, the gates are too loose and must be tightened. This acts as an empirical monitor of false graduations.

**Regime coverage**, using the deterministic labeller after the close (trend day if |C−O| ≥ 0.6 × range and range ≥ 1.2 × ATR20). Before any graduation, require:
- at least 10 trend days and at least 10 range days;
- at least one results-season month;
- at least 6 Nifty Tuesday expiries (options module) [H, research 09];
- at least 3 high-VIX days.

Report expectancy per regime. A book that is negative in a regime over 40 or more trades needs a pre-registered regime filter, and that filter makes it a new identity.

**Training-data leakage:**
- Forward paper trading is clean, because all current Claude models have a June 2026 training cutoff [H, research 05].
- A replay may use only models whose cutoff is earlier than the moment being replayed.
- The tool server answers "as of" the moment, and there is no web search during replay.
- A historical LLM run is a plumbing test only, never a performance claim. The registry enforces this.

**Drift and noise:**
- Pin the OpenRouter provider and set `allow_fallbacks: false` on the decision routes. Log the provider that actually served each call.
- If the take/pass flip rate on repeated calls is above 20%, treat that identity as noisy.
- Days with a feed outage, and the Muhurat session, are excluded for every book alike.

---

## 6. Chart images: the decision

**The champion L works from numbers plus the level-ID table.** The reasons:
- it is precise;
- it caches well;
- it can be replayed through Batch, which is text-only [M].

**The V twin adds two charts at every equity moment.**

**Evidence:**
- The Agent Trading Arena study (EMNLP 2025 Findings) found that chart inputs improved LLMs' numerical reasoning and trading, **in a simulated market** [M] ([ACL](https://aclanthology.org/2025.findings-emnlp.294/)).
- FinAgent (GPT-4V) gained from adding charts [M] ([survey](https://arxiv.org/pdf/2408.06361)).
- Vision models read monotonic trends well but struggle with precise timing [L] ([summary](https://www.besthub.dev/articles/can-large-vision-language-models-really-understand-candlestick-charts-743b57154783)).

**Cost:** an image costs about width × height / 750 tokens [H] ([Claude vision docs](https://platform.claude.com/docs/en/build-with-claude/vision)). A 1000×700 chart is about 930 tokens, roughly $0.002 on Sonnet. The real cost is the second call.

**Chart spec:**
- **Chart A:** 5-minute candles for today and the prior session, with VWAP, the OR15 box, PDH/PDL lines **labelled with the same level IDs**, a volume panel and a marker at the moment.
- **Chart B:** 120 daily bars with the 20 and 50 EMAs and the 52-week high.
- Both are 1000×700 PNGs from a pinned renderer, with each image's hash stored.

**Keep-or-drop rule:**
- After 200 moments, if V disagrees with L less than 5% of the time, **drop V**. Charts are not changing decisions.
- Otherwise, at 150–250 moments of disagreement:
  - if V − LD averages at least +0.15R with a 90% interval above 0 (Holm-corrected), **fork L into a chart-reading identity**;
  - if it averages 0 or less, drop V.

---

## 7. What the owner sees, and when he can rely on a book

**Daily, at 15:45, on Telegram and an HTML page:**
- **Leaderboard columns:** book or identity, trades, net R today and in total, expectancy with its confidence sequence, profit factor, maximum drawdown in R, SPRT progress bar, LLM ₹, net after LLM cost.
- The value-ladder waterfall.
- **Veto ledger:** the 3 best saves and 3 worst misses, with L's rationale for each.
- LLM spend against budget.
- Decision log: snapshot, thesis, invalidation, outcome and counterfactual for every decision.

**Weekly:**
- equity curves in R with confidence bands;
- calibration plot;
- regime-coverage meter;
- meta-labeler out-of-sample results;
- **trust meter** (progress toward each gate).

**The owner as a book (optional):**
- **Manual log:** `/log symbol side entry stop exit` builds an OWN-manual book in R, compared day by day with L.
- **Telegram take/pass taps:** sample up to 10 of L's moments a day, each with a 60-second window to answer. This builds an OWN-taps book on the **same** moments, compared directly with LD. It answers "would I have done better?" with real statistical power.

**Trust milestones:**
- **T0, plumbing trusted:** 20 sessions, zero risk breaches, 100% replay parity, COE parity within 0.02R.
- **T1, paper-proven:**
  - discovery and confirmation windows passed;
  - regime coverage met;
  - Deflated Sharpe ≥ 0.95;
  - no placebo has passed the gates.
- **T2, confirmed live:**
  - L0 calibration done;
  - at least 80 trades at L1;
  - live vs paper twin gap ≤ 0.05R.
- **T3, "rely on it instead of your manual trading":**
  - at least 6 months of forward record with at least 400 trades;
  - at least 3 months live at L2 or above;
  - anytime-valid 95% lower bound above 0 **after LLM costs**;
  - drawdown within the 90th percentile simulated for the book's edge;
  - if the owner logs his own trades: at least matching OWN day by day, with a smaller drawdown.

---

## Top 5 recommendations

1. **Build the moment table and the COE first,** on the same PaperExchange code, with the conformance check. Seven of the nine books and every paired test depend on them.
2. **Send every rule trigger in the shared universe to L, and split `setup_verdict` from `action`.** That gives H, LD, M, E and the placebos at zero LLM cost.
3. **Run paid LLM calls only for L (Sonnet for decisions, Opus for the game plan) and V (chart twin).** Overnight Batch challengers decide whether Haiku is good enough (cheaper) or Opus is worth it. About ₹5.5k a month, capped at ₹7k.
4. **Pre-register five primary questions with Holm, anytime-valid intervals, placebo books, a confirmation window, and gates stated in R** (drawdown ≤ 20R, not 6%). Plan for an 11–20 week verdict.
5. **Treat every prompt or model change as a new trader identity in the registry, scored only forward.** Allocate real risk on the lower confidence bound; use Thompson sampling only for paper exploration.

## Risks and unknowns

- **Counterfactual realism:** L's passes may cluster in names where liquidity is thin. The conservative fill tier and L0 probes mitigate this, but they cannot eliminate it.
- **Choice of default bracket:** pass values depend on it. Report them under two alternative brackets as a sensitivity check.
- **σ and trade counts are guesses.** If L trades only about 2 times a day, every timeline doubles.
- **OpenRouter behaviour for Anthropic models is [M]:** Batch support, caching ([explicit breakpoints only on some routes](https://openrouter.ai/docs/prompt-caching)) and pricing. Verify all of this in phase 0.
- **Forced forks:** a model deprecation or a provider-side change forces a fork, which resets the track record.
- **Regime shift after graduation:** opportunity drops once results season ends.
- **Derived books share L's blind spots,** so agreement between them is not independent evidence.
- **Owner patience:** the first statistically honest verdict is about 3–5 months away.