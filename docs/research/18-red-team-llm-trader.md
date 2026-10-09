# Red-team review: the LLM-trader decision layer

**Reviewer stance:** sceptical prop-desk head and cost controller. **[H]/[M]/[L]** mark verified facts by confidence. **[J]** marks my judgment.

## 0. Verdict

1. **The core loop is sound:** a plan, code watching the scenarios, one decision call at each moment, deterministic risk, and paired scoring. All five proposals then add too much at once. With roughly 5 proposals × 5–9 books, an 8–12 week paper run cannot separate skill from luck.
2. **The question that decides everything is selection skill.** The "eyes" are the same rule triggers the owner already knows lose money. The LLM only adds value if its ex-ante score ranks those triggers well. **That can be measured in 8 weeks. Net profitability cannot be proven in 8 weeks.** [J]
3. **The budget is real but tighter than the proposals say.** At a landed rate of ₹118/$ (OpenRouter fee plus 18% GST, if it applies), ₹7k buys only about **$59 a month at list prices**. The cost-latency "Target" profile (₹6.65k at ₹100/$) comes to about ₹7.8k at that rate.
4. **Charts:** numeric-first is correct and unanimous. The only chart test worth paying for is chart-vision's design: Sonnet on 100% of moments, a noise-floor arm, and an early stop. A 33–50% sample cannot reach a verdict within 12 weeks.
5. **"Rely on it instead of my trading" is a claim that takes at least 6 months.** Weeks 8–12 can only give a trustworthy **kill or continue** decision.

---

## 1. Contradictions and rulings

| # | Issue | Positions | Ruling |
|---|---|---|---|
| 1 | Sonnet 5.5 cache-read price | trader-brain $0.20; cost-latency $0.10 | **$0.10/MTok (0.05×)** per Anthropic's pricing page [H]. The bundled skill table ($0.20) is stale. Opus 5.5 is $0.20 and Haiku 5.5 is $0.01 [H]. |
| 2 | Image tokens | chart-vision and cost-latency use ⌈w/28⌉×⌈h/28⌉; arena uses w·h/750 | **28-px patches** [H, Vision docs]. "Claude 4.7 and later" use the high-resolution tier (2,576 px, 4,784 tokens), so Haiku 5.5 is included [H]. 1000×700 = 900 tokens. The difference does not change any decision. |
| 3 | Batch discount via OpenRouter | cost-latency: none; arena, edge-trust and trader-brain: −50% | **The OpenRouter Batch API exists:** beta, about 50% off, 24-hour window, **text-only**, with Anthropic batch slugs listed [M]. Use it for EOD work and challengers. It cannot carry charts, and there is no SLA. |
| 4 | ₹ per $ | cost-latency ₹100; arena ₹118; edge-trust ₹5.7–6.7k | **Budget at ₹118–120 until the first invoice arrives.** Under OIDAR rules, foreign digital services sold to unregistered Indian users carry 18% IGST [M]. Whether OpenRouter collects it is unverified [L]. |
| 5 | Turning off Sonnet 5.5 thinking | trader-brain assumes medium effort and 1.2k output; arena assumes 750 output | **Thinking is on by default; `disabled` returns a 400.** The only off switch is `between_tools`, at effort high or below. The default effort is **high** [H]. Haiku 5.5 allows `disabled` at effort ≤ high (consistent with Phase 0). Opus 5.5 thinking cannot be turned off; its default effort is medium [H]. **Phase 0 must check that OpenRouter passes `effort: low` and `between_tools` through** [L]. |
| 6 | Decision latency | trader-brain 8–20 s; cost-latency p50 6–10 s / p95 15–20 s; chart-vision **p95 ≤ 6 s** | Chart-vision's 6 s is only realistic for Haiku or for Sonnet with `between_tools`. **Design for a 20 s p95.** No Priority Tier exists for the 5.5 models [H], so variance cannot be bought down. |
| 7 | Calls per day | trader-brain 50–65 (11 moment types); cost-latency 60; arena 30 (cap 45); edge-trust 25 (cap 40); chart-vision 30 | **Hard cap of 40 entry-side calls a day.** Trader-brain's M1–M11 taxonomy generates more moments than either the budget or the statistics can absorb. |
| 8 | Management calls | edge-trust 40+8/day; cost-latency 35; arena 36; trader-brain 15–25 | With 4–5 trades a day, 40 calls means 8–10 calls per trade. That is micromanagement. **Cap at 3 LLM calls per trade.** |
| 9 | Maximum entries per day | trader-brain 8; edge-trust and arena 4 | **4 equity entries a day.** Scarcity forces selectivity, and the sample-size maths below is built on it. |
| 10 | Book labels | "B2" means a chart arm (trader-brain), rules-propose (cost-latency) and Haiku veto (edge-trust) | **Adopt arena's letters as canonical:** R, S, H, L, LD, V, P1. |
| 11 | What counts as the control | trader-brain's B0 trades the *LLM-written* plan scenarios | That is arena's **S** (plan value), **not a rules-only control.** The Opus plan chose the universe and the levels. A true control **R** uses the deterministic in-play top 15 and the rule library. Keep both books. |
| 12 | Veto arm | trader-brain and edge-trust pay for a separate Haiku veto call | **Derive H for free** from L's `setup_verdict` (arena, cost-latency). A Haiku veto also comes for free from the Haiku shadow call. |
| 13 | Chart promotion threshold | trader-brain +0.05R per decision after 150 paired moments; cost-latency "wins ≥ 60% of disagreements"; chart-vision +0.10R per discordant moment at ≥ 150; arena +0.15R with Holm; edge-trust +0.1R over 380 | **Trader-brain's threshold is unreachable.** At about 20% discordance, +0.05R per moment means +0.25R per discordant moment; with σ ≈ 1.2R that needs about 150 discordant moments, which is **about 750–850 paired moments, not 150.** Cost-latency's win-rate metric is wrong for skewed payoffs (a 45% win rate at 2:1 beats 60% at 1:1). **Use chart-vision's rule,** with Holm correction. |
| 14 | Learning during evaluation | edge-trust: up to 3 lesson promotions a week; trader-brain puts a "LESSON" line in every sitrep | Every promotion creates a **new trader identity** and resets the track record (arena §5). **Freeze for season 1.** |
| 15 | Strategist tool loop | trader-brain allows ≤ 10 tool calls | Each tool round re-bills the whole growing context. Without cache pass-through, 10 rounds × ~35k tokens on Opus is about $1.4 a day, **≈ ₹3.5k a month**. **v1 has no tool loop:** code pre-assembles each name's dossier. |

---

## 2. Where this will lose money or fail

| Failure | Mechanism | Fix |
|---|---|---|
| **The base-rate trap** (most likely way it dies) | The eyes are rules with roughly zero or negative expectancy. With trigger outcomes μ₀ ≈ −0.05R and σ ≈ 1.2R, taking the top q = 15% by an LLM score with correlation ρ gives E[R] = μ₀ + ρσ·φ(z_q)/q = −0.05 + 1.86ρ. **To reach +0.15R the LLM needs ρ ≈ 0.11; to reach +0.20R it needs ρ ≈ 0.13.** That is roughly AUC 0.57–0.58, a high information coefficient for intraday outcomes. [J/analytic] | Make the IC the primary metric. Force `p_win` and `exp_R` on **every** moment, including PASSes. Trader-brain's PASS schema does not do this. |
| **Narrative and plan anchoring** | At 08:45 Opus writes a thesis with probabilities. The decision call then sees its own plan, base rate, kNN precedents and a lesson line: four anchors. Trader-brain also **hard-codes today's tape ("short default, longs need a catalyst") into strategist prose**, which is a hidden regime bet that will go stale. | Regime comes only from code features. Keep edge-trust's rationalisation guard. No precedents or lessons in the prompt until n ≥ 300. |
| **Paper optimism on resting limits** | Every proposal escapes latency through resting-limit tactics (T1, T7, T8, T9). In paper these fill when price touches the limit. In reality they fill by queue position and are adversely selected. This is the biggest paper-to-live gap, and nobody priced it. | Fill only when price **trades ≥ 1 tick through** the limit, plus a queue model. Report results by tactic family (marketable vs resting). Live L0 probes check the fill rate. |
| **Stale armed scenarios** | A pre-clearance made at 09:50 still fires at 10:40. | A TTL of 10–15 minutes on any arm (trader-brain's auto-disarm list is good), and scenario approval expires after 90 minutes unless refreshed. |
| **Non-determinism** | Temperature cannot be set on the 5.5 models [H]. A 15–20% take/pass flip rate turns paired comparisons into noise, and the derived books (H, LD) inherit the noise of one call. | An N′ repeat arm on 10% of moments. If flips exceed 20%, that moment class is treated as a PASS zone. |
| **Budget overrun** | Thinking length (+₹2–4.6k), GST (+18%), no cache pass-through (+₹2.2k), Opus tool loops. | Phase-0 gates (§4). Per-route caps. Degrade order: V, then moments capped at 30, then Haiku as primary. |
| **Too many books** | With 8 zero-edge books there is a 36–38% chance that one passes a typical gate (arena's simulation). | **One primary hypothesis plus two secondary, Holm-corrected.** Everything else is exploratory. |
| **Lookahead** | Day-type labels computed at the close used as features; base rates and the in-play scorer fitted on the full 2024–26 history; kNN not ordered in time; prompts tuned on the same days they are scored on. | Live-state features only. Base rates computed walk-forward. Seal 30% of replay days. The first trustworthy scores come only from days after the arena starts. |
| **Management micromanaging** | Trader-brain tests "management alpha" at 40 trades: with σ_d ≈ 0.6R the standard error is about 0.095R, so the test cannot see anything. | Only 3 events trigger an LLM management call. Use LD as the free ablation. Decide at ≥ 100 trades. |
| **Correlated books** | All books share the same moments, universe and regime. "L beats R" is meaningless when R loses. | **Success requires L > 0 in absolute terms after costs,** not just L > R. |

---

## 3. Gaps none of the proposals covered

1. **Cross-sectional bursts.** Between 09:25 and 09:45 many triggers fire together. Isolated yes/no calls cannot compare candidates, and LLMs judge *relatively* better than they calibrate *absolutely* [J]. When 2 or more moments are open within 60 s, send one **"rank and take ≤ k of N"** call. It is also cheaper.
2. **Live-phase rules are already in force.** SEBI's retail algo framework became mandatory on 1 Apr 2026 [M]. It means:
   - **static-IP whitelisting for order APIs** (a home Windows laptop on a dynamic IP needs a static IP or a VPS);
   - a **daily 2FA session**;
   - market orders converted to **MPP** (this changes T5 chase and stop behaviour);
   - a 10 orders-per-second threshold.

   If paper does not model these, the paper book is not the live book.
3. **No owner baseline.** "Instead of my manual trading" needs the owner's last 12 months of net P&L in R terms (broker tradebook) as the bar. Only edge-trust's Owner Twin touches this.
4. **The universe selector is never tested.** Every book shares the in-play scorer, which may be the dominant source of edge or of leak. Add a free placebo: R's tactics run on random liquid names that are *not* in play.
5. **An ex-ante score on PASSes.** Without it, neither the IC nor a meta-labeler can be computed. Make it a schema requirement.
6. **Calendar of the evaluation window.** Results season ends in mid-November; there is Muhurat trading on 8 Nov and thin December holiday markets. A 12-week verdict will cover about 1.5 regimes. Scope it accordingly.
7. **Operational exits.** Handle `stop_reason: refusal` (Sonnet 5.5 safety categories [H]) as PASS. Pin the model IDs. Set `allow_fallbacks: false` on decision routes. Exclude days with laptop or feed gaps from *all* books.

---

## 4. Minimal highest-EV v1: build this first

**Scope:** intraday equity only. Index options, MCX and swing run as rules-only data collection. With 1–3 index-options decisions a day, an LLM verdict there within 12 weeks is impossible.

**Books.** Two are paid; the rest are free through arena's Counterfactual Outcome Engine (COE).

| Book | Definition | Cost |
|---|---|---|
| **L** | Sonnet 5.5, effort low, numeric only, P&L-blind (it sees capacity, not rupees). Default entry mode is approach pre-clearance; confirm mode only for setups that resolve on a bar close. | paid |
| **R** | Rules control on the deterministic in-play top 15. Every R trigger also goes to L. | free |
| **S** | The plan's scenarios traded mechanically | free |
| **H** | R ∩ L's verdict (veto value) | free |
| **LD** | L's entries with default exits (management ablation) | free |
| **P1** | Placebo: random passes at L's pass rate | free |
| **Hk** | Haiku 5.5 shadow decider on 100% of moments: "is Sonnet worth 20×?" | about ₹60 |
| **V** | Sonnet plus one 1400×1036 chart on 100% of moments, run only after the ≥ 95% perception gate. **Early stop at about 300 paired moments** if disagreement exceeds the N′ noise floor by less than 5 points. | about ₹1.9k |
| **OWN-taps** | Blind owner take/pass taps, ≤ 10 a day, with the code-rendered chart | free |

**Chart decision:**
- No chart in the plan for v1. The randomized plan test needs about 300 symbol-days per arm, which is too slow.
- Charts are tested only through V on decisions.
- Charts always go to the owner on Telegram.

**Memory decision:**
- Log every case, including PASSes with their shadow outcomes.
- **No retrieval and no lessons in the prompt during season 1.**
- Generate lesson candidates weekly and test them only as overnight Batch challengers on later moments.

**Monthly budget at ₹118/$ (list price × 1.18)**

| Line | Model, calls/day | ₹/month |
|---|---|---|
| Plan, plus 25 resolvable propositions ("scenario markets") | Opus 5.5 medium, 1 call, no tool loop | 890 |
| Pre-open and 12:15 refresh | Sonnet low, 2 | 210 |
| Filing triage | Haiku, thinking off, about 400 | 220 |
| Materiality | Haiku 10 → Sonnet 3 | 270 |
| **L decisions** | Sonnet: 6k cached + 3k fresh in, about 900 out; ≤ 40 calls | **1,550** |
| Cache writes (1-hour TTL, about 7 a day) | — | 400 |
| Hk shadow / N′ repeat probes (10%) | Haiku 40 / Sonnet 4 | 60 / 155 |
| Management | Haiku 12 + Sonnet 2 (news only) | 75 |
| EOD summary and post-mortems | via OpenRouter Batch | 150 |
| `/why` and other small calls | Haiku | 30 |
| **Subtotal without V** | | **≈ 4,000** |
| **V twin, if it survives the 2-week gate** | Sonnet + chart, ≤ 40 calls | **+1,900 → ≈ 5,900; ≈ 6,500 with 10% contingency** |

One-off Phase-0 and replay-dojo spend of about ₹1.5k comes from month 1's contingency. **Sensitivity:** if Sonnet's real output is about 2k tokens instead of 900, add about ₹2.2k. V is then cut first.

**Phase-0 gates, through OpenRouter, before day 1:**
- Cached tokens greater than 0 on the decision route.
- Sonnet `effort: low` gives p90 output ≤ 1.2k tokens; `between_tools` is accepted.
- Strict JSON works, with < 1% failures.
- Billed image tokens ≈ ⌈w/28⌉×⌈h/28⌉.
- p50/p95 latency measured over 200 calls from the laptop.
- Flip-rate baseline: 50 moments × 3 repeats.
- The first invoice shows whether GST is charged.
- COE reproduces paper fills within 0.02R.

**Timeline:**
- **Arena starts about 26 Oct.**
- **Week 2:** V early-stop decision.
- **Week 4:** plan check, based on S − R and the propositions' Brier score against climatology.
- **Week 8 (about 18 Dec):** main verdict on selection IC and on veto value.
- **Week 12:** go/no-go for L0 live probes.

**Add only after evidence:**

| Evidence | Then |
|---|---|
| Hk ≈ L | Haiku becomes primary; the freed budget buys more moments or an Opus second opinion. |
| V passes | Fork L into an N+V identity at the season boundary. |
| IC ≥ 0.10 and L ≥ 0 | Add the meta-labeler (after 600 moments), the index-options LLM book, lesson forks, and the Owner Twin. |
| Equity proven | Only then consider MCX or swing LLM books. |

---

## 5. Pre-registered kill and success criteria

**Kill**, at week 8 (≥ 35 sessions, ≥ 1,000 scored moments, ≥ 120 L trades). For scale: 1,200 moments with a design effect of about 2.5 gives an effective n of about 480, so the standard error of the IC is about 0.046.

| ID | Test | Kill if |
|---|---|---|
| K1 Selection | Day-clustered Spearman IC between L's `exp_R` and `y_default` (outcome under the default bracket), across all moments L was asked about | Point estimate < 0.03, **or** 90% upper bound < 0.08: the LLM-as-selector idea is dead, and so are H and L |
| K2 Veto | Mean `y_default` of the R triggers L passed, compared with those it took, on ≥ 150 vetoes | Passed triggers do no worse than taken ones: the veto is worthless |
| K3 Absolute | L net per trade after trading costs **and** LLM ₹ | Below −0.10R at ≥ 150 trades, or drawdown > 15R |
| K4 Plan | S − R, and the propositions' Brier skill score, at week 4 | Both ≤ 0: drop the Opus plan for a deterministic watchlist (saves about ₹0.9k) |
| K5 Management | L − LD at ≥ 100 trades | 80% CI excludes +0.05R and the mean is < 0: exits go back to code |
| K6 Tier | Hk's IC compared with L's IC | Hk ≥ L − 0.02 with ≥ 85% agreement: Sonnet is not worth the cost |
| K7 Operations | Flip rate, schema failures, latency, cost | Flips > 20%, schema failures > 3%, p95 > 25 s, or > ₹7k a month for 2 months after the degrade ladder |
| K-final | SPRT on L net R (H1: +0.15R) at 16–20 weeks | Reject: stop the LLM-trader approach for equity intraday |

**Success**

| Milestone | Criteria |
|---|---|
| **S1, "promising": tiny live L0 probes** (weeks 8–12) | IC ≥ 0.10 with 90% lower bound > 0; L net ≥ +0.05R per trade after LLM cost over ≥ 150 trades; H − R > 0; no placebo passes any gate; flip rate < 15% |
| **S2, "rely on it"** | ≥ 6 months forward and ≥ 400 trades; ≥ 3 months live; anytime-valid 95% lower bound > 0 after LLM cost; live-vs-paper gap ≤ 0.05R per trade; drawdown ≤ 20R; positive on both trend-day and range-day subsets; **net R per month ≥ the owner's own manual record over the same period, with a smaller drawdown** |

---

## Top 5 recommendations

1. **Make selection IC on every moment the primary, pre-registered metric.** Force `p_win` and `exp_R` on PASSes. It is the only question an 8–12 week window can honestly answer.
2. **Two paid books (L, plus V on probation) and everything else derived for free.** Freeze identity and memory for season 1, and use arena's book letters and Holm discipline.
3. **Pass the Phase-0 cost and latency gates through OpenRouter first:** effort, caching, `between_tools`, image billing, GST. Budget at ₹118/$ with a 40-call cap.
4. **Fix paper realism before trusting any result:** fills need a trade-through, report by tactic family, and use a pure-rules R control, not LLM-written scenarios.
5. **Tell the owner the truth about timing:** week 8 gives kill or continue, week 12 gives tiny live probes, and "rely on it" takes at least 6 months. Plan for SEBI static-IP, MPP and daily-2FA constraints now.

## Risks and unknowns

- **OpenRouter pass-through is unverified [L]:** effort, `between_tools`, 1-hour cache TTL, Batch for Anthropic models, and GST collection.
- **The IC threshold assumes rough normality.** Real R outcomes are skewed and bimodal, so the required ρ could be higher.
- **The COE default bracket drives `y_default`.** Run a sensitivity check with a second bracket.
- **Regime:** the window covers results season and a market near 6-month lows; the verdict may not generalise.
- **Vendor-side model updates** under a pinned slug, or a deprecation, would force an identity fork.
- **SEBI framework facts come from broker notices dated up to March 2026 [M].** Recheck them against current Upstox rules before going live.

**Sources:**
- [Anthropic pricing](https://platform.claude.com/docs/en/about-claude/pricing) and [Vision docs](https://platform.claude.com/docs/en/build-with-claude/vision) [H]; claude-api skill model notes [H].
- OpenRouter Batch: [AIREITER](https://aireiter.com/blog/openrouter-batch-api-pricing-guide), [SessionWatcher](https://sessionwatcher.com/news/openrouter-batch-api-half-price-inference), [moclaw](https://moclaw.ai/blog/no-endpoints-found-for-openai-batch) [M].
- OIDAR GST: [India Briefing](https://www.india-briefing.com/news/tax-digital-services-oidar-in-india-gst-applicability-and-compliance-22465.html), [TaxGuru](https://taxguru.in/goods-and-service-tax/oidar-services-taxability.html) [M].
- SEBI retail algo framework: [Outlook Business](https://www.outlookbusiness.com/markets/sebi-extends-deadline-to-implement-retail-algo-trading-by-april-2026), [FYERS notice](https://fyers.in/notice-board/new-sebi-framework-for-retail-algo-trading-from-april-01-2026/), [Kite forum](https://kite.trade/forum/discussion/comment/52171), [5paisa](https://tradebetter.5paisa.com/t/important-update-sebi-algo-compliance-effective-1st-april/761) [M].

No files were modified. All cost figures are my own arithmetic from the verified per-token prices.