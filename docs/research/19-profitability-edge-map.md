# Edge map: where the net edge is (quant researcher review, 2026-10-12)

*Read for this review: `/home/user/auto-trading/docs/design/trading-system-design.md`, `/home/user/auto-trading/docs/design/ai-trader.md`, and research reports 02, 03, 04, 09–12, 17 and 18 in `/home/user/auto-trading/docs/research/`. No code was read. Evidence is checked on the web; confidence is tagged H/M/L, and [J] marks my own judgment.*

## 1. Verdict on the current design

- **Keep the chassis.** Conservative fills, the friction gate, pre-registered kill criteria, paired counterfactual books and the drawdown ladder are better discipline than most retail systems ever reach.
- **Effort is going to the wrong places [J].** About 75% of effort and LLM spend goes to the cell with the weakest evidence and the highest friction: intraday cash at minute scale. There the LLM ranks rule triggers whose base rate is about −0.05R (`ai-trader.md` §1). Two cells where evidence, cost and LLM strengths line up are deferred, or gated until they don't matter:
  - **multi-day catalyst drift in stocks:** the LLM reads text at end of day, there is no latency problem, and friction is about 0.1R;
  - **the index-option volatility risk premium (VRP):** there is India-specific academic evidence, and the premium is earned overnight.
- **Swing can't graduate as designed.** The gate needs ≥ +1.5R at 14:30, the top 20% of the day's range and RVOL ≥ 2. That makes swing a by-product of intraday winners, perhaps 1–3 trades a month [J], which never reaches a 200-trade gate.
- **The intraday success bar is elite-prop level.** +0.15R per trade at about 600 trades a year, with σ ≈ 1.3R, implies an annual Sharpe ratio of about 2.5–3 [J]. Plan on **+0.05–0.08R** instead. At R = 0.25% that is ₹80–120k a year gross, against ₹50–80k a year of LLM cost. So the LLM eats most of the edge until R reaches 0.5% or a cheaper model passes K6 (the Haiku-vs-Sonnet test) [J].
- **The risk budget is split the wrong way.** 2% intraday plus 1% overnight puts two thirds of the worst day on the horizon with the weakest evidence.
  - At L1 (R = 0.25%, at most 4 entries a day) the intraday daily loss limit is almost never reached: 4 × 0.25% × 1.1 ≈ 1.1%.
  - The overnight rule (per-name shock ≤ 0.25% of equity, with a 5% shock floor) caps each large-cap swing name at about ₹50k notional.

## 2. The edge map

Friction is the round-trip cost plus slippage as a share of R, at the sleeve's typical stop.

| Cell | Best-documented edge | India evidence | Net at ₹10L | Infra fit | What the LLM adds | Call |
|---|---|---|---|---|---|---|
| **Stocks × scalp** | Order-flow persistence, which colocated tick-by-tick players own | **L.** 71% of intraday cash traders lost money in FY23; loss-makers' costs equalled 57% of their losses [H]. Under 3% of Taiwanese day traders are predictably profitable [H] | 0.2–0.5R friction | Poor: snapshot feed, 50 depth keys | None | Record only |
| **Stocks × intraday** | News continuation (second leg), opening-range breakout (ORB) on stocks in play, intraday market momentum | **L–M.** No India study found. An ORB replication on indices matched the gross result but netted about zero [M]. LLM scores of headlines predict next-day returns, most strongly in small caps and on bad news, and the effect fades as more traders use LLMs [H, US] | 0.15–0.2R | Built | **Medium:** judging catalyst size, yes; reading patterns, no | Keep; catalyst names only |
| **Stocks × swing (2–10 days)** | Drift after earnings (PEAD) and news; short-horizon momentum; 1-week reversal in large caps without news; the overnight premium | **M.** Momentum stays profitable after costs at short horizons [M]. PEAD is mixed: none found in 100 large caps (2014–18), but drift appears after bad news and in broader samples [M]. Reversal earns 30–50 bps a week after costs in large caps [H for US/EU; L for India]. Nifty's gains come mostly overnight [L–M, practitioner] | Delivery costs ≈ 30–35 bps → **0.06–0.12R** at 3–5% stops | Excellent: daily bars and filings, no depth needed | **High:** reading results and order filings, ranking candidates against each other at end of day, Batch API at about −50% | **Best cell; under-built** |
| **Options × scalp** | Cost advantage only | **L.** 87.7% of individual F&O traders lost money in FY26, and 92% of their losses came from options [H] | 0.04–0.08R, but theta | OK | None | Cut |
| **Options × intraday** | O1: intraday momentum (H for US, L for India). O2: expiry-day (0DTE) afternoon theta | **L.** Short Nifty options earn their premium **overnight** and on average **lose intraday** [H]. 0DTE in India after 2024 is untested [J]. A large player moved expiry-day index levels (SEBI impounded ₹4,843 cr from Jane Street) [H] | 0.05–0.1R | Needs a multi-leg order system | Low: event veto | Rules-only paper |
| **Options × swing (1–5 nights)** | Index VRP through hedged short premium held overnight; long straddles from 3 days before earnings to the announcement (+3.34% in the US [H]; L for India, given 0.3–3% spreads) | **M–H.** The overnight premium is significant; selling at the close and covering at the open fails after costs [H/M]. Proprietary traders and FPIs made ₹61k cr gross in FY24, 96–97% of it by algorithms [H] | Costs ≈ 3–6% of credit when held to expiry [J] | Good: expired F&O data | Low–medium: event and geopolitical vetoes | **Best options cell; currently out of scope** |
| **Commodities × scalp** | None at retail | L | Costs 0.4–0.8 × 1-min σ | — | None | Drop |
| **Commodities × intraday** | Evening crude breakout; EIA report trades | **L.** Report 12 (red team) expects losses: 0.39R friction at 1 lot | 0.15–0.4R | OK | Low | Paper-log only |
| **Commodities × positional** | Time-series momentum over 1–12 months: 12-month returns were positive for all 58 futures tested, with a century of supporting evidence [H]. Indian commodity momentum survives costs but varies over time [M]. Weak at 2–10 days [J] | M | **0.02–0.05R** | Trivial: daily data | Low: parsing circulars, the duty-cut flag | Keep C1 (daily trend), rules-only |

**The selection math decides the ranking.** By the design's own formula, the expected result of a taken trade ≈ μ₀ + 1.87ρ. Here μ₀ is the pool's base rate and ρ is how well the LLM's scores rank outcomes (its information coefficient, IC).
- **Intraday triggers:** μ₀ ≈ −0.05R, so +0.15R needs ρ ≈ 0.11.
- **Swing events:** friction is about 0.1R lower, so μ₀ ≈ +0.05R at the same gross edge, and +0.15R needs only ρ ≈ 0.05 [J].

The same LLM skill pays roughly twice as much where the pool's base rate is not negative.

## 3. Ranking by risk-adjusted net return per unit of effort [J]

1. **Stocks × swing (catalyst drift).** The pool's base rate is not negative, friction is low, and it uses the LLM's real skill. The filings scrapers and triage already exist.
2. **Commodities × positional trend.** Small in rupees (about ₹10–25k a year on 1 CRUDEOILM lot plus up to 6 GOLDPETAL lots). But the extra effort is near zero, it is uncorrelated with equities, and its payoff is positively skewed.
3. **Options × swing (index VRP).** The strongest India-specific evidence of any options cell, but negatively skewed.
4. **Stocks × intraday, catalyst names only.** Viable but friction-heavy. This is the current core.
5. **Options × intraday (O1/O2).**
6. **Stocks × intraday, pattern-only triggers.** This is the base-rate trap: ranking a pool whose average outcome is negative.
7. **Commodities × intraday.**
8. **Options × scalp.**
9. **Stocks × scalp.** (Commodities × scalp is dropped outright.)

## 4. Is the current emphasis right? The portfolio of sleeves

**Partly.** These parts are right:
- one LLM sleeve plus an arena first;
- scalping deferred;
- no LLM decisions in options or MCX.

These are not:
- swing as an exception path;
- LLM money spent on pattern moments and a chart twin;
- the VRP left out of scope.

| Sleeve | Instrument and horizon | Decided by | Share of the 3% worst day | Effort, now → proposed |
|---|---|---|---|---|
| A. Intraday catalyst | Cash intraday (MIS) | LLM at decision moments | 1.5% daily loss limit (from 2%) | ~70% → 35% |
| B. Catalyst swing | Delivery (CNC) longs; put debit spreads on the top ~25 F&O names for shorts; 2–10 days | Rules prefilter, then LLM ranking at end of day (Batch API) | 0.75% | ~3% → 30% |
| C. Index VRP | Nifty/Sensex weekly short premium with defined risk, 1–4 nights | Rules, with an LLM veto | 0.4% | 0 → 8% (or the owner's existing options-selling agent, on one shared risk ledger) |
| D. Commodity trend | C1 (daily trend) | Rules | 0.35% | ~8% → 7% |
| E. Index options intraday | O1/O2 | Rules, in paper | Inside A's daily loss limit | ~5% → 5% |
| F. Research | Base rates, replays, recorder | Code | — | ~10% → 15% |

**Stress-test B and C together.** Both lose in a crash gap, while D (gold, trend) often gains. Use one joint scenario: Nifty −4%, VIX +40%, and an MCX price-band lock.

## 5. Improvements ranked by expected impact

**1. Build sleeve B, catalyst swing.**
- **What:**
  - Jev triages every filing (about $0.00002 each).
  - The events are: results (XBRL data plus surprise proxies), orders of at least 5% of trailing-12-month revenue, guidance changes, and pledge and insider flags.
  - Each evening a Sonnet or Opus call through the Batch API ranks 30–60 candidates. Opus refuses requests without reasoning, and in the evening there is time to let it reason.
  - Entries come the next session on limit orders. The stop is 1.5–2 daily ATR. Exit on a close below the 10-day EMA or after 10 days. Never hold through the stock's own results.
- **Why:** friction is low, there is no latency problem, and there is drift evidence (M for India; Lopez-Lira and Tang [H] and Siano 2025 [M] for the US).
- **Expected effect:** +0.1–0.2R per trade net, on 150–250 trades a year. That is ₹50–120k a year under today's overnight budget, and about 1.5× that after item 5 [J].
- **Cost:** 2–3 weeks to build. LLM cost is about ₹2.5–3k a month, paid for by dropping the chart twin V.
- **Risk:** gap losses correlated with sleeve C; trade flow bunches into results seasons; momentum crashes.
- **How to measure it in the arena:** an outcome engine on daily bars, with four books:
  - SW-L: the LLM's top picks;
  - SW-R: a rules-only surprise score;
  - SW-H: SW-R's trades minus those the LLM vetoes;
  - SW-P: a placebo of similar names with no event.

  The main metric is the IC between `exp_R` and the 5-day return relative to the stock's sector, over **all** scored events, with trades grouped by day. Kill the sleeve if the IC is below 0.02 at 1,500 events, or if the top fifth beats the rest by 0.3% or less after 35 bps of costs.

**2. Replay the months after the model cutoff, now.**
- **What:** replay every NSE and BSE filing from 1 Jul to 10 Oct 2026 through the triage and decision prompts. That window covers the whole Q1 FY27 results season, after the models' June 2026 training cutoff. Time each filing at its dissemination time plus 60–100 s. Score intraday trades on 1-minute candles and swing trades on daily bars.
- **Why:** about 500 Nifty 500 results and thousands of filings that the models cannot have seen. At 1,000 events the IC can be measured to within about ±0.03 (one standard error).
- **Expected effect:** a kill-or-continue verdict for both catalyst sleeves in 2–3 weeks instead of 8–14.
- **Cost:** about 1 week, plus ₹3–5k of LLM spend once.
- **Risk:** tuning the prompts on the replay days. Seal 30% of the days, and label the replay "season 0", never proof of edge.
- **How to measure it in the arena:** its results decide which sleeves get forward paper capacity.

**3. Build a base-rate map in code (no LLM, 2022–26 data).**
- **What:**
  - how returns split between overnight and intraday, for Nifty and the Nifty 500;
  - drift from day 0 to day 10, by catalyst type and size of surprise;
  - whether gaps fade or continue, with and without a catalyst;
  - 1-week reversal of stocks that moved without news;
  - whether Nifty's first 30 minutes predict its last 30 minutes.
- **Why:** the base-rate trap is the design's own most likely failure mode. Only send the LLM pools whose base rate is at least zero.
- **Expected effect:** +0.05–0.1R per trade at the same IC [J].
- **Cost:** 3–5 days.
- **How to measure it in the arena:** the base rates (walk-forward) go into the sitrep, the situation report the LLM sees at each decision, and the P2 universe placebo checks them.

**4. Narrow the intraday LLM book to catalyst moments.**
- **What:** call the LLM only when catalyst materiality is at least 60, on results days, or for second legs. E1/E2 pattern triggers feed the rules-only book R, which costs nothing. Add short scenarios for bad news.
- **Why:** reading text is where the LLM adds value, and predictability is stronger on negative news [H, US].
- **Expected effect:** a better base rate per call, and 30–40% of decision spend freed.
- **How to measure it in the arena:** pre-register the IC per mode, and the value of vetoes per mode (book H minus book R), as secondary questions.

**5. Re-split the worst day to 1.5% intraday plus 1.5% overnight, with scenario-based stress (owner decision).**
- **What:** replace the sum of per-name shock floors with one joint scenario: Nifty −4% times each position's beta, plus the worst single name at −10% to −15%, plus VIX +40% on the option sleeves, plus an MCX band lock. Raise the per-name cap to 0.4% of equity.
- **Why:** the intraday daily loss limit sits mostly unused at L1, and the sleeves with the best evidence hold overnight.
- **Expected effect:** about 1.5–2× more notional for sleeves B, C and D, at the same 3% worst day.
- **Risk:** geopolitics. Keep the rule that cuts overnight positions by 50% before weekends when geopolitical risk is high.
- **How to measure it in the arena:** realized overnight stress against the budget, with zero breaches.

**6. Build VRP sleeve C.**
- **What:** a weekly iron fly or condor on Nifty or Sensex, entered 1–3 sessions before expiry. Maximum loss is ₹5k per set, with at most 2 sets. The LLM may veto it before events or risky geopolitical weekends. Exit at 50–60% of the credit, or at 14:30 on expiry day.
- **Why:** in India the option-selling premium is paid overnight (Bhat, Pandey and Rao 2024; Muravyev and Ni 2020 for the US).
- **Expected effect:** ₹25–60k a year, at a Sharpe ratio of about 0.5–1 after costs [J].
- **Cost:** 1–2 weeks, reusing O2's multi-leg order handling. Backtest it on expired F&O data from Oct 2024.
- **Risk:** jump days; the extra expiry-day margin (ELM); lot-size changes; and two option-selling systems on one PAN, which then need one shared ledger.
- **How to measure it in the arena:** a rules-only VRP book compared against O2, with results split by VIX regime and by jump days.

**7. Switch brokers for cost.** Use Zerodha for delivery trades (₹0 brokerage) and pay ₹20 per order intraday instead of Upstox Plus's ₹30. That saves about ₹59k a year at 10 round trips a day, about a third of a realistic intraday edge.

## 6. Cut or de-prioritise

- **Chart twin V** (₹1.9k a month, about 30% of LLM spend). Move the money to sleeve B.
- **Scalping ML** (the LightGBM filter and the dense flow model). Keep the recorder running in the background.
- **0DTE momentum bursts and index-option scalps.**
- **MCX C2 (evening breakout) and the EIA trade variants.** Keep C3 (the EIA flatten-and-blackout rule) as risk control.
- **New intraday pattern setups from the backlog.** Each adds more base-rate-trap triggers and more multiple testing.
- **The LLM book for index options.** Keep it deferred.

## 7. Top 5 recommendations

1. **Build catalyst swing (sleeve B)** with a daily-bar arena and IC measured across all events.
2. **Run the Jul–Oct 2026 replay within 2 weeks.**
3. **Build the base-rate map**, and only send the LLM pools whose base rate is at least zero.
4. **Ask the owner to move to 1.5% intraday plus 1.5% overnight**, with scenario-based stress.
5. **Narrow intraday LLM calls to catalysts**, drop the chart twin, plan intraday at +0.05–0.08R, and make K6 (a cheaper Haiku or Jev decider) the economic gate.

### Sources
- SEBI intraday study, FY23: [Business Standard](https://www.business-standard.com/amp/markets/news/7-in-10-intraday-traders-in-equity-cash-suffered-losses-in-fy23-sebi-study-124072400975_1.html)
- SEBI F&O study, FY26: [Business Today](https://www.businesstoday.in/markets/story/rs91685-cr-lost-88-of-individual-traders-lost-money-in-fy26-options-drove-92-of-losses-550474-2026-08-21)
- Proprietary and FPI profits, FY24: [Outlook Business](https://www.outlookbusiness.com/markets/fo-frenzy-over-93-retail-investors-lost-average-rs-2-lakh-in-three-years-says-sebi), [Benzinga](https://in.benzinga.com/24/09/40994647/sebi-study-unveils-93-of-individual-f-o-traders-suffered-losses-between-fy22-and-fy24)
- Day-trader skill in Taiwan (Barber et al.): [paper](https://faculty.haas.berkeley.edu/odean/papers/day%20traders/Day%20Trading%20Skill%20110523.pdf)
- ORB replication: [MQL5](https://www.mql5.com/en/blogs/post/776235)
- LLM headline scores (Lopez-Lira and Tang): [arXiv](https://arxiv.org/abs/2304.07619v5)
- LLM reading of earnings releases (Siano 2025): [summary](https://academicnewsletter.sufe.edu.cn/info/395835)
- Momentum in India: [JCAR](https://www.publishingindia.com/archive/jcar/can-small-investors-gain-from-momentum-trading-in-india-an-empirical-investigation), [Managerial Finance](https://emerald.com/insight/content/doi/10.1108/03074351211193730/full/html)
- PEAD in India: [Gupta and Dhusia](https://journals.vutbr.cz/index.php/trends/article/view/541), [Nottingham](https://eprints.nottingham.ac.uk/26569)
- Short-term reversal after costs (De Groot, Huij and Zhou): [JBF](https://ideas.repec.org/a/eee/jbfina/v36y2012i2p371-382.html)
- Overnight vs intraday returns in India: [Capitalmind](https://premium.capitalmind.in/2019/10/while-you-were-sleeping-what-stocks-do-overnight-versus-in-trading-hours/)
- Day vs night returns on Nifty options (Bhat, Pandey and Rao): [JFM 2024](https://ideas.repec.org/a/wly/jfutmk/v44y2024i8p1320-1337.html), [note on costs](https://harbourfrontquant.substack.com/p/volatility-risk-premium-is-a-reward)
- Day vs night option returns in the US (Muravyev and Ni): [summary](https://academicnewsletter.sufe.edu.cn/info/355741)
- Jane Street expiry-day order: [ECGI](https://www.ecgi.global/publications/blog/expiry-day-and-the-governance-of-algorithmic-trading-the-jane-street-episode)
- Straddles before earnings (Gao, Xing and Zhang): [JFQA](https://resolve.cambridge.org/core/journals/journal-of-financial-and-quantitative-analysis/article/anticipating-uncertainty-straddles-around-earnings-announcements/7B34877AD5E06304BA3C55FBA3219FDD)
- Market intraday momentum (Gao, Han, Li and Zhou): [JFE](https://profiles.wustl.edu/en/publications/market-intraday-momentum/)
- Time-series momentum and trend following: [Moskowitz, Ooi and Pedersen](https://fairmodel.econ.yale.edu/ec439/jpde.pdf), [Hurst, Ooi and Pedersen](https://fairmodel.econ.yale.edu/ec439/hurst.pdf)
- Momentum in Indian commodity futures: [AJBA](https://ajba.um.edu.my/article/view/19492)