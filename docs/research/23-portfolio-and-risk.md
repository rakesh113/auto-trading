# Portfolio and risk review: combining the sleeves into one book (₹10L)

## 1. Verdict

**The risk rules for each trade are good, but there is no portfolio layer, and costs eat most of the expected gross at the starting size.**

**What is right:**
- Code enforces the risk rules, and the LLM can only shrink size.
- Gates are stated in R.
- Each paper book trades its own full ₹10L.
- The sceptical prior (N(0, 0.1R), worth about 170 trades) and allocating on the lower confidence bound (LCB) are in report 16 §4.
- The drawdown ladder is sound. My simulation (below) shows it cuts the chance of reaching the 25% drawdown by roughly 10×.

**What is missing or wrong, from a portfolio point of view:**
1. **Nothing measures the combined book.** Every sleeve is judged on its own. The module sub-caps (Equity 60%, Options 40%, MCX 40%, Scalping 25% of DLL_eff) are "caps, not allocations, and not additive". So nothing estimates how the sleeves move together, how often the combined book hits the daily stop, how much margin it uses at peak, or its drawdown.
2. **The worst-day budget sits where costs are highest.** Intraday gets 2% and overnight gets 1%. Inside the overnight 1%, the swing rule is: per-name shock = 2 × P95 gap, a floor of 5–10%, ≤ 0.25% of equity per name, summed linearly. That caps a swing position at about ₹36–50k, or about ₹1.5L in total. So the horizon where costs per unit of move are lowest (delivery round trip ≈ 0.23% against 3–8% moves) cannot contribute. The 2%/1% split is not the problem. Summing worst cases linearly is.
3. **Fixed costs are not scaled to R** (table below). At live stage L1, LLM spend plus infrastructure is larger than the expected net profit.
4. **The ladder's deepest steps don't work for intraday trading.** At 0.35x and 0.25x of R = 0.25%, R is ₹875 and ₹625. The fixed ₹47–71 brokerage then fails the friction gate on its own, so those steps are a halt in disguise.
5. **No volatility targeting, no Kelly framing, and no stated return or drawdown expectation** for the combined book.

**Cost drag for the intraday sleeve** [J, using the design's own numbers]. Assumptions: 2.5 trades a day (625 a year), friction 0.15R at L1 and 0.13R at L3, and a target of +0.10R net of trading costs.

| | L1 (R = ₹2.5k) | L3 (R = ₹5k) |
|---|---|---|
| Gross edge needed | 0.25R | 0.23R |
| Gross P&L | ₹3.9L | ₹7.2L |
| Trading friction | ₹2.3L (60% of gross) | ₹4.1L (56%) |
| LLM at ₹7k/month | ₹0.84L (21%) | ₹0.84L (12%) |
| Infra at a ₹3k/month target* | ₹0.36L (9%) | ₹0.36L (5%) |
| **Net / drag** | **₹0.37L (3.7%/yr) / 91% of gross** | **₹1.9L (19%) / 73%** |

*The design's "full cloud stack" at ₹15–25k a month would add 18–30% of capital a year (design §2). Reject it.

SEBI's FY23 study fits this picture [H]:
- 71% of individual intraday traders lost money; 80% of those making more than 500 trades a year lost.
- Loss-makers' trading costs equalled 57% of their losses.

**Expected outcomes: one sleeve versus the combined book.**

Method: a 20,000-path Monte Carlo with fat tails (t4) over 2 years [S/J]. The intraday sleeve ("A") has daily σ = 2.47R (2.5 trades, σ 1.3R per trade, within-day ρ 0.3) and pays the LLM bill. The other sleeves are:
- O2 expiry-day iron fly: +3% a year, σ 3.9%;
- MCX trend: +1.5%, σ 3.5%;
- event swing: +3%, σ 5%.

Correlations are from the table in §2.4. The combined runs assume ₹60k a year of LLM spend (Haiku/Jev first, no chart twin).

| Book | Edge of A | Year-1 mean | P(year < 0) | Median 2-year max drawdown | P(25% hit): no ladder / with ladder |
|---|---|---|---|---|---|
| A alone, R 0.25% | +0.10R | +7% | 25% | 10% | 1% / – |
| A alone, R 0.25% | 0 | −8% | 82% | 22% | 36% / – |
| A alone, R 0.5% | +0.10R | +25% | 14% | 17% | 15% / – |
| A alone, R 0.5% | 0 | −8% | 70% | 33% | 75% / – |
| **Combined, A at 0.25%** | +0.10R | **+17–18%** | 10% | 11% | 1.1% / **0.1%** |
| **Combined, A at 0.25%** | 0 | +0–1.5% | 48% | 17% | 18% / **1.6%** |
| Combined, A at 0.5% | 0 | ~0% | 51–62% | 25% | 61% / **23%** |
| Combined, A at 0.5% | +0.10R | +31–38% | 8% | 17% | 12% / 1.1% |

**What the simulation says:**
- **The most likely case is that the LLM has no edge.** Evidence:
  - fewer than 1% of Taiwan day traders were predictably profitable [H];
  - LLM strategies in FINSABER lost their edge out of sample [H].

  In that case the combined book with the ladder breaks even with a small chance of ruin. A single intraday sleeve at R = 0.5% loses money and probably hits the 25% stop.
- **Going to R = 0.5% before the edge is proven is the biggest risk to the account.** Even with the ladder there is a 23% chance of reaching 25%, because the LLM bill keeps running while size shrinks.

---

## 2. Improvements, ranked by expected impact on profit

### 2.1 Allocate capital on the lower bound, and kill fast at portfolio level (very high impact: it removes the −8% to −20% a year outcomes)

- **What.** Fund a sleeve only when the 10th percentile of its posterior edge is above 0. The prior is N(0, 0.1R), n₀ ≈ 170, with day-clustered σ. Add a **cost kill**: if no sleeve has LCB > 0 by week 14, LLM spend drops to triage only (about ₹1.5k a month), saving about ₹65k a year.
- **Why.** Report 16 already uses this prior; this rule applies it to money.
- **Effect.** It turns the "edge 0" rows above into "small loss, stop".
- **Cost.** About a day of work. **Risk:** a real but slow edge gets starved; the paper books keep running, so the evidence still accumulates.
- **Arena measure.** Posterior per book on the daily leaderboard, and the share of LLM ₹ spent on books with LCB ≤ 0.

### 2.2 R-ramp rule: 1/8 Kelly on the 10th-percentile edge (high impact: sizing errors are what reach the 25% stop)

- **Rule.** r = min(0.5%, c × q10(μ) / σ²_R, the vol-target cap), with c = 1/8.
- **Kelly is not the binding limit.** At +0.15R and σ 1.3R, full Kelly is about 9% of equity per trade. With intraday clustering it is about 6%. 0.5% is 1/12–1/18 Kelly. What binds is how uncertain the edge is.
- **Worked examples:**
  - 150 trades at +0.15R → posterior +0.07R, q10 −0.02 → **R = 0** (the paper gate is passed, but no live money yet).
  - 400 trades at +0.20R → q10 +0.07 → r ≈ 0.52% → **0.5%**.
  - 600 trades at +0.15R → q10 +0.057 → **0.42%**.
- **So full R takes roughly 400–600 trades, about 8–12 months.** That is consistent with S2.
- **Ruin check** [derived for GBM]. P(ever falling to 75% of starting equity) = 0.75^(2/c − 1):
  - ½ Kelly: 42%;
  - ¼ Kelly: 13%;
  - ⅛ Kelly: 1.3%.

  If the edge is overstated 2×, ⅛ behaves like ¼, which is why ⅛ is the right cap.
- **Other conditions to raise R.** The existing ones (≥ 20 days, ≥ 80 trades, live − paper ≤ 0.05R), plus realised drawdown < 10R. Raise R only at month boundaries. Size off min(start-of-month equity, HWM-adjusted equity): down fast, up slowly.
- **Arena measure.** Posterior q10 per book, and a "proposed R" column on the leaderboard.

### 2.3 Rebalance the 3% worst-day budget toward cheaper horizons with a new event-swing sleeve (high impact)

- **Overnight stress, measured properly.** Replace the linear sum of per-name 2×P95 shocks with a portfolio stress figure: a Nifty −4% factor shock, plus −10% idiosyncratic on the largest name, plus a correlated 99% shortfall on the rest. It still has to fit 1%.
  - Option: a Nifty put spread on the overnight long book, which turns factor gap risk into a known cost.
  - This lets a market-neutral or hedged book grow from about ₹1.5L to about **₹3–4L**.
- **New sleeve E, event swing (2–10 days, CNC or futures for shorts).** Jev triages every filing (about $0.00002 each, so about ₹50 a month). The top ~5 a day go to a Sonnet batch call after the close (about ₹200 a month).
  - The bet is post-results and order-win drift. Positions are entered after the event, never held through it.
  - **Why.** The LLM's real advantage (reading filings and scaling them to company size) does not depend on speed, while intraday trading charges it for every second of delay. Friction is about 0.05R, against 0.13–0.15R intraday.
  - **Evidence** [M, contested]:
    - post-earnings drift in India: about 6% over 64 days, long/short by earnings surprise, Nifty 500, 2002–17 (Harshita et al.);
    - a VUT study finds the market efficient around earnings.
- **Effect.** +2–5% a year at about 5% vol, ρ ≈ 0.2 with intraday [J]. **Cost:** 1–2 weeks of build. **Risk:** gaps; the event filter must hold.
- **Arena measure.** Books E-L (LLM), E-R (a rule ranking by surprise) and E-P (random catalyst names) on the counterfactual engine with delivery costs. Decide at about 100 trades.

### 2.4 Composite portfolio book, correlation monitor and volatility targeting (medium–high impact: lowers drawdown)

- **Add book PF.** It applies the target allocation (§3) through the real global risk engine: DLL_eff, overnight stress, margin and the 4x cap. It reports daily-stop hits, peak margin, risk contribution per sleeve and drawdown. The standalone ₹10L books stay as they are for comparability.
- **Expected correlations** [J], to be re-estimated from PF after 60 or more days:

| Pair | ρ |
|---|---|
| A vs O1 long index options | **+0.5** (same trend days: count as one bet) |
| A vs O2 expiry fly | **−0.2 to −0.3** (A wins on trend days, the fly on range days) |
| A vs MCX trend | ≈ 0 |
| A vs event swing | +0.2 |
| O2 vs event swing | **+0.3**, and it rises in crashes (short gamma plus long beta) |
| MCX crude long vs Nifty | negative in oil shocks (Brent ≈ $100) |
| Scalping vs A | +0.4 |

- **Volatility targeting.** Set an ex-ante portfolio σ target:
  - 0.5% daily (8% a year) at L1;
  - 0.75% (12%) at L3;
  - never above 15% a year.

  Each sleeve's R is scaled by min(1, target ÷ 20-day EWMA σ of its own P&L). The short-vol sleeve is also switched off by VIX rules.
- **Evidence.** Moreira–Muir report about a 25% Sharpe gain [H in sample]. The FAJ "Conditional Volatility Targeting" paper finds look-ahead bias in it and in Harvey et al.; Cederburg et al. report it fails out of sample [M]. So treat vol targeting as **a risk control, not alpha.**
- **Arena measure.** P(25% drawdown) and daily-stop hit rate in PF, with and without the scaler.

### 2.5 Cost-drag programme (medium–high impact: about 0.2R → about 0.14R per trade, plus treasury income)

1. **Scale LLM spend to risk.** Keep LLM ₹ ≤ 15–20% of a sleeve's expected gross. At L1 that means Haiku/Jev first and no chart twin V (target about ₹3.5k a month). Keep Sonnet decisions only if K6 shows Haiku's IC is worse by more than 0.02.
2. **Fewer, larger-stop trades.** Raise the minimum cash stop to 50–60 bps; friction falls from 0.2R to about 0.12R. Use passive entries only where markouts are proven.
3. **Zerodha at ₹20** rather than Upstox Plus at ₹30 (about ₹59k a year at 10 round trips a day, design §5).
4. **Treasury sleeve.** Keep idle cash (₹4–6L) in LIQUIDBEES or a liquid fund at about 6%, which is ₹25–35k a year.
   - Zerodha treats pledged liquid funds and LIQUIDBEES as cash-equivalent collateral for the 50% cash rule, with about a 10% haircut [M].
   - Pledged margin **cannot be used for MCX** [M], so MCX margin stays in cash.
5. **Live infrastructure ≤ ₹3k a month:** the laptop, a static IP, and a small VPS for the deadman process.
6. LLM and infrastructure spend are business expenses against non-speculative income from F&O and commodities [M, ask a CA].

- **Arena measure.** Expectancy bucketed by friction, "value-add ROI", and LLM ₹ as a share of gross per book.

### 2.6 Make the expiry-day iron fly (O2) the second sleeve, as an intraday hedge (medium impact)

- **What.** It costs ₹0 in LLM spend, is rule-based, and has defined risk. It earns on range days, when momentum setups chop, so it partly hedges A.
- **Evidence.** A variance risk premium is well documented globally [M]. I found no India-specific study [L].
- **Tail.** On 4 Jun 2024 (election results) Nifty fell about 6% in a day [H]. Wings, SIT-OUT on event days and 1 set per expiry contain this.
- **Effect.** About +2–3% a year, ρ ≈ −0.25 with A.
- **Arena measure.** Paired daily correlation of O2 and A in PF; ≥ 40 trades over 16 expiries.

### 2.7 Replace the bottom of the drawdown ladder with sleeve-drop (medium impact)

- At 10% or more drawdown, **drop the sleeve with the lowest LCB** instead of shrinking every sleeve below a workable R.
- Floor for intraday R: ₹2k; below it, switch the sleeve off.
- Cut LLM spend in step with the drawdown: one degrade-ladder step per drawdown step.
- **Evidence.** Grossman–Zhou: risk proportional to the cushion above a floor tied to the running peak [H]. In my simulation the existing ladder beat a gentler cushion-proportional rule (0.1% vs 0.2% chance of reaching 25%).

### 2.8 Keep MCX trend (C1) as a small diversifier, not a profit centre (low–medium impact)

- **Sizing.** 1 CRUDEOILM lot or ≤ 6 GOLDPETAL lots at 0.5–0.75% risk gives about 3.5% vol and **about +1–2% a year** [J].
- **Evidence:**
  - trend following worked in 8 of the 10 worst 60/40 drawdowns since 1880 (Hurst–Ooi–Pedersen) [H];
  - a study of 16 MCX commodities (2005–16) found no momentum [M-L];
  - trend following on 2 markets has a low Sharpe.
- Build only the rolls, delivery and margin-stress pieces C1 needs.

---

## 3. Target allocations

**Paper season 1.** The standalone books stay at full ₹10L for evaluation. PF applies the table below. The worst day stays at 3% (2% intraday + 1% overnight). Daily σ target 0.6%.

| Sleeve | Mode | Size | Daily loss sub-cap | Overnight stress | Capital use | LLM ₹/month |
|---|---|---|---|---|---|---|
| A: intraday equity (L, Hk, R, H, …) | as designed | R 0.25%, ≤ 4 entries | 1.2% | 0 | ≤ ₹4L MIS margin | ~3.5k (no V) |
| O1: long index options | rules; **shares A's cap** | R 0.25% | (in A) | 0 | premium ≤ ₹28k | 0 |
| O2: expiry iron fly | rules | 1 set, max loss ≤ 0.5% | 0.5% on expiry days | 0 | ₹1–1.2L | 0 |
| E: event swing (new) | E-L / E-R / E-P books | 0.25% to stop | – | ≤ 0.5% (portfolio stress) | CNC ≤ ₹3L | ~0.3k |
| C1: MCX trend | rules | 1 position | evening ≤ 0.4 × DLL_eff | ≤ 0.5% | ₹1–1.5L cash | 0 |
| MCX C2/C3, scalping | record only | – | – | – | – | – |
| Treasury | simulated accrual | – | – | – | the rest (≥ ₹4L) | – |

**First live phase.** Only gated sleeves go live, and only one book per sleeve: the one with the highest LCB, since L, H and R are correlated above 0.6. Vol target 8% a year. Keep ≥ 30% of capital free.

| Sleeve | Entry condition | Size | Share of risk |
|---|---|---|---|
| Intraday equity | Gate 1 + Gate 2 + S1 + q10 > 0 | R 0.25% → by the rule in §2.2 | 50–60% |
| O2 | ≥ 40 trades / 16 expiries, LCB > 0 | 1 set → 2 at L3 | ~15% |
| Event swing | ≥ 100 paper trades, LCB > 0 | ≤ 2 names, stress ≤ 0.5% | ~15% |
| MCX C1 | 10-year backtest (shorts and USD series checked separately) + 3 months of clean operations in paper | 1 position | ~10% |
| Treasury | always | ≥ 50% of capital | – |

**Realistic expectations for the combined book** [J]:

| Case | Return a year | 2-year drawdown |
|---|---|---|
| A has edge (+0.10R) | +12–18% | median about 11% |
| A has no edge, other sleeves modest | 0 to +3% | ~17%, ladder keeps P(25%) < 2% |
| Nothing works | about −6% a year (cost bleed), killed by month 4–5 | – |

---

## 4. Cut or de-prioritise

- **Chart twin V** (₹1.9k a month, about 30% of the core LLM spend). Don't start it in season 1.
- **R = 0.5% before q10 > 0.** The ladder steps at 0.35x and 0.25x for intraday.
- **O1 as its own sleeve.** Merge it into A's risk cap.
- **MCX evening breakout (C2), EIA trades and intraday MCX:** low edge, an evening operating burden, and 0.15–0.39R friction.
- **Scalping as a sleeve in 2026:** it has the worst cost per R; keep it as recording only.
- **The ₹15–25k a month cloud stack.**

---

## 5. Top 5 recommendations

1. **Allocate on the lower bound and kill fast.** No live risk while q10(μ) ≤ 0. Cut the LLM to triage only if no sleeve qualifies by week 14.
2. **Size R at 1/8 Kelly on q10(μ), capped at 0.5% and by the vol target.** Expect full R only after 400–600 trades.
3. **Build the composite book PF** with a correlation monitor, volatility targeting (8% a year at L1) and sleeve-drop de-risking.
4. **Move risk toward cheap horizons.** Measure overnight risk as portfolio stress and add the Jev-triaged, Sonnet-batched event-swing sleeve. Run the O2 expiry fly as the hedge for intraday.
5. **Cut cost drag.** Scale LLM spend to R, raise the minimum stop to 50–60 bps, use Zerodha at ₹20, keep infrastructure ≤ ₹3k a month, and put idle cash in LIQUIDBEES.

---

**Sources:**
- [SEBI intraday study FY23 (Business Standard)](https://www.business-standard.com/amp/markets/news/over-70-intra-day-traders-incur-losses-during-fy23-reveals-sebi-study-124072401110_1.html) [H]
- [SEBI F&O study FY25](https://www.business-standard.com/amp/markets/news/net-losses-of-traders-in-fo-widens-in-fy25-sebi-study-125070701221_1.html) [H]
- [Barber et al., day traders in Taiwan](https://faculty.haas.berkeley.edu/odean/papers/Day%20Traders/Day%20Trading%20and%20Learning%20110217.pdf) [H]
- [Zarattini–Aziz, opening-range breakout](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4416622) [M]
- [Hurst–Ooi–Pedersen, a century of trend following](https://www.chesler.us/resources/academia/A_Century_of_Evidence_on_Trend_Following.pdf) [H]
- [Moskowitz–Ooi–Pedersen, time-series momentum](https://elmwealth.com/wp-content/uploads/2017/06/timeseriesmomentum.pdf) [H]
- [MCX momentum, no effect found](https://www.proquest.com/docview/2070391899) [M-L]
- [Moreira–Muir, volatility-managed portfolios](https://www.nber.org/system/files/working_papers/w22208/w22208.pdf) [H]
- [Conditional Volatility Targeting, FAJ critique](https://www.tandfonline.com/doi/full/10.1080/0015198X.2020.1790853) [M]
- [Post-earnings drift in India, Harshita et al.](https://scirp.org/journal/paperinformation?paperid=88060) [M]
- [Indian market efficient around earnings, VUT](https://journals.vut.cz/index.php/trends/article/view/541) [M]
- [Grossman–Zhou, controlling drawdowns](https://onlinelibrary.wiley.com/doi/abs/10.1111/j.1467-9965.1993.tb00044.x) [H]
- [Zerodha, LIQUIDBEES collateral](https://support.zerodha.com/category/trading-and-markets/general-kite/funds/articles/what-does-liquidbees-collateral-margin-in-the-funds-mean) [M]
- [MacLean–Thorp–Ziemba, Kelly](https://www.stat.berkeley.edu/~aldous/157/Papers/Good_Bad_Kelly.pdf) [H]
- Internal: `/home/user/auto-trading/docs/design/trading-system-design.md` §5–§7, `/home/user/auto-trading/docs/design/ai-trader.md` §11–§16, research reports 02, 03, 09–12, 16 and 18.

Simulation scripts: [`scripts/portfolio_monte_carlo.py`](scripts/portfolio_monte_carlo.py), [`scripts/portfolio_monte_carlo_ladder.py`](scripts/portfolio_monte_carlo_ladder.py)