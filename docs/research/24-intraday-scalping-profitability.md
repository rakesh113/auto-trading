# Intraday equity and scalping: review for profitability (reviewer: senior NSE intraday trader / microstructure quant)

## 1. Verdict

**The structure is sound, but the economics are understated.** These parts are right: cash MIS for stock direction, no futures intraday, a friction gate, the plan-then-arm entry flow, risk owned by code, IC-first scoring, and recording depth from day 1. Read with realistic friction, though, the intraday book as specified will probably lose money. Three things drive that:

1. **The friction gate underestimates real cost by about 1.5x at the minimum stops.** It assumes 1 bp slippage per side and 2 orders per trade. Two facts contradict that:
   - The design's own paper model charges stop slippage of max(2 ticks, 0.05%), and 0.2% in news shocks (report 03 §9).
   - E1 and E3 scale out in 3 legs, so a trade is 3–4 executed orders, not 2.
2. **The rule library (T1–T9) is deliberately broad.** It includes non-catalyst ORB, midday VWAP and range fades. The design itself assumes these triggers average about −0.05R. With realistic friction, the raw pool sits nearer −0.10 to −0.15R. The needed LLM IC then rises from 0.11 to about 0.15 (E ≈ μ0 + 1.87ρ; +0.15R needs ρ = 0.28/1.87). That is very hard intraday [J]. **The bigger profit lever is raising μ0 (universe, timing, exits), not hoping for LLM selection skill.**
3. **The exits cut off the right tail.** Partials at 1R, 20–45 minute time stops, and the §6 rule "flatten everything when P&L falls to 50% of a peak ≥ ₹10k" all trim the trend-day runners that pay for the losers.

**Cash scalping (3–10 min, Tier A) is not a viable standalone edge** at ₹2.5k R. Details below.

**Capacity at ₹10L is not the constraint; friction is.** A ₹4–12L ticket is far below 1% of daily turnover in Tier A/B names. **The laptop is fine** for ≤ 6 trades a day using APPROACH/ARMED entries. It is not fine for live sub-second scalping over home broadband on Windows.

### Friction at the design's stop sizes (cash MIS)

Assumptions:
- Fees 3.55 bps; Upstox Plus brokerage ₹35.4 per executed order (incl. GST).
- Spread 3 bps; entry slippage 1.5 bps.
- Losers: stop slippage 5 bps (report 03's own paper model), 2 orders.
- Winners: target slippage 1.5 bps, 3 orders (one partial).
- Outcome mix 35% win / 25% scratch / 40% loss. That mix is typical when time stops are used [J].

| Stop | R | Notional | Gate estimate | Realistic, loser | Realistic, winner | Average gross winner to break even | Average winner for +0.15R |
|---|---|---|---|---|---|---|---|
| 45 bps | ₹2.5k | ₹5.6L | 0.20R | **0.32R** | 0.26R | **1.94R** | 2.37R |
| 60 bps | ₹2.5k | ₹4.2L | 0.15R | 0.25R | 0.20R | 1.77R | 2.20R |
| 80 bps | ₹2.5k | ₹3.1L | 0.12R | 0.19R | 0.16R | 1.64R | 2.07R |
| 45 bps | ₹5k | ₹11.1L | 0.18R | 0.30R | 0.23R | 1.89R | 2.32R |
| 80 bps | ₹5k | ₹6.25L | 0.11R | 0.18R | 0.14R | 1.59R | 2.02R |

**Win rate needed with no scratches,** 45 bps stop at ₹2.5k R (the paper books' R):
- 51% at a 1.5R average winner.
- 43% at a 2.0R average winner.
- The design's formula gives 40%.

Partial-at-1R brackets typically realise a 1.3–1.7R average winner [J], so at minimum stops they are underwater. **Every scratch costs about 0.25R.** A 3–5 minute "not at +0.3R" time stop on scalps therefore bleeds roughly 0.08–0.1R per trade.

**Scalp arithmetic.** A 2R target on a 45 bps stop needs a 90 bps move in ≤ 10 minutes.
- On an average day, 10-minute σ is about 26 bps for a 2%-ATR large cap (3.4σ away) and about 39 bps at 3% ATR (2.3σ).
- Only first-hour, in-play names with roughly 4%+ effective ATR get there.
- Tier A names (≤ 3 bps spread, ₹300 cr+ turnover) rarely qualify, so the overlap between "scalp-eligible" and "moves enough" is near zero on most days [J].

**For comparison,** a Nifty ATM option (2 lots, ₹150 premium, 15-point premium stop) costs about **0.07R**, consistent with report 02.

**LLM cost** is about ₹80 per trade (≈ 0.03R at ₹2.5k R). It is not the binding drag; trading friction is.

## 2. Improvements, ranked by expected effect on profit

### 1. An opportunity gate: trade only "stocks in play", and allow zero-trade days
- **What:**
  - New equity entries only on names with catalyst materiality ≥ 60, **or** a gap ≥ 1 ATR from the pre-open price with RVOL15 ≥ 3.
  - F&O names only for shorts.
  - If no name qualifies by 10:30, the equity book stands down.
  - Turn this into a hard rule. The in-play score is only a ranking today, and the R book runs on the top 15 regardless.
- **Why:**
  - SEBI FY23: 71% of individual intraday cash traders lost money, 80% of those with more than 500 trades a year. Loss-makers paid costs equal to 57% of their losses (H).
  - Fewer than 1–3% of day traders are predictably profitable net of fees (Barber–Lee–Liu–Odean, M-H).
  - Zarattini–Barbon–Aziz (2024) found ORB worked on the top-20 relative-volume "stocks in play". An independent index replication found the gross edge reproduced but net ≈ 0 (M). The paper charged commissions only, with no spread or slippage, so selection, not the breakout, carried the result.
- **Expected effect [J]:** μ0 +0.05 to +0.15R; trade count −40 to −60%.
- **Cost:** about a day of config and rules.
- **Risk:** fewer trades slows the arena, and quiet months produce almost nothing. Accept that; results seasons are where this module lives.
- **Arena:** split R-book and current E1/E2 paper results by opportunity class (catalyst / gap+RVOL / neither). Compare with P2, the non-in-play placebo. All of this is free.

### 2. Make the friction gate honest and widen the stop floor
- **What:**
  - friction_R = expected value over exit paths, using live spread from recorded depth by symbol and time of day.
  - Stop slippage = the paper model's (5 bps, 20 bps on news).
  - Brokerage = (exit legs + 1) orders.
  - Keep 0.2R on this realistic number. That puts the practical minimum stop at about 75–80 bps at ₹2.5k R and about 65–70 bps at ₹5k.
  - **Maximum 2 exit legs** (50% at T1, 50% trailed).
  - Add a rule: spread ≤ 0.08 × stop. Tier B's 8 bps spread allowance alone is 0.2R on a 40 bps stop.
- **Why:** the table above; 57% of retail losses are costs (SEBI).
- **Effect [J]:** removes trades that are negative by construction. +0.03 to +0.08R on the trades that remain. In practice the filter selects names with ATR ≥ 2.5–3%, which is the in-play set.
- **Cost:** about 2–3 days.
- **Risk:** trade count falls further.
- **Arena:** realised friction per trade compared with the gate's estimate, by tactic family. Pre-register a check: median realised/estimated friction ≤ 1.15.

### 3. Exit redesign: let catalyst and trend-day winners run, and remove the forced profit-protection flatten
- **What:** add three exploratory brackets to the Counterfactual Outcome Engine (COE). They cost compute only and do not change L's identity:
  - **B0:** the current default.
  - **B1:** no fixed partial; trail on the 15-minute swing or a 1.5-ATR(15m) chandelier; hold to 14:55 when the day is labelled trend.
  - **B2:** exit if not +0.5R by 25 minutes, otherwise B1.

  Also change §6 profit protection so that "50% of peak" **blocks new risk** but does **not** flatten positions whose stops are already in profit.
- **Why:**
  - ORB evidence shows a fat right tail: QQQ ORB had a 24% hit rate at +0.13R per trade, and the stocks-in-play version held to the close (M).
  - Market intraday momentum: the first half-hour predicts the last half-hour, more strongly on high-volume and news days (Gao et al., JFE 2018; H for the US, unverified for Nifty).
- **Effect [J]:** average winner +0.3 to +0.6R, win rate −5 to −10 points. Net ±0.1R, so the arena has to decide. Dropping the flatten rule alone is worth about +0.01–0.03R per trade, concentrated on the best days.
- **Cost:** about 3–5 days in the COE.
- **Risk:** more give-back; deeper intraday drawdowns.
- **Arena:** paired B0/B1/B2 on identical entries, day-clustered bootstrap. Decide before L's season 1 is frozen.

### 4. Concentrate on 09:20–10:45 and stop trading lunch
- **What:**
  - Primary window 09:20–10:45.
  - **No new equity entries 11:00–13:30.** This cuts the T6/T8 VWAP and range fades the design currently allows at lunch.
  - 13:45–14:40 only on a confirmed trend label, and only for leaders already in play.
  - Test a 5-minute vs 15-minute opening range (free in the COE).
  - Pre-arm opening-drive pullbacks (T7) for the top 2 catalyst names from a 09:12 pre-open call, so the first entries do not wait for the 09:31 open read.
- **Why:**
  - NSE volume and volatility are U-shaped or "reverse-J", concentrated at the open (Sampath & Gopalaswamy 2020; IIMA WP 2012; M).
  - Midday ranges are narrow, so stops are tight relative to friction, and VWAP acts as a magnet (report 03).
- **Effect [J]:** +0.03 to +0.05R per trade by removing lunch trades.
- **Cost:** config.
- **Risk:** low.
- **Arena:** R-book net R by 15-minute entry bucket.

### 5. Treat negative-catalyst shorts as a first-class setup, with symmetric eyes and no standing bias
- **What:**
  - Short tactics (failed rally to VWAP, PDL break-retest, results-miss first bounce) on F&O names.
  - The catalyst card weights negative events equally: misses, guidance cuts, blocks at a discount, regulatory action, pledge invocations.
  - Keep the rule that regime comes only from code.
- **Why:**
  - Indian evidence of drift after bad earnings news lasting more than a week (Nottingham event study, L-M).
  - LLM news scores predict best for small stocks and negative news, and this decays as adoption rises (Lopez-Lira & Tang, M).
  - "Bad news travels slowly" (Hong–Lim–Stein 2000, H).
  - Current tape: FIIs net sellers for 15 months.
- **Effect [J]:** +0.02 to +0.05R; more trades in a weak market.
- **Cost:** about a week of tactic work.
- **Risk:** short squeezes on F&O ban and OI-unwind names (keep the ban-list rule).
- **Arena:** results by side × catalyst sign; the monthly mirror audit.

### 6. Narrow what the LLM does intraday, and promote Jev for triage

| Ask the LLM | Do not ask it |
|---|---|
| Pre-market: which 3–5 names have catalysts material relative to size; priced-in; results trees; avoid list | Timing of generic MOMENTUM/FADE moments on non-catalyst names (send these to R and Hk only) |
| A 09:12 pre-open confirm/kill plus pre-arming | Day type, OFI/depth reads, chart-pattern names |
| Burst "rank and take k of N" at 09:25–09:45 | Time-stop extensions, trail changes, anything near a stop |
| News on held or watched names: "thesis broken?" (exit value) | Anything with less than 20 s to act |

- **Make CATALYST mode L's primary domain** and pre-register its IC. The arena has not started, so this is still allowed. Keep Haiku (Hk) scoring all moments so the general IC is still measured cheaply.
- **Jev 1.13** (0.5–0.9 s, about $0.00002 per filing) should be the lead triage candidate on 100% of filings, with Haiku as fallback. Update D11 in the main design, which says Jev is unreachable.
- **Why:** FINSABER and Alpha Arena (report 17) show weak LLM timing and pattern skill. The evidence for LLM value is in text and catalyst interpretation (Lopez-Lira & Tang).
- **Effect [J]:** a better chance of passing the K1 selection screen; Sonnet spend scales with results season.
- **Cost:** routing changes, about 2 days.
- **Arena:** IC on CATALYST moments vs other moments; K6 (Hk vs L).

### 7. Use maker orders where selection is favourable and taker where it is not
- **What:**
  - **Taker** (marketable limit) for breakouts and stops.
  - **Maker** for pullback entries (T1/T7), reported with the cost of missed fills.
  - Resting limit orders for target partials. When the target is hit, cut the stop order's quantity, behind the existing guard that blocks sells larger than the net position.
- **Why:** passive orders are adversely selected (Linnainmaa, JF 2010, H). A resting exit at a target is the favourable case.
- **Effect:** saves about 2–4 bps on winning exits, roughly +0.01–0.02R per trade.
- **Risk:** a double-fill race. Rehearse it in the fault-injection harness.
- **Arena:** fill rate and post-fill markouts by tactic family; missed-winner cost.

### 8. Build E3 (news-shock first pullback) next, ahead of anything for scalping
Phase 1 shipped E1 and E2. E3 is the setup best aligned with items 1, 5 and 6. Q2 results season runs to mid-November and the next one is mid-January to February 2027, so it needs to be in paper within about 3 weeks. Restrict E2 (VWAP reclaim) to catalyst names and trend-day leaders, because on range days VWAP is a magnet.

## 3. Cut or de-prioritise

- **Cash scalping as its own module.** Fold it into intraday as a fast-exit variant of E3/T7 on news names. Keep the recorder running. Drop the LightGBM meta-filter until some rule setup is positive on candles at *realistic* friction.
- **SC2 index-lead catch-up and absorption/wall reversals as executable setups.** Feed delays create fake lead-lag, and a snapshot feed cannot tell a cancel from a trade. Keep them as logged research features only.
- **Index-option scalps driven by Nifty futures order flow.**
  - Order-flow imbalance (OFI) explains *simultaneous* price changes; it does not forecast minutes ahead (Cont–Kukanov–Stoikov 2014, H). Any lagged content is gone at 1–3 snapshots/s with 100–500 ms lag.
  - Expiry-day index moves can be engineered by large players, with retail option traders on the other side (SEBI's Jane Street interim order, 3 Jul 2025, H).
  - 91% of individual F&O traders lost money in FY25 (SEBI, H).
  - If index options are used at all, use them for 15–60 minute Nifty level breaks (O1, the options reviewer's area). The cost advantage (about 0.07R vs 0.25–0.32R for cash) is real; OFI timing is not.
- **Relative-strength pairs intraday.** Two legs double the friction, and a lower-volatility spread makes friction relative to the stop worse. Use relative strength as a filter for which name and which side, single leg only.
- **Stock futures intraday** (already excluded). They cost about 2.1 bps more per round trip (≈ 0.03–0.05R), and one lot is a coarse size relative to a ₹4–12L ticket (lot sizes revised April 2026; L). Their only use is overnight shorts, which is the swing reviewer's area.
- **Stock options intraday,** except the top approximately 10 liquid names, and only for binary-gap risk. Spreads of 0.5–2% of premium erase the benefit.
- **LLM management calls for time-stop extension.** Let code do it; K5 will show whether management adds anything.
- **V chart twin for intraday decisions, until L shows IC.** It is ₹1.9k a month, about 27% of the LLM budget, and the evidence on vision models is weak.
- **Midday VWAP and range-fade tactics, and post-lunch breaks** on anything other than labelled trend days.

## 4. Top 5 recommendations

1. **Make "stocks in play" a hard gate.** Catalyst ≥ 60, or a gap ≥ 1 ATR with RVOL ≥ 3; F&O names only for shorts; zero-trade days allowed. Measure it first on the current E1/E2 paper results and the R book against the P2 placebo.
2. **Rebuild the friction gate on realistic numbers** (stop slippage from the paper model, brokerage per executed order, live spread). Raise the practical stop floor to about 70–80 bps and cap exits at 2 legs. As specified now, the 40–47 bps minimum stops need a 1.9R+ average winner just to break even.
3. **Test exits in the COE before freezing season 1.** Run the default vs a no-partial runner vs a time-stop-then-runner bracket. Change profit protection to block new risk only, so it no longer flattens runners whose stops are in profit.
4. **Trade 09:20–10:45 and stop trading lunch.** Pre-arm opening-drive pullbacks from a 09:12 pre-open call. Build E3 next and give negative-catalyst shorts equal weight.
5. **Narrow the LLM to catalysts and ranking.** Make CATALYST-mode IC L's pre-registered primary; send non-catalyst moments to R and Hk only; put Jev 1.13 first in triage. Fold cash scalping into intraday and drop OFI-driven index scalps and RS pairs.

**What the arena should test first (weeks 0–3, free, on existing paper and candle history):**
- R-book net R by opportunity class, by 15-minute entry bucket, by side × catalyst sign, and by exit bracket.
- Realised vs estimated friction.
- Missed-fill cost of resting entries.

Treat all of these as design inputs before the freeze, not as claims of edge.

**Sources**
- [SEBI press release PR 37/2024: intraday cash study (FY23)](https://www.sebi.gov.in/media-and-notifications/press-releases/jul-2024/sebi-study-finds-that-7-out-of-10-individual-intraday-traders-in-equity-cash-segment-make-losses_84948.html) (H); [Business Standard coverage](https://www.business-standard.com/amp/markets/news/7-in-10-intraday-traders-in-equity-cash-suffered-losses-in-fy23-sebi-study-124072400975_1.html)
- [SEBI FY25 F&O study coverage](https://www.business-standard.com/amp/markets/news/net-losses-of-traders-in-fo-widens-in-fy25-sebi-study-125070701221_1.html) (H)
- [Barber, Lee, Liu, Odean: day-trading skill](https://faculty.haas.berkeley.edu/odean/papers/day%20traders/Day%20Trading%20Skill%20110523.pdf); [Learning fast or slow (2018)](https://www.econ.puc-rio.br/uploads/adm/seminarios/Learning_fast_or_slow_180606.pdf) (M-H)
- Zarattini, Barbon, Aziz (2024), Stocks-in-Play ORB, SSRN 4729284, via [summary](https://www.letsdatascience.com/news/traders-adopt-orb-strategy-for-stocks-in-play-19394da2) and [critical replication](https://www.mql5.com/en/blogs/post/776235) (M)
- [Gao, Han, Li, Zhou: market intraday momentum](https://profiles.wustl.edu/en/publications/market-intraday-momentum/) (H, US)
- NSE intraday patterns: [Sampath & Gopalaswamy 2020](https://ideas.repec.org/a/sae/emffin/v19y2020i3p271-295.html); [IIMA WP](https://iima.ac.in/sites/default/files/rnpfiles/19191060542012-11-03.pdf); [Singh & Gangwar](https://mpra.ub.uni-muenchen.de/89689/) (M)
- [Linnainmaa (2010), JF](https://ideas.repec.org/a/bla/jfinan/v65y2010i4p1473-1506.html) (H)
- [Cont, Kukanov, Stoikov (2014)](https://arxiv.org/abs/1011.6402) (H)
- SEBI Jane Street interim order: [Oxford Business Law Blog](https://blogs.law.ox.ac.uk/oblb/blog-post/2025/07/jane-street-and-expiry-day-trap-unpacking-sebis-crackdown-algorithmic), [Moneylife](https://moneylife.in/article/jane-street-accused-of-massively-rigging-indias-derivatives-market-sebi-orders-ban-escrow-of-rs4843-crore-illegal-gains/77585.html) (H)
- [Lopez-Lira & Tang, arXiv 2304.07619](https://arxiv.org/abs/2304.07619v5) (M)
- India earnings drift: [Nottingham event study](https://eprints.nottingham.ac.uk/26569), [VUT PEAD study](https://journals.vutbr.cz/index.php/trends/article/view/541) (L-M)
- [Stock-derivative lot revision, Apr 2026 (FYERS)](https://fyers.in/notice-board/revision-in-lot-size-for-stock-derivative-contracts/) (L)
- [Alpha Arena season 1.5 (Forklog)](https://forklog.com/en/news/ai-model-grok-4-2-triumphs-in-trading-tournament) (L)

Design docs reviewed:
- /home/user/auto-trading/docs/design/trading-system-design.md (§5, §6, §7.1, §7.3, §8, §12)
- /home/user/auto-trading/docs/design/ai-trader.md
- /home/user/auto-trading/docs/research/02, 03, 04, 13, 17, 18

Friction script: [`scripts/intraday_friction.py`](scripts/intraday_friction.py)