# Intraday Options Module: design report (as of 2026-10-08)

Confidence tags: **[H]** means checked against an exchange circular or several consistent sources. **[M]** means broker or secondary sources only. **[P]** means my own practitioner estimate; validate it with our own data. Sources are listed by number at the end.

**Market snapshot [M]:** Nifty 22,776 (Oct 6). India VIX 13.6–14.7. BankNifty about 54,500–55,200. Sensex about 71,900 (Oct 1). The index is down roughly 7% in five weeks [20]. All worked numbers below use Nifty about 22,800 and VIX about 14.

---

## 1. Market structure facts

| Item | Current fact | Conf |
|---|---|---|
| Weekly expiries | Only **Nifty 50 (NSE, Tuesday)** and **Sensex (BSE, Thursday)**. BankNifty, FinNifty, MidcpNifty and NiftyNxt50 are **monthly only**, expiring on the last Tuesday. Bankex is monthly, expiring on the last Thursday. Stock F&O expires on the last Tuesday. If expiry falls on a holiday, it moves to the previous trading day [1][2][3]. | H |
| Lot sizes | Nifty **65**, BankNifty **30**, FinNifty **60**, MidcpNifty **120**, NiftyNxt50 **25** (from the Jan 2026 series). Sensex **20** [4][5]. NSE reviews lot sizes about every six months, so the next change could come around Dec 2026–Jan 2027. **Hard rule: read `lot_size`, `freeze_quantity` and `tick_size` from the instrument master every day.** Upstox's `complete.json.gz` carries all three. Beware a known scaling quirk in `tick_size` [18]. Stock lot sizes were revised in May and July 2026. | H |
| Freeze qty (from 5-Oct-2026) | Nifty **3,510** (54 lots), BankNifty **1,440**, FinNifty **3,240**, MidcpNifty **5,760**, NiftyNxt50 **1,125** [6]. These do not bind at our size, but slicing must still be generic. Upstox V3 `slice=true` splits into at most 25 child orders, and each child pays brokerage [17]. | H |
| Position limits | Index options are checked intraday: per entity, net FutEq ₹5,000 cr and gross ₹10,000 cr, with at least 4 random snapshots a day [7]. These are irrelevant at ₹10L, so a config sanity check is enough. **Stock ban rule:** a stock goes into ban when FutEq OI reaches 95% of MWPL, and only risk-reducing trades are allowed after that [8]. The scanner must drop ban-list names from fresh option trades. | H |
| Upfront premium / ELM | Option buyers pay 100% premium upfront, so long options get no leverage. **Extra 2% ELM** applies to all short index options expiring that day, **even if hedged**. Zerodha's method is 2% × spot × lot, about **₹29.6k per short Nifty lot** [9]. Calendar-spread margin benefit is removed on expiry day: for index since Feb 2025, and for single stocks since about May 2026 [10]. | H/M |
| SL-M | Not allowed for stock or index options since Sept 2021. Only SL-L works [11]. Many brokers also block market orders on stock options. | H |
| Algo rules (mandatory from 1-Apr-2026) | Orders must come from a whitelisted static IP. 2FA login every day. Exchange Algo-ID tagging. Above **10 orders/sec** (modifications count) the strategy needs registration, or orders are rejected outright depending on the broker. Some brokers convert market orders to price-protected (MPP) orders [15]. | M |
| Charges (from Apr 2026) | **STT 0.15%** of sell-side premium (was 0.10%). 0.15% of intrinsic value if exercised. **Futures STT 0.05%** (was 0.02%) [12]. NSE options transaction charge **0.03553%**, BSE **0.0325%** [13]. Stamp duty 0.003% on buys. SEBI fee ₹10/cr. GST 18% on brokerage + transaction + SEBI charges. Brokerage ₹20/order at Zerodha and Upstox Basic, **₹30 on Upstox Plus**, with multi-leg discounts [14]. | M-H |
| F&O pre-open | Runs 9:00–9:15 for **futures only** (since Dec 2025) [19]. Option quotes at 9:15 are noisy price discovery. | M |

**Break-even per round trip for Nifty options** (buy and sell at the same premium, ₹20/order, NSE). The total excludes spread. Typical Nifty weekly ATM spread is 0.05–0.10, which adds about 0.10/unit when we cross it [P].

| Premium | 1 lot (65) total ₹ | ₹/unit | % of premium | 5 lots ₹/unit | % |
|---|---|---|---|---|---|
| 50 | ~55 | 0.85 | 1.7% | 0.26 | 0.53% |
| 100 | ~63 | 0.96 | 0.96% | 0.38 | 0.38% |
| 200 | ~78 | 1.20 | 0.60% | 0.62 | 0.31% |

At delta 0.5, a 1-lot trade at ₹100 premium must move about **2.1 Nifty points** to break even, including spread.

**Key derived fact:** one Nifty **futures** lot now costs about **₹741 in STT per round trip**: 0.05% × 65 × 22,800, or about 11.4 index points. The same delta through 2 ATM option lots costs about ₹90–130.
- **Index intraday direction:** ATM/ITM weekly options are 6–8× cheaper per unit of delta for holds under about 1–2 hours. Theta outweighs this saving only on longer holds.
- **Stock intraday direction:** cash MIS (STT 0.025% on the sell side) beats both futures and options. Options should be the exception there.

**Stock option liquidity [P]:** I found no 2026 published source on stock-option spreads.
- **Top tier, typically about 20–25 names:** HDFC Bank, ICICI Bank, Reliance, SBI, Infosys, Axis, Bharti, Kotak, L&T, Bajaj Finance, TCS, M&M, Tata Steel, ITC, BEL, HAL, Eternal. Front-month ATM spreads run 1–3 ticks, about **0.3–1.0%** of a ₹15–60 premium.
- **Second tier:** 1–3%.
- **OTM and next month:** 2–5% or more.
- NSE does not publish impact cost for options.

**Recommendation:** build a daily **liquidity whitelist** from our own recorded 30-level depth. Measure median spread% for ATM±2 strikes at 9:30, 11:00 and 14:00, top-5 depth in lots, volume and OI.
- To qualify: median spread ≤ 0.8% (≤ 0.5% preferred), top-5 depth on each side ≥ 5× our order, and ATM daily traded premium ≥ ₹25 cr.

---

## 2. Directional option buying intraday

**When it works:**
- The day-type classifier says trend or breakout: the opening range breaks with expanding realized volatility, and price holds above or below VWAP.
- Momentum after news.
- Event aftermath, once IV has already been crushed.
- ATM IV percentile ≤ 60–70, or IV/RV20 ≤ 1.2.

**Avoid:**
- IV in the top decile with no momentum.
- The first 15 minutes, for anything except opening-range confirmation.
- Any setup where the expected move is less than 3× break-even.

**Strike policy.** The LLM specifies a delta band. Code picks the exact strike at trigger time.
- Default: **Δ 0.50–0.65** (ATM or 1 strike ITM). Premium band: Nifty ₹80–250 on non-expiry days, ₹30–120 on expiry day.
- OTM (Δ 0.30–0.40) only on confirmed trend days with low IV. Use half size.
- **Never buy Δ < 0.15 or premium < ₹10**, except to close a position.

**Days to expiry (DTE).**
- Regular intraday trades use the current weekly when DTE ≥ 1. On expiry day, roll to the next weekly. The 0DTE expiry playbook (§5) is separate.
- BankNifty is monthly only: premium ₹500–900, spread 0.2–1.0. Use it on bank-led days.
- Sensex weekly is a valid second instrument. BSE now holds about 25–30% of options premium [21].
- FinNifty and Midcap are excluded in phase 1 because they are illiquid.

**Stops and exits:**
- **Primary stop is on the underlying** (structure low/high, OR mid, VWAP), never a raw premium %.
- **Premium catastrophe cap:** −35% (non-expiry) or −50% (expiry), whichever comes first. This guards against IV collapse and gaps.
- **Time stop:** exit if there is no +0.5R move within 20 minutes (index) or 40 minutes (stock). Maximum hold 120 minutes. Also exit when theta paid exceeds 0.3R without progress.
- **Scaling:** take 50% off at 1R (measured on the underlying), then move the stop to breakeven on the underlying. Trail the rest on 5-minute swing points or VWAP. The final target is the next OI wall or level.

**Translating an equity plan into an option position (R-matching).** Size on a full repricing, not on delta alone, especially near expiry:

```
loss_per_lot = lot × [P0 − BS(S_stop, K, T−t_hold, σ−Δσ_crush)] + fees + exit_half_spread
lots = floor(R_equity / loss_per_lot);  premium_stop = BS(S_stop, …)  # consistent with underlying stop
```

Worked example (Reliance; the lot of 500 is illustrative):
- Equity plan: long at 1,400, stop 1,386, R = ₹5,000. That is 357 shares.
- Option: 1,380 CE, Δ 0.62, Γ 0.006, 12 DTE, about ₹38.
- Repricing at 1,386 after 30 minutes gives a loss of about ₹8.2/unit. One lot loses about ₹4.1k + costs, so trade 1 lot. The premium stop is about ₹29.8.

**Prefer cash or futures over options when:**
- Spread > 1% of premium.
- IV percentile > 70, or results fall within the option's life.
- Expected hold is over 2 hours.
- The stock has no liquid options.

Prefer options when the trade needs **defined loss through a gap or halt** (binary news, a circuit-prone name), or when expressing index direction (see the cost math in §1).

---

## 3. Intraday selling: hedged, defined-risk spreads only

**Structures:**
- Credit spreads, iron condors and iron flies on Nifty or Sensex.
- Wings 100–200 points (Nifty) or 300–500 (Sensex).
- Same expiry only. No naked shorts, ever.

**When to sell:**
1. **Range day**, from 10:45 onward. The first-hour range is below 0.6× the implied daily move, VIX is flat or falling, spot sits between the max-call-OI and max-put-OI walls, and the walls are not migrating against the position.
2. **After an IV spike.** A gap with VIX up 8% or more, followed by the first 60–90 minutes holding a range. Sell the side away from the move, or an iron fly, for vega plus theta.
3. **Expiry-day theta** (see §5).

**When not to sell:**
- Trend or breakout classification, or realized volatility expanding.
- VIX up more than 5% intraday.
- Before 10:15.
- Scheduled events: RBI policy, Budget, election results, large index-weight results, war or geopolitical headlines.
- IV percentile below 15 on non-expiry days, where premium is too thin.
- A gap of more than 1% that has not stabilised.

**Margin at ₹10L [M/P]:**
- A Nifty iron condor needs about ₹35–60k per set on non-expiry days. On expiry day add about ₹29.6k per short lot, so roughly ₹95–120k per set. Always fetch the exact figure from the broker margin API before trading.
- Selling margin cap: ₹3L.

**Risk:**
- Maximum loss per structure, (width − credit) × qty, must be ≤ ₹8k. For example, (150 − 30) × 65 = ₹7.8k.
- Working stop: MTM loss of 1.0× credit or ₹4–5k.
- **Costs bite:** a 4-leg set is 8 orders, about ₹200–250 per round trip, or about 15% of expected profit at 1 set. Trade 2 or more sets, or use Upstox Plus multi-leg pricing.

**Adjustment rules (deterministic):**
- If spot reaches the short strike − 0.25 × remaining 1σ, **close the threatened spread** rather than rolling it.
- At most one roll per day, only of the untested side, and only if the new maximum loss stays within the cap.
- Never widen, never add to a loser, never leave a short leg unhedged.
- Exit everything if the day type flips to trend or VIX rises 5% from entry.

**Leg sequencing is enforced by the executor:**
- Entry: buy the hedge first, then sell the short. If the hedge fails, abort.
- Exit: buy back the short first, then sell the hedge.
- Risk-manager veto: any order that would leave net short options without a hedge in the same underlying and expiry is rejected.

---

## 4. Option-chain features: what code computes and what the LLM sees

Snapshot cadence: index chains every 15–60 s; stock watchlist every 3–5 min. OI updates more slowly than price on the feed, so treat it as 1–3 minute granularity and verify on Upstox.

| Feature | Computation | Code uses for | LLM uses for |
|---|---|---|---|
| OI buildup class | Underlying/futures: price direction × OI direction (long buildup, short buildup, short covering, long unwinding). Options: premium × OI (call writing = CE price falling with OI rising). | Confirmation gates on triggers | Narrative, bias |
| ΔOI by strike | 15/30/60-min ΔOI for ATM±10 strikes. Max-call-OI and max-put-OI walls. **Wall migration** events (e.g. put wall moves up 1 strike with ΔOI > X). | S/R levels, breakout confirmation (wall unwinding) | Levels in plans |
| PCR | OI-PCR on ATM±10 strikes, level plus 30-min slope. Total PCR as context only. | Weak filter | Sentiment context |
| Max pain | Standard computation | Only on expiry day after 13:00, and only if \|spot − MP\| < 0.5× remaining expected move | Mention only |
| IV, IVP/IVR | ATM constant-maturity IV, percentile over 252 days. India VIX is the long-history proxy for Nifty. | Buy/sell eligibility | Regime |
| Skew | 25Δ put IV − 25Δ call IV, plus its intraday change | Fear-building flag | Context |
| Implied vs realized | Day's implied σ = S·IV·√(1/252). Ratio = realized range so far ÷ implied. | **Day-type input:** above 0.8 by 11:00 suggests trend (buy); below 0.35 by 12:30 suggests range (sell) | Context |
| GEX (approximate) | Σ Γ·OI·lot·S²·1% per strike | Strike-concentration / pin magnet only | Caveated context |
| Basis, futures OI | (Fut − Spot) − fair carry. Futures ΔOI with price. NSE participant-wise OI (EOD; FII/Pro/Client long/short) as a daily prior. | Bias filter | Daily prior |

**GEX caveat for India:** the US "dealers short, customers long" sign convention does not hold here. Writers are prop and FPI desks, many do not delta-hedge (they roll strikes instead), and retail is net long OTM. Use GEX as a concentration map, not a flow forecast.

**Division of labour:**
- Code computes everything and emits a compact `chain_state` JSON (walls, migrations, PCR level and slope, IVP, skew, RV/IV, basis, day type).
- The LLM chooses the **vehicle and structure**: cash, long option, debit spread, credit structure, or none. It writes underlying-level triggers and invalidations, and a delta/DTE policy.
- The LLM never picks the exact strike, computes greeks, or sizes positions.

---

## 5. Expiry-day playbook (Nifty Tuesday, Sensex Thursday)

| Window | Allowed | Rules |
|---|---|---|
| 9:15–9:45 | Observe; opening-range momentum buys only after 9:30 confirmation | No shorts |
| 9:45–13:00 | **Momentum bursts:** Δ 0.45–0.6 0DTE, breakouts of OI walls or levels with futures volume > 1.5× | Risk **₹3k/trade** (60% of normal). Premium cap −50%. Time stop 10–15 min. Max hold 30 min. Target 1.5–2R. |
| 13:00–14:30 | **Theta sells:** iron fly or condor, only if range-contained (RV/IV < 0.5), VIX flat or falling, spot between walls | Maximum 1–2 sets. Short strikes at or beyond the walls. ELM-inclusive margin check. Take profit at 50–60% of credit. |
| 14:30–15:00 | Exits only. No new shorts after 14:30, no new longs after 14:45. | **Pin rule:** if spot is within 0.2% of a short strike or high-OI strike at 14:30, close that leg |
| 15:00 / 15:10 | **Shorts flat by 15:00. Everything flat by 15:10.** | Only exception: long OTM options worth < ₹0.5, where exit cost exceeds value (logged) |

**Gamma-scalping** (long straddle hedged with futures): not recommended. Futures STT of 0.05% kills it at our size.

**Lottery ban:** no buys of premium < ₹5 or Δ < 0.15 after 13:00. Expiry-day cap on aggregate long premium: ₹25k.

---

## 6. Stock options around news and results

- **Before results:** never buy naked options within 3 sessions of results. IV typically runs 1.3–1.8× normal and crushes 20–40% afterwards [P]. If a view is mandatory, use a debit spread at half size.
- **Day after results:** the move is linear and gap-driven. **Default to cash MIS.** If using options (for defined risk), go ITM (Δ 0.65–0.75) after 9:45, once IV has settled.
- **News shock** (orders, regulatory news, block deals): IV jumps 5–15 points [P]. Options are still worth it only if all of the following hold:
  - expected follow-through ≥ 2× (break-even + spread + a 3-point IV mean-reversion allowance);
  - spread ≤ 1%;
  - ITM strike;
  - name on the whitelist and not in the ban list.
  
  Otherwise trade cash.
- **Physical settlement:** stock options are physically settled. Never trade them in the final 2 sessions before expiry; broker restrictions and auto square-off apply.

---

## 7. Execution specifics

- **Limit orders only.** Entry starts at mid (or mid + 1 tick) and re-pegs every 1–2 s toward the touch.
  - Maximum chase: min(3 ticks for index, 0.5% of premium, 0.25 × R per unit).
  - Abort after 15 s, or if the underlying runs more than 0.3R past the trigger.
- **Spread filter.** Reject if spread > max(1 tick, X% of premium). X is 0.5% for index weeklies, 1.0% on expiry day, 0.5% for BankNifty, 1.0% for stocks (1.5% hard reject). Also reject if same-side top-5 depth < 3× order size.
- **Strike universe.** Index ATM±6, stocks ATM±3. Strike must have traded in the last 60 s and meet minimum OI and volume.
- **Slicing.** Slice above `freeze_quantity`, and also at ≤ ⅓ of visible depth.
- **Stops (SL-M is unavailable):**
  - The real stop is software on the underlying. When it fires, send a marketable limit at bid − max(2 ticks, 2%), re-peg every 500 ms up to 3 times, then go to bid − 5%. Stay inside the exchange price band.
  - Also place a **broker-side SL-L catastrophe order** at the premium cap: limit = trigger − max(₹2, 5%). This covers a system outage.
- **Fast-market mode.** Triggered by spread > 3× median, 1-minute range > 3× ATR, or feed lag > 1 s. Pause entries, widen exit buffers, cancel working entries.
- **Stale feed** (> 3 s): rely on the catastrophe orders and raise an alert.
- **Throttle.** Global ≤ 8 orders+modifications per second (SEBI's 10 OPS threshold), and a per-order cap of 20 modifications.
- **Infra.** Static IP for the order API. Tag every order with strategy ID and plan ID.

---

## 8. Risk and sizing (proposed defaults; owner to confirm)

```yaml
options_risk:
  global_daily_stop: 25000        # 2.5%, soft stop at 15000 -> half size, A+ only
  options_daily_cap: 12500        # module ring-fence (configurable/shared)
  long_option_risk_per_trade: 5000   # expiry day 3000; A+ max 7500
  max_premium_per_trade: 60000    # expiry 25000; total long premium open <= 150000
  spread_margin_cap: 300000; spread_max_loss_per_structure: 8000; spread_stop: 4500
  max_lots: {NIFTY: 6, SENSEX: 10, BANKNIFTY: 4, STOCK_OPT: 2}
  max_concurrent: 3; max_trades_day: 6; consecutive_loss_halt: 3
  book_limits:
    beta_wtd_net_delta_nifty_notional: 2000000   # 1% Nifty ≈ ₹20k
    net_vega_per_volpt: 2500
    expiry_gamma_pnl_0p5pct_move: 8000
  free_cash_reserve: 200000
```

**Correlation.** All positions roll up to **beta-weighted Nifty-equivalent delta**. Example:
- Long 2,000 HDFC Bank in MIS (β ≈ 1, about ₹19L) plus 3 lots Nifty ATM CE (Δ 0.5 × 195 units ≈ ₹22L) totals about ₹41L.
- The book limit is ₹20L, so the risk manager **vetoes or downsizes** the second order.
- BankNifty options together with bank stocks are aggregated the same way, via beta to BankNifty and then to Nifty.

---

## 9. Backtesting with expired-contract data

**What Upstox provides** (Upstox Plus) [16]:
- OHLC + volume + **OI** candles at **1, 3, 5, 15, 30 min and daily**, from a contract's first trade to expiry.
- Retention was historically about 6 months, with about 2 years planned [M]. Verify how far back the owner's account actually reaches.
- Some contracts return empty data.
- **No bid/ask and no depth history.**

**IV and greeks reconstruction:**
- Per minute, take the ATM pair that minimises \|C − P\| to get the **synthetic forward** from put-call parity. This avoids dividend and basis error.
- Use Black-76 with r = 91-day T-bill (config) and a single, consistent time convention (calendar minutes, as India VIX uses).
- Only use strikes with volume in that minute and premium ≥ ₹2. Drop parity violations larger than the assumed spread.
- Build a daily constant-maturity 30-day ATM IV (interpolating front and next expiry) to get IVR/IVP. Use India VIX history as the Nifty fallback.
- Flag IVP as low-confidence until 252 days of history exist.

**Fill model (conservative):**
- Decide on bar close, fill at next bar open ± a half-spread model by bucket. Assumed half-spreads: Nifty ATM 0.05–0.10 normal, 0.5–1.0 in the first 5 minutes and during shock minutes; stocks 0.5% of premium, minimum 1 tick.
- Stops trigger on the underlying's 1-minute bar and fill at the option bar's adverse extreme ∓ half-spread.
- Fill quantity ≤ 10% of bar volume. No fills on zero-volume bars.

**Pitfalls:**
- Stale last prices on illiquid strikes.
- Strike survivorship: choose "ATM" only from strikes that existed and traded at that moment, since strikes are added dynamically.
- Per-contract lot sizes (65 vs 75).
- Regime breaks: Thursday-to-Tuesday expiry (Sept 2025), BankNifty weeklies removed (Nov 2024), STT changes (Oct 2024, Apr 2026), extra ELM.
- Design on the current regime (Sept 2025 onward). Use older data only for robustness checks.
- About 100 expiry days a year across Nifty and Sensex is a small sample.
- **1-minute bars cannot validate 1–3 minute option scalps.**

**Start a tick + 30-level depth recorder now.** It builds our own spread, fill and liquidity dataset, and is the only real fix for the missing bid/ask history.

---

## 10. First three strategies to paper trade

**S1 — Index level-break momentum (long options).** Nifty/Sensex. Current weekly if DTE ≥ 1, otherwise next weekly. Expiry-day variant at 60% size.
- **Window:** 9:30–14:15.
- **Preconditions:** day type is trend or breakout candidate; IVP ≤ 70; no event within 30 minutes; VIX not up more than 8%.
- **Trigger:** 5-minute close beyond the opening-range high/low or an LLM-plan level, on the correct side of VWAP, with futures 5-minute volume ≥ 1.5× its 20-bar average. Also require **at least one chain confirmation**: call OI unwinding at the broken strike, or fresh put writing one strike below (mirror for shorts).
- **Strike:** Δ 0.55–0.65.
- **Stop:** underlying, at the breakout-bar extreme or OR mid, but at least 0.25 × ATR(5m). Premium cap −35%.
- **Size:** ₹5k R using the repricing formula in §2.
- **Exits:** 50% at 1R; trail the rest on 5-minute swings. Time stop 20 minutes. Hard exit 15:10.

**S2 — Range-day hedged iron condor or iron fly.** Nifty.
- **Entry window:** 10:45–13:30 (expiry variant 13:00–14:30).
- **Preconditions:** range classification; first-hour range < 0.6× implied; VIX ≤ prior close; spot between stable OI walls.
- **Structure:** short strikes ≥ 0.5× remaining implied move and at or beyond the walls; 150-point wings.
- **Size:** 1–2 sets; maximum loss ≤ ₹8k per set.
- **Exits:** take profit at 40–50% of credit. Stop at 1× credit, or underlying within 0.2 × ATR of a short strike, or VIX +5%, or day-type flip. Flat by 15:00.

**S3 — Stock-plan option overlay with a cash shadow.**
- Every triggered LLM stock plan on a whitelisted, non-ban name with no results inside 5 sessions and IVP ≤ 60 is executed **both** in cash MIS (paper) and as an R-matched ITM option (Δ 0.6–0.75, front month if ≥ 5 sessions remain, otherwise next month).
- Both legs share the same underlying stop and targets.
- Purpose: measure empirically when options beat cash.

**Go-live gates (per strategy):**
- At least 10 weeks of paper trading covering ≥ 8 Nifty and ≥ 8 Sensex expiries.
- At least 60 trades for S1 and at least 40 each for S2 and S3.
- Net expectancy ≥ +0.15R and profit factor ≥ 1.3, after modelled costs and **depth-based paper fills** (fill only on a cross of bid/ask with available quantity, never on an LTP touch).
- Realized slippage within 1.5× the model.
- Maximum drawdown ≤ 6 daily-cap units.
- **100% compliance:** zero naked legs, zero missed flats, catastrophe stop present on 100% of positions.
- Paper results within 1 standard deviation of the backtest.

**Ramp:** 25% size for 4 weeks, then 50%, then 100%, with each step re-checked against the same gates.

---

## Open questions for the owner

1. What share of the ₹20–30k daily loss can options use? Should module budgets be ring-fenced (I propose ₹12.5k) or shared?
2. Is hedged selling (S2) and 0DTE expiry trading acceptable in phase 1, or should we start with buying only?
3. Should Sensex weeklies on BSE (Thursday) be included alongside Nifty?
4. Which broker for live options: Upstox Basic (₹20/order) or Plus (₹30, multi-leg discounts), or Zerodha? Where will the static-IP host run (a Mumbai VPS?)
5. For "exceptional" swing setups, may we carry **defined-risk debit spreads** overnight instead of naked longs?
6. Should cash MIS be the default for stock ideas, with options only when the gates pass? Is that acceptable?
7. How far back does your Upstox expired-contract data actually go? Would you pay for historical bid/ask or tick data (e.g. a vendor feed)?
8. What is the event-calendar source (results, RBI, macro), and who maintains it?
9. Are you willing to register strategies with the exchange if order rates ever exceed 10/sec?
10. Do you accept the hard 15:10 flat rule and the expiry-day 15:00 shorts cut-off?

---

**Sources:**
[1] https://www.bajajfinserv.in/nse-revises-nifty-expiry-day ·
[2] https://algotest.in/blog/sensex-expiry-day/ ·
[3] https://www.outlookmoney.com/news/fo-trading-all-equity-derivatives-on-exchanges-to-expire-on-either-tuesday-or-thursday-sebi-mandates ·
[4] https://hdfcsky.com/news/nse-revises-market-lot-sizes-for-major-index-derivatives-effective-january-2026 ·
[5] https://www.sahi.com/blogs/nifty-lot-size-2026-bank-nifty-sensex ·
[6] https://nsearchives.nseindia.com/content/circulars/FAOP76693.pdf , https://choiceindia.com/news/nse-revises-quantity-freeze-limit-for-index-fno-contracts-from-october-5-2026 ·
[7] https://www.business-standard.com/amp/markets/news/sebi-stricter-intraday-position-limits-options-market-regulation-125090200971_1.html ·
[8] https://www.businesstoday.in/markets/story/sebi-equity-fo-rules-futeq-method-mwpl-risk-management-478321-2025-05-29 ·
[9] https://support.zerodha.com/category/trading-and-markets/margins/margin-leverage-and-product-and-order-types/articles/additional-elm-for-index-expiry ·
[10] https://www.icicidirect.com/ilearn/futures-and-options/articles/removal-of-calendar-spread-margin-benefit-for-single-stock-derivatives-on-expiry ·
[11] https://zerodha.com/marketintel/bulletin/305785/stop-loss-market-sl-m-orders-blocked-for-index-options , https://community.upstox.com/t/stopp-loss-market-orders-are-not-allowed-on-this-price/5742 ·
[12] https://www.icicidirect.com/ilearn/futures-and-options/articles/stt-changes-in-budget-2026-what-f-o-traders-should-know , https://zerodha.com/marketintel/bulletin/445377/revision-in-stt-securities-transaction-tax-from-1st-april-2026 ·
[13] https://nsearchives.nseindia.com/content/circulars/FA73061.pdf , https://zerodha.com/pricing?c=ZMPOTY ·
[14] https://upstox.com/help-center/does-the-brokerage-plan-change-with-upstox-plus-264072/ ·
[15] https://support.fyers.in/portal/en/kb/articles/what-are-the-new-sebi-rules-for-retail-algo-trading-from-april-01-2026 , https://thedailybrief.zerodha.com/p/sebis-latest-algo-trading-rules ·
[16] https://upstox.com/developer/api-documentation/backtesting , https://community.upstox.com/t/issue-with-expired-contract-historical-data-10-minute-timeframe-using-python-sdk/12473 , https://community.upstox.com/t/historical-availability-retrieval-limit-per-query-for-expired-options-contract/9245 ·
[17] https://upstox.com/developer/api-documentation/v3/place-order ·
[18] https://community.upstox.com/t/duplication-of-lot-size-and-minimum-lot-keys/9576 , https://community.upstox.com/t/tick-size-in-json-instruments-file-not-correct/6258 ·
[19] https://www.tradejini.com/blogs/nse-to-launch-preopen-session-for-futures-contracts-from-december-8-2025 ·
[20] https://www.jmfinancialservices.in/market-news-and-insights/1735386 , https://www.angelone.in/news/market-updates/nifty-bank-index-climbs-above-54-600-mark-in-intraday-trade-on-october-5-2026 ·
[21] https://www.multibagg.ai/market-pulse/articles/nse-options-market-share-decline-cmu1gmiuhfac7a5b496e3ffd1