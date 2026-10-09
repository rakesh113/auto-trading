# Red-team review: MCX Commodities Module (2026-10-08)

**Verdict:** The overall shape is sound: minis and micros only, an LLM that plans but cannot execute, a contract calendar, and gap budgeting. But the review found three things that break the design as written:
- The energy roll dates sit inside the pre-expiry margin window.
- The "2x margin headroom" rule fails against the February 2026 event the design itself cites.
- The positional gap budget is stacked on top of the owner's daily loss limit instead of being carved out of it.

There are also execution assumptions (market orders, SL-M, a separate watchdog host) that the April-2026 SEBI algo rules have overtaken. Most of the playbook is unlikely to earn money after costs at this account size.

---

## 1. Facts that are wrong, outdated or under-rated

| Design claim | Correction | Impact |
|---|---|---|
| All bullion is *staggered* delivery | Broker notices list **GOLDPETAL, GOLDGUINEA and GOLDTEN as compulsory delivery**, meaning every position still open at expiry is delivered. SILVERM, SILVERMIC and SILVER100 are staggered. The Petal/Ten tender window was cut from 5 days to 3 days before expiry in 2026, and cutoffs differ by broker (Fyers 21:00, Zerodha/Upstox 22:30). ([Fyers Jan-26](https://fyers.in/notice-board/precious-metals-expiry-30th-january-2026-compulsory-delivery-contracts/), [Zerodha Aug-26](https://zerodha.com/marketintel/bulletin/455368/commodities-precious-metals-expiry-august-2026), [Upstox Aug-26](https://upstox.com/announcements/updates/commodities-precious-metals-expiry-august-2026/)) | Store the settlement type and cutoff **per expiry, taken from each bulletin**, not per root. |
| Energy pre-expiry margin rise is (M); roll crude "~Oct 14" / "4 sessions before expiry" | **(H):** extra margin for CRUDEOIL/M and NG/mini steps from **5% up to 25% over the last 5 trading days** ([MCXCCL Sep-26 schedule](https://teamleaseregtech.com/updates/article/58827/mcx-notified-regarding-the-tender-pre-expiry-margin-schedule-for-the-month-of-september-2026/)) | Roll at **expiry minus 6 sessions**. CRUDEOILM Oct (expires Oct 19): roll by **Oct 12**. NG Oct (expires Oct 27): roll by about Oct 20, after checking the holiday calendar. |
| "MCX raised silver margin 15%→72%, gold 10%→30%" | The exchange add-on was **+7% silver and +3% gold** (Feb 5–6, withdrawn Feb 19). The 72% and 30% figures are ICICI Securities' *average total* requirement, inflated mainly by SPAN expanding with volatility. ([BusinessToday](https://www.businesstoday.in/amp/markets/stocks/story/mcx-shares-additional-margin-on-gold-silver-futures-withdrawn-what-icici-sec-says-516865-2026-02-19)) | Silver margin went up **4.8x** and gold 3x, so **2x headroom is not enough**. |
| Crude bands 4/6/9% (only crude band stated) | **Gold is 3% → 6% → 9%**, with a 15-minute cooling-off before 9% and no automatic widening beyond that. Silver locked at a **9% lower circuit on Feb 2, 2026.** ([Outlook](https://www.outlookmoney.com/invest/gold-10-contracts-know-all-about-new-trading-unit-launched-by-mcx), [ts2](https://ts2.tech/en/mcx-silver-price-hits-lower-circuit-again-gold-under-%E2%82%B91-45-lakh-as-budget-2026-ripples-through-markets/)) | A duty cut (about −7.8% mechanically) would hit gold's 6% band and then the cooling-off: a **locked market**, so stops cannot fill. |
| Execution uses MARKET / SL-M; watchdog on a separate host | The **SEBI retail-algo framework has been mandatory since Apr 1, 2026**: whitelisted static IP, daily 2FA, 10 orders/second cap, algo-ID tagging ([Fyers](https://fyers.in/notice-board/new-sebi-framework-for-retail-algo-trading-from-april-01-2026/)). Kite rejects MARKET and SL-M orders without `market_protection`, including on MCX, and IOC reportedly cannot be used for MCX algo orders ([Kite forum](https://kite.trade/forum/discussion/16232/exact-api-response-representation-for-sl-m-automatic-market-protection)). | The watchdog needs a whitelisted IP. Protected orders can **go unfilled in a gap**. Unattended start-up is impossible because a human must complete 2FA each morning. |
| Upstox square-off (M) | Confirmed: **40 minutes before close (22:50) in US summer time, 30 minutes before close (23:25) in winter** ([Upstox](https://upstox.com/help-center/252251/)). Zerodha's is 10 minutes before close. | Upgrade to (H). |
| Upstox expired MCX data "not available" | Upstox Plus has **expired-instrument APIs**: expiries, expired futures and options, and 1-minute expired candles. The documented examples are NSE_FO/BSE_FO; MCX coverage is unconfirmed, and the old "not available" forum replies predate these APIs ([docs](https://upstox.com/developer/api-documentation/backtesting)). `full_d30` (30-level depth): Plus plan only, 50-instrument cap, not on BSE, MCX unconfirmed. | Test both in week 1. This decides whether a data vendor is needed. |
| P2: CRUDEOIL option spreads within a 0.5% premium cap; silver via options | My estimates at about 45–50% implied volatility: an OTM CRUDEOIL (100 bbl) spread costs about **Rs 7–15k**, which is over the cap. An ITM leg devolves into a futures position needing about Rs 2.65L margin, above the whole commodity margin cap. Silver options exist only on SILVER/SILVERM, and one 1-month at-the-money SILVERM option costs about **Rs 50k+**. | **CRUDEOILM options only. No silver options.** |

**Checked and correct:**
- CTT unchanged at 0.01%; Budget 2026 raised only STT ([HDFC Sky](https://hdfcsky.com/news/union-budget-2026-impact-on-exchanges-with-recommendations)).
- MCX transaction charge 0.0021%; Upstox brokerage min(0.05%, Rs 20) ([Upstox](https://upstox.com/pricing/)).
- EIA crude report delayed to Thu Oct 15, 12:00 ET = **21:30 IST** ([Manifold](https://manifold.markets/lumi/will-the-eia-publish-the-level-of-t)).
- September CPI on Oct 14 ([Eco3min](https://eco3min.fr/en/next-us-cpi-release/)).
- UAE left OPEC effective May 1 ([ABC](https://abcnews.com/Business/wireStory/united-arab-emirates-leave-opec-effective-1-132450136?rand=1513)).
- Import duty 15% (10% basic customs duty + 5% agriculture cess) from May 13 ([Kitco](https://www.kitco.com/news/off-the-wire/2026-05-13/india-raises-gold-and-silver-tariffs-15-curb-imports-support-rupee)).
- Dec gold about 1,49,241 and Dec silver about 2,25,850 on Oct 6 ([AngelOne](https://www.angelone.in/news/commodities/check-gold-and-silver-prices-across-new-delhi-mumbai-and-chennai-on-october-6-2026)).
- Kite Connect: order API is free; live data and historical candles cost Rs 500/month.

**Minor fixes:**
- I found no evidence of a separate "GOLD10G" symbol. Drop it.
- SILVER100 has monthly expiries, staggered delivery and a 4/6/9% band ([Zerodha bulletin](https://zerodha.com/marketintel/bulletin/449496/introduction-of-silver-100-gram-futures-contracts-by-mcx)). Fill its tick value from the contract specification.

---

## 2. Strategies likely to lose after costs and slippage

- **ESB on CRUDEOILM, as specified:**
  - The minimum stop of 0.25% is about Rs 212 per lot. Costs plus 1 tick of slippage each way come to about Rs 82 per lot, which is **0.39R of friction** on a 1-lot order.
  - In this regime the 15-minute ATR is likely 0.5–0.9%, so a 0.25% stop sits inside normal noise.
  - The 18:00–21:30 window overlaps US data (18:00) and EIA (20:00), so many triggers will be event whipsaws.
  - The international-return filter adds nothing, because the MCX evening session is arbitraged to NYMEX within seconds, and it needs paid data.
- **EIA continuation and fade:**
  - Free consensus figures are noisy, and the API number is already in the price by the Wednesday 09:00 open.
  - The first-bar breakout in CL after EIA is crowded with high-frequency traders.
  - Expect 4–10 ticks of slippage on thin mini books.
  - The fade variant (|z| < 0.5, trading into a volatility spike) is close to a coin flip.
- **Global-lead catch-up and 09:00 gap fade:**
  - Broker feeds send periodic snapshots rather than every tick, and order round trips carry real latency, so a retail account has no realistic edge.
  - CME live data costs about 2% of capital per month.
  - **Drop both.**
- **Day-session VWAP reversion:**
  - GOLDPETAL round-trip cost is about 0.09% against target distances of 0.2–0.4%, so friction takes 25–45% of the target.
  - London open and China data turn quiet sessions into trend days.
- **1–10 minute scalping:** cost is 0.4–0.8 of one-minute volatility, there is no queue priority, and the 10 orders/second cap and market-protection rules apply. **Drop for MCX.**
- **Natural gas, any style:** realised volatility is 60–100%, pre-expiry margin reaches 25%, and settlement is on NYMEX's volatile final day. One NATGASMINI lot's daily range uses the whole per-trade risk.
- **Daily trend:** this is not a loser in itself, but **backtests will be flattered** by rupee depreciation (83 to 95.6) and the duty step from 6% to 15%, both one-off level shifts in favour of long bullion. Validate the shorts and a USD-denominated series separately.

---

## 3. Gaps and failure modes

1. **Loss arithmetic breaks the owner's cap.**
   - A positional gap of Rs 15k on top of the shared Rs 25k daily limit allows Rs 37–40k of loss on a bad day, more than 3%.
   - Carve the gap reserve *out of* the daily limit: with positional positions open, intraday budget = 25k − gap reserve.
2. **Locked-limit days.**
   - Stops do not fill while the band is locked, and international markets keep trading, so a second gap follows the next day.
   - Budget positional risk at the full band ladder.
   - A 9% lock on one SILVERMIC lot is about Rs 20k, twice the commodity daily budget. **Keep intraday silver to 1 lot.**
3. **Margin stress.**
   - Replace 2x headroom with stress multiples: silver 5x, gold 3x, energy 2x plus the 25% pre-expiry add-on.
   - Brokers can add margin on top of the exchange. A shortfall leads to the broker's risk desk squaring off at the worst price, plus a margin-shortfall penalty.
4. **Stop re-arm.**
   - The 08:45–08:59 special session only allows cancellations.
   - If price opens through the stop, an SL-limit order may never fill. The rule must be: "if price is through the stop at 09:00, send a protected marketable exit."
   - Test MCX GTT through the API using a single GOLDPETAL lot.
5. **Calendar drift.**
   - EIA holiday shifts recur (Columbus Day this week, then Veterans Day and Thanksgiving). Ingest EIA's own schedule rather than computing dates.
   - The MCX winter timing switch on **Nov 2** falls the day after the **Nov 1 OPEC+** Sunday meeting, so expect a Monday gap and a timing change on the same day.
6. **Paper-broker realism.** The paper broker must simulate band locks, pre-expiry margin, tender blocks, broker square-off and its penalty, market-protection rejections, and the 10 orders/second throttle.
7. **Go-live gates are statistically weak.**
   - ESB will not reach 100 trades in 60 sessions.
   - "20 trend trades in 6 months" proves nothing.
   - Validate the daily system on 10+ years of bhavcopy data and intraday systems on vendor 1-minute data. Use paper trading to prove *operations*, not edge.

---

## 4. What to build, defer or drop, and sizes

**Phase 1 (paper, now):**
0. **The commodity operations layer comes first.** It is not optional: contract calendar, roll/tender/pre-expiry rules, event blackouts, margin stress monitor, locked-limit handling.
1. **Daily trend, positional:**
   - GOLDPETAL up to **6 lots in a single order**, plus **1 CRUDEOILM**.
   - No entries on Fridays or within 6 sessions of expiry.
   - SILVER100, 2–3 lots, only if the spread is 2 ticks or less and open interest is adequate.
2. **ESB on CRUDEOILM, revised:**
   - **3–5 lots per order**, risk ≤ Rs 3k, stop **≥ 0.5%**.
   - Window starts at max(18:15, event + 15 min); skip Wednesdays; 1 trade per day.
   - Drop the international filter.
3. **EIA protocol as risk control only:** flatten and black out from day 1; the event trades stay paper-only.

**Phase 2 (after evidence):**
- SILVERMIC ESB at 1 lot.
- EIA continuation, only if more than 40 events show net edge.
- CRUDEOILM long puts as a hedge on positional crude.

**Drop:**
- Global-lead and 09:00 gap trades.
- EIA fade.
- MCX scalping.
- Positional NG and NG options.
- Options on CRUDEOIL, NATURALGAS, SILVER and SILVERM.
- Base metals, GOLDGUINEA, NICKEL, GOLDM, and every standard-size lot.

| Contract | Intraday | Positional |
|---|---|---|
| CRUDEOILM | 3–5 lots per order (cost per lot falls about 60% versus 1 lot) | 1 lot |
| SILVERMIC | 1 lot (because of the 9% lock risk) | 0 |
| SILVER100 | — | 2–3 lots (liquidity-gated) |
| GOLDPETAL | none (costs too high) | ≤ 6 lots per order (≤ 8 if no duty-cut risk) |
| NATGASMINI | Phase 2 at most, 1 lot | 0 |

**To test in week 1:**
- Upstox expired-data API and `full_d30` coverage on MCX.
- Kite MCX GTT through the API.
- Static-IP setup for the watchdog.
- Broker margin uplifts on the minis.
- SILVER100 spread and open interest.