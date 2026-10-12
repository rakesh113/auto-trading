# Options desk review: index and stock options sleeve, ₹10L account (as of 12 Oct 2026)

Market inputs: Nifty about 22,520 and India VIX 14.35 on 9 Oct ([JM Financial](https://www.jmfinancialservices.in/market-news-and-insights/1735991), M). Lot sizes are Nifty 65 and Sensex 20. I found no NSE circular revising them in Oct 2026, but 65 × 22,520 is about ₹14.6L, which is below the ₹15L contract-value floor. An upward revision at the next review is therefore likely (M). The system already reads lot sizes from the contract master, which handles this.

## 1. Verdict

**Safety and the "do not build" list are right.** These choices are well made:
- no naked selling, no non-expiry intraday condors, no selling straight after an IV spike, no OTM buying, no futures;
- the stop sits on the underlying, positions are sized by full repricing, and leg sequencing is enforced;
- expiry dates come from the contract master;
- index options are rules-only in season 1 (A10).

**The economic logic has three gaps.**

1. **The design is on the wrong side of the best-documented options anomaly.** In Nifty, sellers earn the volatility risk premium (VRP) overnight. Delta-hedged short-option returns are positive overnight and negative intraday ([Bhat, Pandey and Rao, J. Futures Markets 2024](https://ideas.repec.org/a/wly/jfutmk/v44y2024i8p1320-1337.html), M-H; I read the abstract only). This mirrors the S&P 500: delta-hedged returns of −0.7%/day split into −1% overnight and +0.3% intraday ([Muravyev and Ni, JFE 2020](https://ideas.repec.org/a/eee/jfinec/v136y2020i1p219-238.html), H). Option returns are also lower over weekends and holidays ([Jones and Shemesh, JF 2018](https://ideas.repec.org/a/bla/jfinan/v73y2018i2p861-900.html), H).
   - O1, which buys intraday, is on the right side of this.
   - O2, which sells intraday, is on the wrong side. The only exception is expiry-day decay.
   - The design has no overnight premium sleeve, and no explicit "options as the swing vehicle" sleeve accounted against the gap budget.
2. **Brokerage is the binding options cost, not STT.**
   - STT at 0.15% of sell premium is ₹5–15 per structure.
   - A 1-lot condor or fly is 8 orders. At ₹30 + GST (Upstox Plus), that is about ₹283, or 15–20% of a 1-lot credit.
   - What matters about the 2026 STT changes is the futures rate (0.05%). It kills futures-based delta hedging and gamma scalping.
3. **O2's economics are marginal at 1 set** [J, Black-Scholes with √t decay].
   - At 13:00 on expiry day, a 100-point-wing Nifty iron fly collects about 60–70% of the ATM straddle.
   - If spot pins at the strike, the fly is still worth about 40% of its entry value at 15:00. The last 30 minutes carry the steepest decay. Capture is therefore about 35–45% of credit, so the 50–60% take-profit needs both a pin and an IV drop.
   - Expected gross edge is theta × (1 − RV²/IV²). At RV/IV of 0.85–0.9 that is about ₹330–490 per set. Costs are ₹350–400 at ₹30/order and ₹100–120 at zero brokerage.
   - Net is roughly −₹400 to +₹150 per set at current tariffs.
   - Expiry is also the most competitive arena. About 59% of index-option turnover is same-day expiry, and 99% of prop and FPI profits come from algos ([SEBI FY26 study via Moneylife](https://www.moneylife.in/article/92-percentage-of-aggregate-losses-incurred-by-individuals-are-from-options-trading-sebi-study/81429.html), [fintechbiznews](https://fintechbiznews.com/govtregulators/sebi-released-2-analytical-studies), M).
   - The 15:00 exit is still correct. Since the Closing Auction Session (CAS) began, the official Nifty close (the settlement price) has differed from the 15:15 last trade by 150–200 points on some days, about 0.42% on average in the first sessions ([multibagg](https://www.multibagg.ai/market-pulse/articles/nifty-expiry-cas-options-impact-cmsygcmg1181t0zo56s3085q1), L).

**Base rates.** 91% of individual F&O traders lost money in FY25, with net losses of ₹1.06 lakh crore ([Business Standard](https://www.business-standard.com/amp/markets/news/net-losses-of-traders-in-fo-widens-in-fy25-sebi-study-125070701221_1.html), H). In FY26, 87.7% lost while prop desks earned about ₹44k crore gross, 98% of it from options ([Business Today](https://www.businesstoday.in/markets/story/proprietary-traders-derivatives-profits-fall-in-fy26-says-sebi-study-550558-2026-08-21), M). Simple retail options rules start with negative expectancy.

### Strategy scorecard (₹10L, 2026 costs)

| | Strategy | Net after costs [J] | Drawdown profile | Evidence | Call |
|---|---|---|---|---|---|
| a | Weekly defined-risk VRP, held **overnight**: iron condor or broken-wing butterfly | Small positive only with low brokerage: about ₹70–410/set/week at zero brokerage, about −₹170 to +₹230 at ₹30/order | Negative skew; about 75–85% of weeks win; worst week = max loss (about ₹5k/set) | Nifty VRP positive and overnight (Bhat 2024, M-H); Nifty short strangles profitable 2007–19, costs unclear ([Bangur 2020](https://ideas.repec.org/a/rsk/journ6/7721271.html), M); India VRP pricing contested ([Sankar et al. 2020](https://ideas.repec.org/a/eee/reveco/v70y2020icp321-334.html), M) | Paper counterfactual book (O4); live only with low brokerage and owner sign-off |
| b | Expiry-day theta (O2) | About break-even | Small negative skew | 0DTE VRP exists but static hold-to-expiry Sharpe ≈ 0 ([Dim, Eraker and Vilkov summary](https://harbourfrontquant.substack.com/p/the-rise-of-0dte-options-cause-for), L); Nifty intraday short returns negative (M-H) | Demote to research |
| c | Selling the results IV crush | No documented edge | Lumpy gap tails | US: earnings straddles bought 3 days before the announcement earn **+3.34%**, so pre-announcement uncertainty is *under*-priced ([Gao, Xing and Zhang, JFQA 2018](https://alphaarchitect.com/2013/02/straddle-earnings-announcements-and-win/), H for the US); stock-option spreads 1–3% (report 09, P) | Research only; the anomaly favours buying the run-up |
| d | Intraday directional buying on trend days (O1) | Unknown signal edge; friction tiny, about 0.03R | Positive skew; 35–45% win rate; 8–12-loss streaks; drawdown 10–15R | Intraday long-option returns ≥ 0 (Muravyev-Ni; Bhat); market intraday momentum ([Gao, Han, Li and Zhou, JFE 2018](https://alphaarchitect.com/2014/08/attention-prop-traders-the-first-half-hour-of-trading-predicts-the-last-half-hour/), H for US, M internationally, none found for Nifty) | **Highest-upside sleeve; validate first** |
| e | Debit spreads to express LLM swing views | Depends on the view's edge; the vehicle itself is efficient | Bounded: max loss = debit | [J]; FINSABER-style LLM results warn the view edge may be zero (report 17) | Add as the swing vehicle |

**Whole options sleeve:** about −3% to +8% a year, central +1–3% [J]. That does not cover the ₹60–84k a year of LLM spend. O1 is the only sleeve with meaningful upside.

### Sizing inside the 2% / 1% / 25% framework

| Sleeve | Budget | Rule |
|---|---|---|
| O1 | Intraday DLL_eff; options sub-cap 40% (₹8k on a clean day) | R = ₹2.5k at L1, rising to ₹5k. 1 lot at L1 (a 40-point stop at Δ0.6 ≈ ₹1.6k plus costs). At most 2 concurrent. Premium ≤ 2R ÷ 35%. Flat by 15:10. |
| O2 | Intraday | 1 set, max loss **≤ ₹3k** (not ₹5k), counted at full max loss in the open-risk invariant. |
| O4 + spread swings + CNC + MCX positional | **Shared 1% gap reserve** | Defined-risk structures count at max loss. Suggested split: O4 ≤ ₹5k, debit-spread swings ≤ ₹5k (≤ ₹2.5k per name). CNC and MCX shrink when these are on. An open O4's daily MTM already reduces DLL_eff through the existing formula. |
| Kill rules | 25% drawdown ladder applies | O4: stop after 3 max-loss units in a rolling quarter. O1: SPRT after 60 trades (existing gates: ≥ +0.15R, profit factor ≥ 1.3). |

## 2. Improvements, ranked by expected impact on profit

### #1. Validate and sharpen O1 (intraday long gamma)
- **What:**
  1. Before paper, test the underlying signal offline on 10+ years of Nifty 1-min candles (free): breakout continuation, plus a **late-day continuation** variant (first-30/60-min return predicting 14:30–15:10). Then translate it into options P&L with Black-Scholes repricing and a spread model.
  2. Trade the **next weekly** contract, ITM at Δ0.60–0.70, whenever the current weekly has ≤ 2 days left. That cuts theta% and gamma whipsaw.
  3. Keep the hard flat at 15:10 (never hold long premium overnight).
  4. Fix the RV/IV clock mismatch flagged by red team 10 and refit the 0.8/0.35 thresholds.
- **Why:** intraday is the only window where long options don't pay the VRP. Friction is about ₹135 per 2-lot round trip (≈ 0.03R), against the 0.2R gate for cash.
- **Expected effect:** at +0.10R × ~120 trades × ₹5k, about ₹60k a year (6%). At 0R, nothing is lost but time.
- **Cost:** about 1–2 dev-weeks; no LLM spend.
- **Risk:** the base-rate trap; overfitting on about 55 Tuesday-regime expiries. The post-CAS close differs, so test after 3 Aug 2026 separately.
- **Arena:** O1-rules vs a **random-time placebo** (same days, same direction count) vs O1-in-futures (cost check). Pre-registered existing gates.

### #2. Add O5: debit spreads as the swing and event vehicle
- **What:**
  - Express LLM or rules swing views (1–5 days) as debit spreads: index first, then the top ~20 liquid stocks only.
  - At least 7 sessions to expiry; stocks exit before expiry week (physical settlement).
  - Prefer **bear put spreads**: the short OTM put sells the rich side of the skew. Bull call spreads sell the cheap side.
  - Code picks strikes; debit = max loss, counted against the gap reserve.
- **Why:**
  - Long options held overnight pay the VRP (Bhat; Jones-Shemesh). A spread neutralises most of that.
  - Per rupee of gap budget, a Nifty 100-wide call spread at about 6 days to expiry (debit ≈ ₹3k, about 20 Nifty units of delta ≈ ₹4.5L notional) carries **3–7× the delta** of CNC under the §7.5 shock rule (about ₹50–70k notional per ₹2.5k).
- **Expected effect:** makes the swing module economically meaningful. The profit still depends entirely on the view's edge.
- **Cost:** low; the repricing engine exists.
- **Risk:** stock legs cost 2–4% of the debit per round trip; capped upside.
- **Arena:** every swing nomination is booked as CNC and as a spread on the same signal. Compare net R per rupee of gap budget.

### #3. Fix the options cost stack
- **What:**
  1. For the live options account, verify a zero- or low-brokerage API venue: [Flattrade](https://flattrade.in/llms.txt), [Shoonya](https://select.finology.in/broker/shoonya/faq) or [Kotak Neo Trade Free API](https://www.kotakneo.com/about-us/media-and-press/kotak-neo-introduces-zero-brokerage-zero-fee-trade-apis-for-retail-traders/) (M). Check static-IP and algo-ID support and order-stream reliability.
  2. Minimise legs: 2-leg credit spreads where a view exists, and let OTM legs expire instead of buying them back.
  3. Put all lots in one order.
  4. Run every paper book under two tariffs (₹30/order and ₹0).
- **Why:** an 8-order condor at ₹30 + GST is ₹283, or 15–20% of a 1-lot credit.
- **Expected effect:** turns O2 and O4 from about zero to modestly positive, roughly +₹10–25k a year if both run.
- **Cost:** one adapter plus conformance tests.
- **Risk:** reliability of a smaller broker's API. Keep the hexagonal adapter so the venue can be swapped.
- **Arena:** net-after-cost ledger under both tariffs, and realized slippage against the model.

### #4. Demote O2 and stop structurally negative trades
- **What:**
  - O2 becomes a research book: 1 set, max loss ≤ ₹3k. Test a 2-leg credit-spread variant (4 orders).
  - Add an **unconditional twin** that sells every eligible expiry, to show whether the range filter adds anything.
  - Keep shorts flat by 15:00 (CAS settlement risk).
  - Hard rule: no intraday short premium on days that are not expiry days.
- **Why:** the computation in §1 shows O2 is about break-even, and Nifty intraday short returns are negative.
- **Expected effect:** avoids a likely bleed of −₹5k to −₹15k a year, or finds a small filtered edge.
- **Cost:** trivial.
- **Arena:** filtered vs unconditional; capture % of credit; P&L on VIX +15% days.

### #5. Build O4: overnight defined-risk VRP, as a free counterfactual book first
- **What:**
  - Enter Wednesday or Thursday 14:30–15:00 for the Tuesday expiry.
  - Shorts at about 0.15Δ (≈ ±420 points), 100-point wings. Credit about 22–28 points (₹1.4–1.8k), max loss about ₹4.7–5k [J].
  - Exit at 50% of credit or Monday 15:00, so the position is never held into expiry-day ELM or CAS settlement.
  - Enter only if IV ÷ HAR-forecast RV ≥ 1.15, VIX is not up more than 15% over 5 days, and there is no binary event in the window (RBI, Budget, election results, FOMC or US CPI nights, heavyweight results).
  - Use broken-wing butterflies rather than naked ratio spreads.
- **Why:** the VRP is earned overnight and over weekends (Bhat; Jones-Shemesh). O4 also complements O1: own gamma by day, sell it by night.
- **Tail:** on 4 Jun 2024, Nifty closed −5.93% with an intraday low near −8.5%, VIX rose about 40%, and a put went from ₹98 to ₹996 ([Moneylife](https://moneylife.in/article/nifty-sensex-crash-on-election-surprise-tuesday-closing-report/74316.html), [Business Standard](https://www.business-standard.com/amp/markets/news/lok-sabha-election-results-trends-send-options-market-in-a-tizzy-124060401523_1.html), H). Wings are mandatory.
- **Expected effect:** +₹3–15k a year per set (0.3–1.5%); worst week −₹5k.
- **Cost:** low; rules only.
- **Risk:** this duplicates the owner's separate strangle/condor agent, so the owner carries the same short-vol tail twice. Go live only by explicit owner decision.
- **Arena first step (cheap, do it now):** decompose the recorded chain P&L for ATM and OTM weeklies into **overnight (15:25 → 09:20) vs intraday** segments. That confirms or refutes Bhat on our own data and informs O2 and O4 together. Backtest on expired-contract candles from Sep 2025 with a conservative spread haircut (there is no bid/ask history).

### #6. LLM as veto, structure picker and event-uncertainty ranker (never numbers)
- **What:**
  1. A weekly O4 entry veto plus an expiry-day O2 veto: Sonnet or Opus with reasoning (Opus refuses without it), 1–2 calls a week, reading the scheduled calendar plus geopolitical and overnight-US risk. It may **only block or shrink**.
  2. Jev (0.5–0.9 s, about $0.00002 per call) for headline triage that triggers an O1 entry blackout. Market signals (VIX jump, 1-min futures range, spread blowout) remain the hard veto.
  3. Structure choice from a closed menu (none / debit spread / broken-wing butterfly / condor / fly), based on code's `chain_state`. Code picks strikes and size.
  4. For results, the LLM predicts |actual move| ÷ implied move per name, scored by information coefficient (IC).
- **Why:** VRP losses cluster in event and shock regimes, and reading events is the LLM's plausible edge. Numbers stay in code.
- **Expected effect:** small, and measurable only over months: 1–3 decisions a day gives a small sample.
- **Cost:** under ₹100 a month.
- **Arena:** rules book vs LLM-vetoed book on identical moments. Veto value = mean outcome of vetoed cycles.

### #7. Results event-vol research track
- **What:** on the top 25 names over the last 6–8 results seasons (about 150–200 events) from expired candles, test:
  - (a) the pre-event IV run-up (long straddle from 3 days before to the announcement);
  - (b) a defined-risk crush sale.
- **Why:** the US evidence favours (a); India is untested.
- **Expected effect:** unknown; go to paper only if the edge is at least 2× costs.
- **Cost:** about 1 week.
- **Risk:** small sample and wide spreads.
- **Arena:** paper only, at half size.

## 3. Cut or de-prioritise
- **O2 as a profit target:** keep it as research only (#4).
- **Holding long premium overnight** in any form other than a spread.
- **Sensex on days other than Thursday**, and Sensex O1 until it passes the whitelist.
- **0DTE momentum bursts:** stay deferred. ATM theta is about 7–8 points an hour.
- **Live stock-option news or results trades**, and front-month stock options in expiry week.
- **Ratio spreads with a naked extra short** (use broken-wing butterflies instead), and IV-spike selling intraday.
- **Futures delta-hedging and gamma scalping** (0.05% STT).
- **OI, PCR, max pain and GEX as gates:** OI is about 3 minutes stale. Keep them as context only.
- **A second live weekly-strangle engine** that duplicates the owner's separate selling agent, unless the owner explicitly wants that tail twice.

## 4. Top 5 recommendations
1. **Validate O1 first.** Run the offline 10-year underlying test, then paper with a random-time placebo. Use the next weekly ITM at Δ0.6–0.7 and a hard 15:10 flat. It is the only options sleeve with roughly 5–10% a year of upside.
2. **Add O5 debit spreads** as the swing and event vehicle, accounted at max loss against the 1% gap reserve. It gives 3–7× more delta per rupee of gap risk than CNC, with bear put spreads preferred.
3. **Fix the cost stack.** Verify a zero or low-brokerage API venue for options, use 2-leg structures, let OTM legs expire, and run paper under two tariffs. Brokerage, not STT, decides whether selling sleeves are positive.
4. **Re-align with the day/night evidence.** Demote O2 to research with an unconditional twin. Run the overnight-vs-intraday P&L decomposition on our recorded chains now. Build O4 (overnight, defined-risk, event-vetoed) as a free counterfactual book, and take it live only by owner decision given the separate agent.
5. **Use the LLM only as a veto, a structure picker and an event-uncertainty ranker.** It never sets strikes, greeks or size. Measure it as veto value in the arena, and expect a slow verdict.

Sources not linked above: [Dim, Eraker and Vilkov 0DTE discussion](https://harbourfrontquant.substack.com/p/the-rise-of-0dte-options-cause-for), [SEBI FY26 (Outlook Money)](https://www.outlookmoney.com/invest/nearly-88-of-retail-derivatives-traders-incur-losses-even-as-participation-cools-says-sebi-study), [NSE lot revision, Oct 2025 (Zerodha)](https://zerodha.com/marketintel/bulletin/429705/revision-in-lot-size-of-index-derivative-contracts-from-december-30-2025), [SEBI weekly-expiry status (Angel One)](https://www.angelone.in/news/market-updates/sebi-may-shift-to-fortnightly-expiry-to-curb-index-options-activity-report). Design inputs: /home/user/auto-trading/docs/design/trading-system-design.md §5–§8, /home/user/auto-trading/docs/design/ai-trader.md (A10, §8, §16), /home/user/auto-trading/docs/research/09-intraday-options-module.md, /home/user/auto-trading/docs/research/10-red-team-intraday-options.md, /home/user/auto-trading/docs/research/02-regulation-margins-costs.md.