# MCX commodities module review: a CTA's view (2026-10-12)

## 1. Verdict

**Keep the operations layer exactly as designed. The strategy layer has its priorities backwards.**

- **What's right.** These belong in Phase 2 and should stay:
  - D12's operations layer: per-expiry `contract_calendar`, compulsory delivery for GOLDPETAL/GOLDTEN, energy rolls at T−6 sessions, margin stress multiples (silver 5x, gold 3x, energy 2x), band-lock handling.
  - Minis and micros only.
  - The LLM never executes.
- **What's wrong.** Slow, diversified trend following is the one MCX strategy with a century of evidence, and the design weakens it four ways:
  - C1 is a single-speed Donchian-20 with arbitrary ADX/EMA50 filters.
  - The risk budget allows one overnight position: "hold crude or gold, not both."
  - It is scheduled late (weeks 5–13; LLM books only in Phase 5).
  - Its gates are trade counts it can never reach. Report 11 asks for "≥ 20 trades in 6 months"; red-team report 12 already says that proves nothing.
- **Where the effort goes instead.** Design attention goes to the evening breakout (C2) and EIA variants, which have weak or no retail evidence.
- **One position at a time is a single-market trend book.** Expect a Sharpe of about 0.1–0.3 [J], multi-year dead spots, and returns that depend on luck. Trend pays through breadth plus volatility scaling.
- **Recommendation:** make commodity trend a core diversifying sleeve and start it in paper now, alongside equity season 1. It costs ₹0 in LLM spend, needs one decision a day (the laptop only has to be awake until about 22:00), and costs 0.01–0.04R per trade. Be honest about size, though. At ₹10L with a 1% gap reserve, expect **+₹10–25k a year (Sharpe 0.25–0.4 at 4–6% sleeve volatility)** [J]. It diversifies; it will not make the account profitable on its own.

**Evidence base**
- Moskowitz, Ooi & Pedersen (JFE 2012): 12-month time-series momentum was profitable in every one of 58 futures, 1985–2009 (H). The diversified portfolio's Sharpe was about 1 gross (M; secondary source).
- Hurst, Ooi & Pedersen (2017): trend was positive in every decade since 1880 (H). Sharpe about 0.4 after 2-and-20 fees (M). The average *single-asset* gross Sharpe was only 0.29–0.36 (M). This is the breadth argument.
- Counter-evidence:
  - Huang et al. (JFE 2020) find weak asset-by-asset predictability; trend profits are close to those of a historical-mean strategy (H).
  - Boubaker et al. report a commodity time-series-momentum Sharpe of **0.07 for 2010–2018** (M).
  - SG Trend Index: +27% in 2022 (H), −10.5% in H1 2025 (M). Returns are lumpy.
- India: Jaiswal & Uchil (2020) find MCX momentum profits that survive costs, vary over time and have low correlation with stocks and bonds (M). Barik & Balakrishnan (2017) are less favourable (L–M). MCX crude, gold and silver are CME prices × USDINR (× duty), so the global evidence transfers [J].
- Volatility targeting does not raise Sharpe in commodities, but it cuts left-tail events in every asset class (Harvey et al. 2018, H). Use it for tail control.

## 2. Cost math per round trip

Statutory costs ≈ **1.72 bps of notional**: CTT 0.01% on the sell side, MCX transaction charge 0.0021% per side, stamp duty 0.002%, the SEBI fee, and GST on the exchange charges. Brokerage of ₹20 per order (₹23.6 with GST) adds **₹47.2 per round trip**. At these notionals the ₹20 cap binds on both Zerodha and Upstox. Prices are early-October 2026.

| Trade | Notional | Fees + tax | Slippage (assumed) | Total | bps | Relative to risk |
|---|---|---|---|---|---|---|
| CRUDEOILM, 1 lot | ₹85k | ₹62 | 1 tick per side = ₹20 | **₹82** | 9.6 | Trend stop (2.5 ATR ≈ ₹6.25k): **0.013R**. ESB with a 0.25% stop: 0.39R |
| CRUDEOILM, 7 lots (ESB, ₹3k risk, 0.5% stop) | ₹5.95L | ₹150 | ₹140 calm; ₹560–1,400 around events | ₹290–1,550 | 4.9–26 | **0.10R calm, 0.2–0.5R near events** |
| CRUDEOILM roll (2 legs, 1 lot) | — | ₹62 | ₹20 | ₹82 | 9.6 | About 12 a year ≈ ₹1k per lot |
| GOLDPETAL, 10 lots (one order) or GOLDTEN, 1 lot | ₹1.49L | ₹73 | ₹20 | ₹93 | 6.2 | 12 forced rolls a year ≈ 0.75% of notional a year |
| SILVERMIC, 1 lot | ₹2.26L | ₹86 | ₹20 | ₹106 | 4.7 | 6 rolls a year |
| SILVER100, 3 lots | ₹68k | ₹59 | verify the tick | ~₹70 | ~10 | Monthly rolls ≈ 1.2% a year |
| NATGASMINI, 1 lot | ₹72.5k | ₹60 | ₹50–100 | ₹110–160 | 15–22 | — |

**What the table shows**
- Including rolls, slow trend pays **about 0.03R per trade**. Annual cost for the whole sleeve is about ₹4–5k (0.4–0.5% of capital), mostly rolls.
- Flattening one positional crude lot for every EIA release would cost about ₹4k a year per lot. That is roughly a third of the lot's expected trend profit (about ₹11k a year at Sharpe 0.3).
- A routine 10% OTM monthly CRUDEOILM put costs about **₹1.15k per lot per month** (Black–Scholes at 45% IV, before skew), or about ₹14k a year. That is more than the expected profit, so no routine hedges.

## 3. Improvements, ranked by expected effect on profit

### #1 Rebuild C1 as a multi-speed, volatility-targeted trend sleeve
- **What:**
  - **Signals:** three EWMA crossovers (16/64, 32/128, 64/256 days) plus a normalised 40/80/160-day breakout, equally weighted. Scale to a forecast capped at ±2.
  - **Volatility:** EWMA with a span of about 35 days, blended 30% with 10-year volatility so spikes don't whipsaw size.
  - **Sizing:** lots = forecast × (instrument risk target ÷ daily σ per lot), rounded to whole lots.
  - **Buffer:** trade only when |desired − held| ≥ 0.75 lot. This stops integer-lot flip-flopping.
  - **Remove:** the ADX>20 and EMA50 filters, the no-Friday rule, and "no entries within 6 sessions of expiry". Enter in the next contract instead of skipping the signal.
  - **Risk targets:** sleeve volatility of 4% of capital at L1 and 6% at L3, mirroring the R ramp. Instrument weight 1/N with a diversification multiplier of about 1.4.
  - **Resulting per-instrument risk at L3:** about ₹1.9k a day at an average forecast.
  - **Daily σ of one unit:**

    | Unit | Daily σ |
    |---|---|
    | 1 CRUDEOILM lot | ≈ ₹2.4k |
    | 1 GOLDTEN lot | ≈ ₹2.1k |
    | 1 GOLDPETAL lot | ≈ ₹210 |
    | 1 SILVER100 lot | ≈ ₹630 |
    | 1 SILVERMIC lot | ≈ ₹6.3k (too big) |

- **Why:** the breadth and volatility-scaling evidence above. Multiple speeds diversify across trend horizons, and the slower speeds cut turnover.
- **Expected effect:**

  | Configuration | Effective bets | Net Sharpe [J] | Sleeve volatility | Expected ₹ per year | Expected 5-year max drawdown |
  |---|---|---|---|---|---|
  | C1 as designed (one position overnight) | ~1 | 0.1–0.3 | ~3% | ₹3–9k | 6–9% |
  | Multi-speed, crude + gold + silver, 1% reserve | ~2.3 | 0.25–0.4 | 4% | ₹10–16k | ~8% |
  | Same plus NG, 1.5% reserve | ~3 | 0.3–0.45 | 6% | ₹18–27k | ~12% |

  Expect 12–24-month flat or negative stretches.
- **Effort:** 1–2 weeks on top of the operations layer, which is mandatory anyway. ₹0 in LLM spend.
- **Risk:** overfitting, and backtests flattered by long bullion. Mitigated in #3.
- **Arena:** separate positional books:
  - T0 = C1 as specified (control)
  - T1 = multi-speed
  - T1+C = with carry
  - T1+E = with the LLM event shrink

  Track:
  - daily P&L
  - implementation shortfall against a backtest run on the same days (target < 10% of gross)
  - realised against modelled roll cost
  - correlation with the equity books (target < 0.2)
  - attribution by instrument and by speed

### #2 Replace the count-based overnight rules with a scenario stress budget
- **What:** delete "crude or gold, not both" and "at most 1 swing name while MCX positional is open". Instead, require that the **maximum loss across a scenario set** fits the reserve. Do not sum each position's 3×ATR gap. Scenarios:
  - duty cut: bullion −8%
  - Gulf de-escalation weekend: crude −12%, gold −2%
  - escalation: crude +15%, gold +4%
  - USDINR ±2%
  - Nifty −4% gap, beta-adjusted, applied to equity swing positions
  - a combined weekend
- **Why:** these shocks don't coincide. Summing them is about 1.5–2x too conservative and forces the sleeve down to one market.
  - Worked example: 1 crude lot plus 10 GOLDPETAL lots. Summed 3×ATR (₹7.5k) + 8% gap (₹11.9k) ≈ ₹19k, which fails. Scenario maximum ≈ ₹11.9k (duty cut).
  - With 6 GOLDPETAL lots (₹7.2k), the duty-cut scenario fits ₹10k. The de-escalation scenario then lands at about ₹12k (crude −12% ≈ ₹10.2k plus gold −2%), only marginally over. With 5 lots and the crude scenario at −10%, the scenario maximum is about ₹10k.
- **Owner decision to raise:** split the 3% worst day as **1.5% intraday / 1.5% overnight** at go-live. At R of 0.25–0.5% the intraday DLL rarely binds, so lowering it costs little intraday expectancy, while it buys the sleeve 50% more breadth. That is how NG becomes possible.
- **Arena:** log the scenario maximum and the realised overnight gap every day. Count reserve breaches (target 0).

### #3 Validate on long history; gate on robustness plus operations, not paper trade counts
- **Data:**
  - CME continuous futures × USDINR, 1990–2026 (Databento historical one-off, or free sources)
  - MCX bhavcopy (free, includes expired contracts)
  - Kite `continuous=1` daily data from 2011
- **Duty-neutral bullion series:** divide bullion prices by (1 + duty). Without that, the step from 6% to 15% looks like a long trend, and the July 2024 duty cut (MCX gold fell about 5–6% in a day, H) looks like a short breakout.
- **Gate:**
  - net Sharpe ≥ 0.3 over the full sample
  - positive in ≥ 60% of rolling 3-year windows
  - a parameter plateau: ±50% speed changes move Sharpe by less than 0.1
  - longs-only and shorts-only each non-negative in USD terms
  - deflated Sharpe > 0 across all logged variants
- **Paper's job:** 8–12 weeks to prove operations (zero missed rolls or tender cutoffs, 100% stop coverage, shortfall within the model). It cannot prove the edge: at about 20–40 entries a year, SPRT on trade counts would take a decade.

### #4 Contracts, rolls and delivery risk

| Contract | Position cap | Rule |
|---|---|---|
| CRUDEOILM | 1 lot (2 only if annualised volatility < 30%) | Roll at T−6 sessions or when next-month OI exceeds front, whichever comes first. Do both legs in the same 19:00–22:00 window. Never approach expiry: the April 2020 MCX contract settled at about −₹2,884 (H). |
| Gold | GOLDTEN 1 lot, or GOLDPETAL 6–12 lots in one order | Compulsory delivery: roll at broker cutoff − 2 sessions. GOLDTEN OI was about 26k contracts in Sep 2026 (M). |
| Silver | SILVER100, 2–4 lots | Only if the spread is ≤ 2 ticks. SILVERMIC (staggered delivery) only when one lot's σ ≤ 1.5× the instrument target. |
| NATGASMINI | 0 now | Enable only with a 1.5% reserve and a backtested marginal Sharpe > 0.05. One lot is about ₹3.3k a day of σ, and a 15% gap is about ₹11k. |

Treat gold and silver (correlation 0.75–0.85) as one cluster, capped at 50% of sleeve risk.

### #5 Gap and weekend control without paying for hedges
- **Shrink before scheduled events:** halve positions in the session before:
  - OPEC+ weekends
  - the Union Budget (1 Feb) and duty or GST news when `duty_change_risk` is high
  - MCX closures while CME is open
  - long weekends

  Code enforces the shrink; the LLM only supplies the calendar. Precedents: the Abqaiq weekend in Sep 2019 and the OPEC+ surprise cut in Apr 2023 both gapped crude 6–15% (M).
- **Disaster stop:** a wide stop at 4–5× ATR, as an SL-limit re-armed every day *after 10:00*. Spreads are 2–3x wider in the 09:00–12:00 session. This satisfies D1's broker-side stop rule. Normal exits are close-based. If price opens through the stop, exit with a protected order after the first 15 minutes. MCX GTT through the API is unconfirmed (M).
- **No routine puts:** see the cost math in §2.

### #6 Carry tilt on crude (and NG), no seasonality
- **What:**
  - Crude carry = annualised (front − next) ÷ front, from the MCX curve, volatility-scaled, at 20–25% of crude's forecast weight.
  - No carry signal on bullion: its contango is just INR interest rates and carries no information.
  - NG carry only if seasonally adjusted.
- **Evidence:**
  - Fuertes, Miffre & Rallis (2010): momentum plus term structure improves on either signal alone (H for the paper; M for applying it to a 1–2-market tilt).
  - Koijen et al. (carry).
  - Jaiswal (2021): the same combination on MCX (M).
- **Effect:** small, about +0.03–0.05 Sharpe [J].
- **Seasonality:** the evidence is cross-sectional across wide universes (L for 4 markets). NG seasonality is already priced into the curve, and Indian festive demand shows up as physical premiums, not in futures. Skip it.

### #7 Intraday evening session: research only; use the evening as the execution window
- **Why:** the documented crude intraday-momentum effect is about the US first and last half-hour and EIA days (Wen et al., *Energy Journal* 2023; USO studies; M).
  - NYMEX's last half-hour (14:00–14:30 ET) is 23:30–00:00 IST in summer and 00:30–01:00 in winter, at or after the MCX close, so it **cannot be traded on MCX**.
  - The evening session is arbitraged to NYMEX within seconds.
- **What:**
  - Keep C2 paper-only, and trade it only in the sleeve's trend direction (a test of entry timing).
  - It needs about 150 trades, roughly 9–12 months.
  - Allocate no live risk to it until it shows net ≥ 0.15R.
  - Execute the sleeve's orders at 19:00–22:00, when spreads are about 1 tick.
- **EIA protocol:** keep it for intraday positions, but **exempt positional holdings**. An EIA move is smaller than daily σ and is already inside the gap sizing.
- **Arena:** a counterfactual "flatten-for-EIA" book against "hold".

### #8 LLM role: calendar, circulars and shrink-only flags, with no directional input
- **What:**
  - Jev 1.13 (about $0.00002 per filing) parses MCX circulars and broker bulletins into `contract_calendar`; code validates against the instrument master.
  - It also triages duty, OPEC and margin headlines into shrink-only flags.
  - A weekly Sonnet review.
  - Total under ₹200 a month.
- **No veto on trend entries for at least 12 months:**
  - Trend P&L is concentrated in a few big moves (2022). A veto that removes one of five big winners wipes out the year.
  - With about 20–40 entries a year, the value of a veto can't be measured for years (report 18's base-rate trap).
  - A10 already keeps MCX out of the LLM books. Keep it out until there is evidence.
- **Arena:** T1 against T1+E. Measure the drawdown and tail reduction per rupee of return given up on flagged days, against pre-registered rules.

### #9 Capital efficiency (outside the module, but worth more than any MCX signal)
- **LIQUIDBEES:** Zerodha has allowed pledged collateral for MCX F&O since December 2024 (H). LIQUIDBEES counts as cash-equivalent for the 50% cash rule (M; verify with the broker).
  - A yield of about 5–6% on ₹8–10L is about **₹40–60k a year, more than the trend sleeve's expected P&L**.
  - Keep a cash buffer for MTM debits.
  - Paper books should credit the risk-free yield on idle cash, so "profitable" means beating about 6%.
- **GOLDBEES as an option for the long gold leg:** no STT on gold ETFs (H), and no rolls, tender or margin spikes. It is pledgeable. The trade-offs: long-only, cash-funded, day session only, and an expense ratio of about 0.5–0.8%.
- **Do not use SILVERBEES:** Indian silver ETFs traded at 5–12% premiums in Oct 2025 (H).

## 4. Cut or de-prioritise
- Live risk for C2 (evening breakout). Keep it paper-only research.
- The EIA fade, and further effort on EIA continuation.
- SILVERMIC intraday in Phase 2: a 9% lock on one lot is about ₹20k, the whole DLL.
- C1's ADX and EMA50 filters, the no-Friday rule, and the expiry-proximity skip.
- The count-based overnight caps (replaced by #2).
- The "≥ 20 trend trades in 6 months" go-live test, and SPRT on trade counts for trend.
- Routine CRUDEOILM put hedges, and any real-time CME data spend.
- NG intraday, base-metal minis (one lot is ₹4–6k a day of σ in thin books), and seasonality signals.
- Any MCX LLM trader book.

## 5. Top 5 recommendations
1. **Make a multi-speed, volatility-targeted trend sleeve (crude, gold, silver; NG conditional) the core MCX strategy, and start it in paper this month.** It is the best-evidenced edge in the whole design, needs no LLM spend, and costs about 0.03R per trade.
2. **Replace the count-based overnight rules with a scenario stress budget.** Ask the owner about a 1.5%/1.5% intraday/overnight split at go-live to get breadth.
3. **Validate on 30+ years of CME × USDINR plus MCX bhavcopy, with duty-neutral bullion series.** Gate on robustness plus 8–12 weeks of clean paper operations.
4. **Exempt positional holdings from the EIA flatten.** Use scheduled-event shrinks, wide disaster stops and strict roll and delivery discipline instead of option hedges.
5. **Limit the LLM to calendar parsing and shrink-only event flags (no direction, no veto), and earn yield on idle margin through pledged LIQUIDBEES.**

**Sources**
- [Moskowitz–Ooi–Pedersen, SSRN](https://papers.ssrn.com/abstract=2089463)
- [AQR TSMOM data](https://www.aqr.com/Insights/Datasets/Time-Series-Momentum-Original-Paper-Data)
- [Hurst–Ooi–Pedersen, Century of Evidence](https://oxfordstrat.com/coasdfASD32/uploads/2016/03/A-Century-of-Evidence-on-Trend-Following-Investing.pdf)
- [CXO summary: per-asset Sharpe](https://www.cxoadvisory.com/momentum-investing/intrinsic-momentum-diversified-across-futures/)
- [Huang et al., JFE 2020](https://ideas.repec.org/a/eee/jfinec/v135y2020i3p774-794.html)
- [Post-2009 TSMOM decay, Boubaker et al.](https://ideas.repec.org/p/hal/journl/hal-03323675.html)
- [Harvey et al., Volatility Targeting](https://people.duke.edu/~charvey/Research/Published_Papers/P135_The_impact_of.pdf)
- [Jaiswal & Uchil 2020 (MCX)](https://ajba.um.edu.my/article/view/19492)
- [Barik & Balakrishnan](https://jcrm.psgim.ac.in/index.php/jcrm/article/view/657)
- [Jaiswal 2021](https://inderscience.com/offers.php?id=111810)
- [Fuertes–Miffre–Rallis 2010](https://openaccess.city.ac.uk/id/eprint/6416/)
- [Koijen carry slides](https://www.fmg.ac.uk/sites/default/files/2020-08/Ralph-Koijen-slides.pdf)
- [Wen et al., EIA intraday predictability](https://ideas.repec.org/a/aen/journl/ej44-5-xu.html)
- [SG Trend 2022](https://www.hedgeweek.com/trend-followers-turn-leaders-ctas-deliver-record-returns-2022/)
- [SG Trend H1 2025](https://www.alternativeswatch.com/2025/07/01/trend-following-hedge-funds-loss-h1-societe-generale-index/)
- [MCX gold −6% on duty cut, 2024](https://www.businesstoday.in/amp/union-budget/story/union-budget-gold-and-silver-prices-fall-by-up-to-rs-4000-after-budget-cuts-customs-duty-to-6-438383-2024-07-23)
- [GOLDTEN specs](https://www.angelone.in/news/commodities/gold-ten-futures-to-begin-trading-on-mcx-from-april-1)
- [GOLDTEN OI](https://www.indmoney.com/commodities/futures/gold-ten)
- [MCX charges](https://support.rupeezy.in/support/solutions/articles/2100044913-what-are-mcx-transaction-and-other-charges-as-per-exchange-and-government)
- [Zerodha: collateral for MCX](https://zerodha.com/z-connect/updates/trade-commodity-fo-on-mcx-and-nse-using-collateral-margin)
- [Zerodha: STT on ETFs](https://support.zerodha.com/category/account-opening/charges-at-zerodha/articles/stt-etfs)
- [Silver ETF premiums, Oct 2025](https://moneylife.in/article/5-mutual-funds-freeze-silver-etf-subscriptions-as-prices-surge-and-physical-shortage-bites/78585.html)

**Design docs reviewed**
- /home/user/auto-trading/docs/design/trading-system-design.md (§6, §7.4, §7.5, §12, §15)
- /home/user/auto-trading/docs/design/ai-trader.md (A10)
- /home/user/auto-trading/docs/research/11-mcx-commodities-module.md
- /home/user/auto-trading/docs/research/12-red-team-mcx-commodities.md
- /home/user/auto-trading/docs/research/13-llm-trader-decision-process.md (§8)