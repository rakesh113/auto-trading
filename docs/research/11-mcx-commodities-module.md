# MCX Commodities Module: Design Report (as of 2026-10-08)

Confidence tags: **(H)** high, **(M)** medium, **(L)** low. Rupee prices are illustrative and taken from early-October 2026 levels. The feature engine must recompute every number from live quotes and ATR.

Reference prices used below: gold ≈ Rs 1,49,000/10g (Dec contract), silver ≈ Rs 2,26,000/kg, crude ≈ Rs 8,500/bbl (WTI about $88–89), natural gas ≈ Rs 290/mmBtu, USDINR ≈ 95.6, copper ≈ Rs 1,385/kg, zinc ≈ Rs 420/kg, aluminium ≈ Rs 351/kg. Sources: [AngelOne Oct-6](https://www.angelone.in/news/commodities/check-gold-and-silver-prices-across-new-delhi-mumbai-and-chennai-on-october-6-2026), [PTI crude Sep-18](https://telanganatoday.com/crude-oil-prices-fall-rs-168-to-rs-9590-per-barrel-on-mcx), [Kalshi WTI](https://kalshi.com/markets/kxwtiw/wti-oil-weekly-range/kxwtiw-26oct0914), [rupee 95.74](https://hdfcsky.com/news/rupee-falls-3-paise-to-close-at-95-74-against-us-dollar), [NG Oct-27 contract](https://choiceindia.com/commodity/mcx-natural-gas-price).

**Regime context (M):** Energy volatility is high in 2026. Iran and Hormuz tensions pushed WTI above $100 in mid-September, and crude volatility hit a 4-year high in March. The UAE left OPEC in May. A 7-country OPEC+ group now decides output monthly, and its next meeting is Sunday, Nov 1 ([Bernama](https://bernama.com/en/world/news.php?id=2615376), [OPEC PR](https://www.opec.org/pr-detail/1835613-6-september-2026.html)). The gold/silver import duty was raised from 6% to 15% on May 13, 2026, and a cut back toward 6% is reportedly under consideration ([GTRI/AngelOne](https://www.angelone.in/news/economy/new-import-duties-could-drive-demand-for-dubai-gold-says-gtri), [BusinessToday Aug-31](https://www.businesstoday.in/latest/economy/story/government-may-cut-gold-silver-import-duties-as-higher-rates-fuel-grey-market-report-552339-2026-08-31)).

---

## 0. Executive recommendations

1. **Trade only minis and micros:** CRUDEOILM, NATGASMINI, SILVERMIC, GOLDPETAL / GOLDTEN. ZINCMINI and ALUMINI are optional later. Do not trade the standard contracts or the Gold Mini / Silver Mini lots. At Rs 10L, one day's range on a Silver Mini lot (Rs 28–45k) is bigger than the whole daily loss limit.
2. **Commodity sleeve limits:** margin cap Rs 2.5L, daily loss sub-budget Rs 10k (1%), per-trade risk Rs 2.5–4k. Positional gap-risk cap is 1.5% across the book.
3. **First strategies:** (A) Evening Session Breakout on CRUDEOILM/SILVERMIC, (B) EIA Event Protocol, (C) Daily Trend positional on small lots. Build the global-lead and fair-value feature from day 1 as a measured research signal, not a strategy yet.
4. **Positional holding is feasible only at small size** in the current volatility regime: about 1 CRUDEOILM lot plus about 8 GOLDPETAL lots. Silver positional only through options or the Silver 100 contract.
5. **Scalping (1–10 min)** is viable only on multi-lot CRUDEOILM, SILVERMIC and NATGASMINI in the evening session. Gold Petal and Gold Ten fail on costs. Defer it to phase 3.

---

## 1. Contract universe

| Root | Lot / quote | Tick → Rs per tick per lot | Notional | Est. margin | Est. daily range per lot | Settlement / expiry | Fit for Rs 10L |
|---|---|---|---|---|---|---|---|
| CRUDEOIL | 100 bbl, Rs/bbl | Re1 → 100 | 8.5L | ~31% ≈ 2.65L | 21–34k | Cash; ~19–20th monthly | **Avoid** |
| **CRUDEOILM** | 10 bbl | Re1 → 10 | 85k | ≈ 26k | 2.1–3.4k | Cash; same expiry | **Core** |
| NATURALGAS | 1,250 mmBtu | 0.10 → 125 | 3.6L | 15–30% (L) | 14–22k | Cash (NYMEX HH × RBI rate); ~25–27th | Avoid |
| **NATGASMINI** | 250 mmBtu | 0.10 → 25 | 72.5k | 7–22k (L) | 2.9–4.4k | Cash | **Core (half size)** |
| GOLD | 1 kg, Rs/10g | Re1 → 100 | 1.49 Cr | ≈ 14.1L | 1.5–2.7L | Staggered delivery; 5th of even months | Avoid |
| GOLDM | 100 g, Rs/10g | Re1 → 10 | 14.9L | ≈ 1.4L | 15–27k | Staggered; 5th monthly | Avoid (too large) |
| **GOLDTEN** (and GOLD10G) | 10 g | Re1 → 1 | 1.49L | ≈ 14.1k | 1.5–2.7k | Staggered; last day of month | **Core (positional)** |
| GOLDGUINEA | 8 g | Re1 → 1 | 1.19L | ≈ 11k | 1.2–2.1k | Staggered; month-end | Thin, skip |
| **GOLDPETAL** | 1 g | Re1 → 1 | 14.9k | ≈ 1.5k | 150–270 | Staggered; month-end | **Core (fine sizing)** |
| SILVER | 30 kg, Rs/kg | Re1 → 30 | 67.8L | ≈ 8.6L | 1.7–2.7L | Staggered; 5th Mar/May/Jul/Sep/Dec | Avoid |
| SILVERM | 5 kg | Re1 → 5 | 11.3L | ≈ 1.52L | 28–45k | Staggered; end Feb/Apr/Jun/Aug/Nov | **Avoid** |
| **SILVERMIC** | 1 kg | Re1 → 1 | 2.26L | ≈ 30k | 5.6–9k | Same as SILVERM | **Core (intraday)** |
| SILVER100 | 100 g (since 2026-06-01) | — | 22.6k | ~3k | 560–900 | — | Watch liquidity |
| COPPER | 2,500 kg | 0.05 → 125 | 34.6L | ~3.5–4L (L) | 52–69k | Staggered; month-end | Avoid |
| ZINC / ALUMINIUM / LEAD | 5 MT | 0.05 → 250 | 9–21L | — | — | Staggered | Avoid |
| ZINCMINI / ALUMINI / LEADMINI | 1 MT | 0.05 → 50 | 4.2L / 3.5L / ~1.9L | ~10–12% (L) | 6–8k / 4–5k / ~2k | Staggered | Satellite, later |
| NICKEL | **250 kg** (relaunched 2025) | 0.10 → 25 | ~3.7L | — | ~7.5k | Staggered | Skip (illiquid) |

Sources: crude mini specs (H) [Dhan](https://dhan.co/commodity/crude-oil-mini-futures-summary/); bullion lots (H) [Varsity](https://zerodha.com/varsity/chapter/gold-part-1/), [Upstox silver](https://upstox.com/learning-center/commodity/what-is-silver-trading-on-mcx/article-1869/); Silver 100 [bulletin](https://zerodha.com/marketintel/bulletin/449496/introduction-of-silver-100-gram-futures-contracts-by-mcx); nickel 250 kg (M) [The Week](https://www.theweek.in/wire-updates/business/2025/08/18/dcm47-biz-agri-mcx.html); base-metal minis [AngelOne](https://www.angelone.in/news/market-updates/mcx-launches-3-new-mini-contracts-of-aluminium-lead-and-zinc); margins (M, early-Sep 2026) [Sahi table](https://www.sahi.com/blogs/commodity-margin-lot-size-2026); NG settlement at the Due Date Rate (M) [MCX DDR](https://teamleaseregtech.com/updates/article/57273/mcx-due-date-rates-notified-for-natural-gas-futures-contracts-expired-on-june-25-2026/). The daily-range column is my own estimate (L–M) from 2026 realised volatility.

**Margin shock risk (H):** In February 2026, MCX raised average margins on silver from 15% to 72% and on gold from 10% to 30% ([BusinessToday](https://www.businesstoday.in/amp/markets/stocks/story/mcx-shares-additional-margin-on-gold-silver-futures-withdrawn-what-icici-sec-says-516865-2026-02-19)). The system must keep at least 2x margin headroom on overnight positions.

**Tender and delivery risk (H):** All bullion and base metals are *staggered delivery*. During the tender window, the exchange can mark open positions for delivery, and that obligation survives a later exit. Zerodha squares off at 22:30 on the day before tender starts and blocks fresh entries. Recent cutoffs:
- GOLD/GOLDM, 5-Oct expiry: Sep 29.
- GOLDPETAL/GOLDTEN/GUINEA, 30-Sep expiry: Sep 25.
- SILVERM/SILVERMIC, 30-Apr expiry: Apr 23.

Sources: [Zerodha Sep-2026 bulletin](https://zerodha.com/marketintel/bulletin/458280/commodities-precious-metals-expiry-september-2026), [Zerodha holding FAQ](https://support.zerodha.com/category/trading-and-markets/trading-faqs/commoditytrading/articles/how-long-can-i-hold-mcx-contracts).

**Rule:** for any physically settled contract, `exit_or_roll_by = broker_cutoff − 1 trading day`. Crude and NG are cash-settled and can be held to expiry. Even so, roll them 3–5 sessions early, because liquidity migrates and pre-expiry margins rise (M).

**Current calendar (approximate):**
- CRUDEOILM Oct expires ~Oct 19–20, so roll to Nov around Oct 14.
- NG Oct expires Oct 27.
- GOLD and SILVER Dec contracts expire Dec 4.
- SILVERMIC next expiry is Nov 30.

**MCX options on futures:**
- Available on CRUDEOIL, CRUDEOILM and NATGASMINI (both since April 2024), NATURALGAS, GOLD, GOLDM, SILVER and SILVERM.
- European style. Crude options expire 2 business days before the future. In-the-money options *devolve into futures*, which needs 50% of futures margin on T−1 and 100% on T. Sources: [crude mini options](https://zerodha.com/marketintel/bulletin/376789/mcx-launches-crude-oil-mini-options-contracts-with-crude-oil-mini-10-barrels-futures-as-underlying), [devolvement](https://support.zerodha.com/category/trading-and-markets/trading-faqs/commoditytrading/articles/devolvement-of-commodity-options).
- Liquidity (M): CRUDEOIL and NATURALGAS options are the deepest. Bullion is about one-third of options activity ([HDFC Sky](https://hdfcsky.com/news/mcx-scaling-new-heights-maintain-buy)). Mini options are thinner.
- Zerodha allows only current-month commodity options (two months for energy). MIS is allowed only on energy options ([Zerodha](https://support.zerodha.com/category/trading-and-markets/trading-faqs/general/articles/how-can-i-trade-commodity-options-in-zerodha)).
- **Policy:** buy options only, as hedges or defined-risk positions. No short options at this capital.

---

## 2. Sessions and timing (IST; S = US daylight time until Oct 30, W = from Nov 2)

**MCX non-agri hours (H):** 09:00–23:30 (S) and 09:00–23:55 (W), with W starting Mon Nov 2, 2026 ([Zerodha](https://zerodha.com/marketintel/bulletin/459705/revision-in-commodity-market-trading-hours-from-november-02-2026)).

**Broker intraday auto square-off:**
- Zerodha: 10 minutes before close, i.e. 23:20 (S) / 23:45 (W) (H) ([Zerodha](https://support.zerodha.com/category/trading-and-markets/trading-faqs/market-sessions/articles/intraday-auto-square-off-timings)).
- Upstox: about 22:50 (S) / 23:25 (W). Sources conflict, so this is (M) ([Upstox help](https://upstox.com/help-center/252251/)).
- **System time-stop = earliest broker cutoff − 10 min:** 22:40 (S) / 23:15 (W).

| Event (source timezone) | IST, S | IST, W | Effect on MCX |
|---|---|---|---|
| China NBS/Caixin PMIs, CPI (09:30–09:45 CST) | 07:00–07:15 | same | Base-metal gap at 09:00 |
| SHFE day / night session | 06:30–12:30 / 18:30–22:30 | same | Copper/zinc lead |
| London open; LME ring 11:40–17:00 London | 12:30; 16:10–21:30 | 13:30; 17:10–22:30 (UK changes Oct 25) | Base metals |
| US CPI / NFP / GDP (08:30 ET) | 18:00 | 19:00 | Tier-1 for bullion and crude |
| NYMEX/COMEX day open; NYSE open | ~17:50; 19:00 | ~18:50; 20:00 | Liquidity peak starts |
| EIA crude (Wed 10:30 ET) | 20:00 | 21:00 | Tier-1 crude |
| EIA NG storage (Thu 10:30 ET) | 20:00 | 21:00 | Tier-1 NG |
| API inventories (Tue 16:30 ET) | Wed 02:00 | Wed 03:00 | MCX closed, so gap at Wed open |
| Baker Hughes (Fri 13:00 ET) | 22:30 | 23:30 | Minor |
| FOMC (14:00 ET) | 23:30 (at close) | 00:30 | Overnight gap event |
| Globex weekly reopen (Sun 18:00 ET) | Mon 03:30 | Mon 04:30 | Weekend gap reconciled at MCX open |
| OPEC+ (usually first Sunday of month) | — | — | Monday gap |

Event timing sources (H): [EIA schedule](https://www.eia.gov/petroleum/supply/weekly/schedule.php), [Fed Oct 2026](https://www.federalreserve.gov/newsevents/2026-october.htm), [BLS Oct 2026](https://www.bls.gov/schedule/2026/10_sched_list.htm).

**Near-term dates:**
- Sep CPI: Oct 14, 18:00 IST.
- EIA crude: Thu Oct 15, 21:30 IST (shifted by the Columbus Day holiday).
- FOMC: Oct 28, 23:30 IST, which falls at the close.
- OPEC+: Nov 1.
- NFP: Nov 6, 19:00 IST.

**India-specific events:**
- RBI MPC at 10:00.
- NSE USDINR futures stop at 17:00, so the evening session needs an offshore USD/INR quote.
- Import-duty notifications are unscheduled. A cut from 15% to 6% would mechanically drop MCX bullion by about 7.8% (1.06/1.15 − 1).
- MCX holiday calendar: some holidays have an evening-only session.

**Liquidity profile (L, measure in week 1):**
- 09:00–12:00: thin, 2–3x normal spreads, gap reconciliation.
- 12:00–17:00: moderate.
- 17:30–23:00: roughly 60–70% of energy and bullion volume.
- Last 30 minutes: thinning, plus broker square-off flows.
- The event calendar must store events in their *source timezone* and convert with zoneinfo. The UK and US daylight-time changes fall a week apart (Oct 25 and Nov 1).

---

## 3. Price drivers and the global-lead / fair-value feature

**Fair-value formulas (tune k, duty and carry by regression; do not hardcode):**
- `FV_crude = CL_matched × USDINR`. MCX settles against NYMEX WTI × the RBI rate (M) ([Sahi](https://www.sahi.com/blogs/crude-oil-trading-on-mcx-beginners-guide-2026)). Map each MCX month to the NYMEX contract that settles around the same date; the MCX Oct contract maps to NYMEX Nov CL.
- `FV_ng = NG_matched × USDINR`.
- `FV_gold(10g) = XAUUSD × USDINR × 0.321507 × (1 + duty) + carry`.
- `FV_silver(kg) = XAGUSD × USDINR × 32.1507 × (1 + duty) + carry`.
- `FV_cu(kg) = LME_3M / 1000 × USDINR × (1 + duty_bm) + premium`.
- Sanity check with current numbers: $4,150 × 95.6 × 0.3215 × 1.15 ≈ Rs 1,46,700, against MCX Dec gold at about 1,49,200. The gap is about 1.7% of carry plus premium, so the model is consistent with 15% duty.

**Signal construction:**
- `basis = EWMA(MCX − FV, 60m)`.
- `resid_z = (MCX − FV − basis) / robust_σ(1 day)`.
- A sudden basis jump above 3% with no move in international prices should be classified as a **duty or policy shock**. The LLM verifies against the news.

**Data sources (broker feeds do not carry COMEX/NYMEX):**

| Option | Latency | Cost | Use |
|---|---|---|---|
| Yahoo Finance (CL=F, GC=F, SI=F, NG=F, HG=F) | ~10–15 min delayed | Free (unofficial) | Regime and end-of-day only |
| Spot XAU/XAG and USD/INR from forex APIs (Twelve Data/Finnhub-class) | Real-time | ~$0–80/mo (L) | Best cheap bullion lead |
| CFD feeds (e.g. OANDA WTICO/BCO/NATGAS) | Real-time | Free demo | India eligibility unconfirmed (L) ([OANDA](https://help.oanda.com/bvi/en/faqs/eligible-ogm-countries-bvi.htm)) |
| Databento CME live (NYMEX+COMEX) | Real-time, exchange grade | $199/mo plan plus CME non-pro fees of ~$1.55 (top of book) to $12.10 (depth) per exchange (M) ([Databento](https://databento.com/blog/updates-to-subscription-pricing), [CME fees](https://www.cmegroup.com/market-data/files/june-2026-market-data-fee-list.pdf)) | About 2% of capital per month, too expensive at Rs 10L |
| Databento *historical* CME 1-minute data | — | Usage-based, cheap | **Lead-lag study before paying for live** |

**Degradation modes:**
- **Mode A**, real-time feed with data age under 3 s: all setups enabled.
- **Mode B**, delayed feed only: the global-lead and open-gap setups are disabled; international data is used for regime and positional decisions only.
- **Mode C**, no feed: MCX-only operation.
- The evening USDINR leg uses the offshore quote. Its error is ±0.1–0.2%, which is small next to crude moves (M).

---

## 4. Intraday playbook

**A. Evening Session Breakout (ESB):** CRUDEOILM, SILVERMIC
- **Context:** no tier-1 event in the next 15 minutes. Pre-US range width between 0.4 and 1.2 × ATR14(daily).
- **Range:** high and low from 16:00–17:45 (S) / 17:00–18:45 (W).
- **Trigger:** a 5-minute close beyond the range by more than 0.1 × ATR(5m), between 18:00–21:30 (S) / 19:00–22:30 (W).
  - Volume must exceed 1.5 × the 20-day median for the same time slot.
  - In Mode A, the international 15-minute return must have the same sign.
- **Stop:** the tighter of the range midpoint and 1.0 × ATR(15m), with a minimum distance of 0.25%.
- **Target:** take 50% off at 1.5R, then trail with a 2 × ATR(5m) chandelier.
- **Time stop:** exit if not at +0.5R within 60 minutes. Hard exit at 22:40 (S) / 23:15 (W).
- **Failure modes:** fake breaks while positions are set before data releases, and simultaneous crude and silver losses on a USD shock (cluster cap applies).

**B. EIA Event Protocol:** CRUDEOILM on Wednesday, NATGASMINI on Thursday
- **Before the release:** at T−10 minutes, flatten intraday positions in that commodity and cancel pending entries. No entries from T−10 to T+5.
- **Surprise score:** z = (actual − consensus) / σ of historical surprises. Consensus and the API figure come from the LLM; the arithmetic is done in code.
- **Continuation trade:**
  - Conditions: |z| ≥ 1, the first 5-minute bar is at least 1.2 × its 20-day average range, and that bar closes in the outer 30% of its range in the surprise direction.
  - Entry: a break of that bar's extreme, between T+5 and T+30.
  - Stop: the opposite end of the bar. Target: 2R. Time stop: T+60.
- **Fade trade:**
  - Conditions: |z| < 0.5, a first bar of at least 1.5 × average range, and price re-crossing the bar's midpoint.
  - Target: the pre-event price. Stop: beyond the bar's extreme. Time stop: T+45.
- **If consensus is missing:** half size, price-only rules.
- **Failure modes:** geopolitical headlines swamping the inventory number, and daily price limit bands (crude 4% → 6% → 9%).

**C. Global-lead catch-up and 09:00 gap reconciliation** (research first; Mode A only)
- **Catch-up entry:** |resid_z| ≥ 2.5 *and* the international price moved at least 0.3% in 3 minutes while MCX moved less than one-third of that. Trade toward FV.
  - Exit when z ≤ 0.5. Stop when z ≥ 4 or the loss reaches 0.3%. Time stop 10 minutes.
- **09:00 gap variant:** fade a first-minute deviation from Globex-implied FV, 1 lot, 30-minute time stop.
- **Honest assessment:** arbitrage desks keep the evening session aligned within seconds. Any edge is most likely in 09:00–12:00 and in fast moves.
- **Promote to a strategy only if** the lead-lag study shows a median lag above 2 s and a residual half-life above 30 s.

**D. Day-session range reversion** (10:00–16:30): GOLDTEN/PETAL, SILVERMIC, CRUDEOILM
- **Context:** ADX14(15m) < 18, overnight range below 0.6 × ATR, and no tier-1 event before 17:30.
- **Trigger:** a touch of VWAP ± 2σ (VWAP anchored at 09:00) followed by a 5-minute rejection bar.
- **Stop:** band extreme + 0.3 × ATR(15m). **Target:** VWAP. Time stop 45 minutes. Flatten by 17:15 (S).
- **Failure modes:** a trend day driven by China or geopolitics, and slippage in thin books.

---

## 5. Positional (multi-day) playbook

**P1. Daily trend following**

Sizing formula:
```
lots = floor(min(0.5–0.75%·C / (2.5·ATR20·mult),   # stop risk
                 0.75%·C / (3·ATR20·mult),          # gap risk
                 margin_cap / (margin_per_lot·2)))  # 2x headroom
```

- **Entry:** daily close above the 20-day Donchian high, EMA50 slope positive and ADX14 > 20. Shorts are symmetric.
- **Exits:** initial stop at 2.5 × ATR20. Then a 3 × ATR chandelier, or a close below the 10-day Donchian low.
- **Sizing at today's ATR:**

| Instrument | ATR20 per lot | 2.5 × ATR (stop risk) | 3 × ATR (gap risk) | Max size |
|---|---|---|---|---|
| CRUDEOILM | ~2,500 | 6,250 | 7,500 | **1 lot** (with 0.75% risk) |
| GOLDPETAL | ~224 | — | — | **8 lots** (≈1.19L notional) |
| GOLDTEN | ~2,235 | 5,590 | — | **1 lot** |
| SILVERMIC | ~6,800 | 17k (1.7%) | — | **0 lots**; use options or SILVER100 |

- **Duty-cut overlay:** while the LLM's `duty_change_risk` flag is high, size bullion longs for an 8% gap. That means at most about 6 GOLDPETAL lots.

**P2. Defined-risk options for geopolitical or event regimes**
- Buy CRUDEOIL OTM call or put spreads, 2–4 weeks out, with premium capped at 0.5% of capital.
- Or hedge a long CRUDEOILM with a long OTM put on CRUDEOILM options.
- Close in-the-money legs before devolvement.

**Weekend and gap rules:**
- No new positional entries on Friday evening.
- Friday 22:30 review: shrink holdings so the total 3 × ATR exposure is at most 1.5%.
- If `geo_risk = high`, positional crude must be options-hedged or flat.

**Overnight stops:**
- Exchange SL orders are day orders and are cancelled at close.
- MCX GTT exists on Kite web since February 2026, but **API support for commodity GTT is unconfirmed**. A December 2025 forum reply said "not available" (M) ([Z-Connect](https://zerodha.com/z-connect/business-updates/updates-for-commodity-traders), [Kite forum](https://kite.trade/forum/discussion/15670/gtt-orders-for-commodity-options-goldm-using-api)).
- Design: a **stop re-arm service** places SL-limit orders at 09:00:05 every day, backed by a software watchdog. Accept that gaps cannot be stopped out; sizing is the only protection.

**Carry and roll:**
- Gold and silver futures are in contango of roughly 0.4–0.5% per month (M).
- Generate signals on a back-adjusted series and book P&L on real contracts.
- Roll on schedule: crude about 4 sessions before expiry; staggered-delivery contracts at tender − 2 sessions.

---

## 6. Risk and allocation inside the shared Rs 10L book

```yaml
mcx:
  margin_cap: 250000             # incl. positional; keep 2x headroom overnight
  daily_loss_subbudget: 10000    # 1.0%
  per_trade_risk: {intraday: 3000, positional: 5000-7500, scalp: 2000}
  max_concurrent: 3              # max 2 per cluster
  max_losers_per_day: 3
  positional_gap_cap: 15000      # sum of 3xATR, correlation-adjusted
  clusters:
    precious: [GOLDPETAL, GOLDTEN, SILVERMIC]   # gold-silver corr ~0.7-0.85: same-direction risks summed
    energy:   [CRUDEOILM, NATGASMINI, eq:BPCL, eq:HPCL, eq:IOC, eq:ONGC]
    base:     [ZINCMINI, ALUMINI, eq:HINDALCO, eq:VEDL, eq:HINDZINC]
  time_stop: {S: "22:40", W: "23:15"}
  event_blackout_min: {tier1: [-10, +5]}
```

**Correlation inputs:**
- Crude and NG correlation is low (about 0.1–0.3) (L).
- Crude correlates *negatively* with Nifty and the oil marketing companies during supply shocks. The global risk manager uses a rolling 60-day correlation matrix across both modules.
- A long crude position plus a short BPCL position counts as the *same* bet.

**Risk-day definition:** the IST calendar date, from 09:00 to the MCX close.
- A single global limit of Rs 25k covers realised plus mark-to-market across equity and commodity.
- Evening commodity budget = `min(10k, 25k − equity_loss_so_far − 2.5k buffer)`.
- Equity profits never *increase* the commodity budget.
- Positional mark-to-market counts toward the daily total. When the limit hits, the response is to block new entries; positional positions are not force-closed, because their gap risk was budgeted in advance.
- Weekly limit −5% and monthly limit −8%, each followed by a halt and review.

---

## 7. Costs (Zerodha; Upstox is identical except brokerage)

**Rates:**

| Charge | Rate |
|---|---|
| Brokerage, futures | Zerodha: min(0.03%, Rs 20) per order. Upstox: min(0.05%, Rs 20) |
| Exchange transaction charge | 0.0021% (futures), 0.0418% (options) |
| CTT | 0.01% on futures sales, 0.05% on option-premium sales. Budget 2026 raised STT only, not CTT (M) |
| Stamp duty | 0.002% (futures, buy side) |
| SEBI fee | Rs 10 per crore |
| GST | 18% on brokerage + exchange charge + SEBI fee |

Sources: [Zerodha charges](https://zerodha.com/charges), [MCX fees](https://www.angelone.in/news/share-market/mcx-fo-transaction-fee-update-post-sebi-directive), [NSE STT circular](https://nsearchives.nseindia.com/content/circulars/FATAX73524.pdf).

**Round trip and break-even** (excluding spread; σ1m is the estimated one-minute price volatility):

| Contract | Notional | Round trip | Break-even (ticks) | Cost incl. 1-tick spread / σ1m |
|---|---|---|---|---|
| CRUDEOILM, 1 lot | 85k | Rs 62 | 6.2 | 0.84 |
| CRUDEOILM, 5 lots in one order | 4.25L | Rs 120 (Rs 24 per lot) | 2.4 | 0.40 |
| NATGASMINI | 72.5k | Rs 60 | 2.4 | 0.77 |
| GOLDPETAL, 1 lot | 14.9k | Rs 13.1 (Upstox Rs 20) | 13 (20) | ~2.0, so **no scalping** |
| GOLDTEN / 10 PETAL in one order | 1.49L | Rs 73 | 73 (7.3 per petal lot) | ~1.1 |
| GOLDM | 14.9L | Rs 303 | 30 | 0.4 |
| SILVERMIC | 2.26L | Rs 86 | 86 | 0.42 |
| SILVERM | 11.3L | Rs 242 | 48 | — |

**Key insight:** the flat Rs 20 brokerage dominates small orders. Always batch lots into a single order.

**Auto square-off penalties:** Zerodha charges Rs 50 + GST. Upstox charges Rs 88.5, or Rs 59 on Plus.

---

## 8. Broker and API support

| Item | Upstox | Zerodha Kite Connect |
|---|---|---|
| MCX trading and streaming | Yes, V3 protobuf feed (H) ([docs](https://upstox.com/developer/api-documentation/v3/get-market-data-feed)) | Yes (H) |
| Depth via API | Full mode 5 levels (M). `full_d30` is Plus-only, max 50 symbols, **MCX coverage unconfirmed** (L) ([Plus](https://upstox.com/plus/)) | 5 levels (M) |
| Order types | LIMIT, MARKET, SL, SL-M. SL-M on MCX *futures* not reported blocked (M) | Same. SL-M blocked for options; MARKET blocked for commodity options (M) |
| Products | I (intraday) / D (carry) | MIS / NRML. MIS on options only for energy |
| Auto square-off | ~22:50 / 23:25 (M) | 23:20 / 23:45 (H) |
| GTT | API in beta, MCX coverage unknown (L) | MCX GTT on web only (M) |
| Expired MCX data | **Not available**, per Upstox staff (M) ([forum](https://community.upstox.com/t/expired-f-o-data-for-mcx/14004)) | Day candles only, via `continuous=1`, from about 2011. No expired intraday data (M) ([forum](https://kite.trade/forum/discussion/comment/41395/)) |

**Product recommendation:**
- On Zerodha, use MIS, so the 23:20 broker square-off acts as a safety net.
- On Upstox, use D (carry) with system time-stops, to avoid losing 22:50–23:30 to the broker's square-off.
- Either way, require a dead-man watchdog on a separate host. If the main process heartbeat is missing for more than 60 s, it flattens positions.

**Instrument master handling:**
- Snapshot it daily at 08:30 and keep the snapshots, because expired tokens disappear.
- Maintain a `contract_calendar` table: `root, expiry, settlement, tender_start, broker_cutoff, roll_date, dpl`. The LLM parses MCX circulars and broker bulletins into it; code validates.
- Resolve the active contract with `front until min(expiry − N, next_OI > front_OI, tender − 2)`.

---

## 9. Backtesting

**Daily data:** MCX bhavcopy (all contracts, including expired) plus Kite `continuous=1`. Build your own series:
- Ratio back-adjustment for signals.
- Real contracts with explicit roll trades for P&L.
- Roll dates identical to live.

**Intraday data:**
- **Start recording now:** ticks, 1-minute bars and L5 depth for the front and next month of each core root.
- Buy 2–3 years of 1-minute data from an MCX-authorised vendor (TrueData / Global Datafeeds; offering unverified) (L).
- Upstox V3 candles cover live contracts since listing only.

**International data:** Databento historical CME 1-minute data, for the FV and lead-lag study.

**Slippage model by time bucket** (initial values, recalibrate from recorded depth):

| Contract | 09:00–12:00 | 17:30–23:00 | Event windows |
|---|---|---|---|
| CRUDEOILM | 2 ticks | 1 tick | 4–10 ticks |
| NATGASMINI | — | 1–2 ticks | 4–8 ticks at EIA |
| SILVERMIC | Rs 10–20 | — | — |
| GOLDPETAL | Rs 2–5 | — | — |

- Add a fill penalty when the daily price limit band is touched.

---

## 10. LLM vs code

**LLM, off the hot path:**
- Maintain the event calendar (EIA, BLS, Fed, OPEC+, China NBS, RBI, MCX circulars, holidays, tender cutoffs).
- Fetch consensus figures and interpret the API and EIA releases.
- Set regime labels: `geo_risk`, `opec_stance`, `fed_tone`, `duty_change_risk`, `usd_regime`.
- Write pre-session briefs at 08:45 and 16:45.
- Produce positional JSON plans:

```json
{"module":"mcx","root":"CRUDEOILM","contract_rule":"front_until_roll","side":"long",
 "thesis":"...","regime":{"geo_risk":"high","blackouts":["EIA_WPSR@2026-10-15T16:00Z"]},
 "trigger":{"type":"daily_close_above","level":8620},
 "invalidation":{"type":"daily_close_below","level":8240},
 "targets":[{"r":2.0},{"trail":"chandelier_3atr"}],
 "hedge":{"required_if":"geo_risk==high","type":"long_put","max_premium_pct":0.5},
 "validity":"2026-10-14T17:00Z","confidence":0.55}
```

**Code:** fair value and residuals, triggers, sizing, roll and tender automation, blackouts, stops, kill switch. Code may shrink or veto any plan.

**Fast scalping models:** gradient-boosted classifiers or regressors on L5 order-flow imbalance, 1–5 minute returns, resid_z and time-of-day, with a 5–15 minute holding horizon.
- Viable instruments: multi-lot CRUDEOILM, SILVERMIC, NATGASMINI, 17:30–23:00 only.
- Requires a measured end-to-end latency under 500 ms.
- Phase 3, gated on paper evidence.

---

## 11. First three strategies to build, and go-live gates

1. **ESB on CRUDEOILM:** setup A exactly as written. Add SILVERMIC after 30 sessions. Maximum 4 lots.
2. **EIA Protocol:** CRUDEOILM on Wednesday, NATGASMINI on Thursday. The pre-event flatten rule applies system-wide from day 1, even before the trading logic goes live.
3. **Daily Trend:** GOLDPETAL ladder (≤8 lots) plus CRUDEOILM (1 lot). This exercises roll, tender, re-arm and gap budgeting at small risk.

Run the global-lead FV and resid_z logging continuously from day 1 for research.

**Go-live criteria per strategy:**
- **Sample size:** at least 60 paper sessions, with ≥100 trades for intraday strategies, or ≥20 trades / 6 months for trend.
- **Edge:** net expectancy ≥ 0.15R, with a positive bootstrap 95% lower bound and profit factor ≥ 1.3.
- **Drawdown:** max drawdown ≤ Rs 40k on the commodity sleeve.
- **Execution:** realised slippage within 25% of the model, and paper results within ±30% of a backtest over the same period.
- **Operations:**
  - Zero missed roll or tender deadlines.
  - 100% stop coverage.
  - Zero risk-rule breaches.
- **Rollout:** live at 1 lot for 1 month, then scale in steps.

---

## OPEN QUESTIONS for the owner

1. Do you approve the commodity sleeve limits (Rs 2.5L margin cap, Rs 10k daily sub-budget) inside the shared Rs 25k daily limit?
2. Should positional holding be allowed, with a 0.75% per-position and 1.5% total gap budget, including weekends and the duty-cut tail risk on bullion?
3. Which MCX execution broker: Zerodha (later square-off, web-only MCX GTT) or Upstox (22:50 square-off)? Or Zerodha for execution and Upstox for data?
4. What is the budget for international data: free and delayed only, a cheap real-time forex/CFD feed (~$0–80/mo), or Databento live (~$200+/mo)?
5. Will you buy historical MCX intraday data from a vendor, or accept 3–6 months of self-recording before backtests?
6. Will the system run until 23:30/23:55 unattended? If yes, which alert channel (e.g. Telegram), and do you accept the watchdog flatten rule?
7. Is buying options on futures allowed (hedges and defined risk)? Should all short-option strategies be banned?
8. Are short positional futures (e.g. crude) allowed?
9. Should a commodity drawdown in the evening reduce the *next day's* equity budget, or only count toward weekly and monthly limits?
10. Should base-metal minis be included now or deferred? Silver 100 depends on liquidity.
11. Do you accept the tier-1 event blackout (−10/+5 min), which gives up the initial spike?
12. Has your CA confirmed tax treatment, i.e. CTT-paid commodity futures as non-speculative business income, and set-off against equity F&O?