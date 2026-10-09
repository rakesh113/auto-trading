# Broker and Market-Data API Capability Map: Upstox (primary) and Zerodha Kite Connect (secondary), as of October 2026

**How this was checked.** The sandbox blocked direct fetches of upstox.com and kite.trade. Facts come from three places:
- **SDK source code**, fetched and read directly: the Upstox SDK at `github.com/upstox/upstox-python` (README, `docs/*.md` and `MarketDataFeedV3.proto`) and Zerodha's SDK at `github.com/zerodha/pykiteconnect` (`connect.py` and `ticker.py`).
- **Search-engine extracts** of official Upstox and Zerodha pages.
- **Staff replies** on the Upstox and Kite developer forums.

**Confidence tags:**
- **[H]**: confirmed in SDK source or an official page.
- **[M]**: an official page seen only in a search extract, or a staff forum reply.
- **[L]**: a user forum post, a third-party source, or an older post.

**Judgment** marks my own analysis, not a fact.

---

## 0. Bottom line

1. **Data: use Upstox.**
   - Only Upstox offers 30-level depth, greeks inside the websocket feed, REST APIs for option chain, PCR, OI and max pain, and expired F&O contract candles.
   - It also offers a 1-year read-only Analytics Token. That lets the research and data side run 24x7 without the daily login.
2. **Execution: build adapters for both brokers. Which one goes live first depends on one fact about your existing agent.**
   - Since 1 Apr 2026 Upstox allows **only one active API app per user**. On top of that, these are shared per account: static IP, the 10 orders/second regulatory cap, the websocket connection limit, and the REST rate limits.
   - So if the existing options-selling agent trades the same Upstox account, the two systems must share one token and one order gateway.
   - **Judgment:** I'd put the new system's executions on Zerodha (Kite Personal API is free for orders). That keeps the two agents' risk separate and costs about ₹10 less per order than Upstox Plus. Upstox would remain the data source.
3. **Neither broker gives tick-by-tick trades or any historical tick or depth data.**
   - Both feeds send conflated snapshots, roughly 1–4 updates per second per instrument.
   - Scalping research therefore needs a recorder that captures our own feed from day one of paper trading, or a paid tick-data vendor.
4. **Since April 2026 a market order is not a true market order on either broker.** Both apply market price protection (MPP): the order is capped within a price band and any unfilled remainder can sit as a limit order.
   - **Judgment:** the system should send its own marketable-limit and IOC orders everywhere, including in paper mode. It should not rely on each broker's protection behaviour.

---

## 1. Upstox

### 1.1 Real-time feed (Market Data Feed V3)
- **Protocol** [H]: WebSocket carrying protobuf messages. You first call an authorize endpoint (`/v3/feed/market-data-feed/authorize`), which returns the socket address.
  - Each message carries a `type`: `initial_feed`, `live_feed` or `market_info`, plus a server timestamp `currentTs`.
  - Order of messages: first a market-status message, then a snapshot of current data, then live updates. ([proto](https://github.com/upstox/upstox-python/blob/master/upstox_client/feeder/proto/MarketDataFeedV3.proto), [doc](https://upstox.com/developer/api-documentation/v3/get-market-data-feed))
- **Modes** [H]:
  - `ltpc`: last price, last trade time, last trade quantity, previous close.
  - `option_greeks`: first-level depth, the greeks, volume today, OI and IV.
  - `full` (`full_d5`): 5-level depth plus ATP, volume today, OI, IV, total buy and sell quantity, and 1-minute and daily OHLC.
  - `full_d30`: the same with 30 depth levels.
  - Pre-open fields are also included: indicative equilibrium price and quantity, plus market status from PRE_OPEN through CLOSING_END.
- **Each depth level carries only price and quantity; there is no order count** [H]. The proto's `Quote` message has only `bidQ, bidP, askQ, askP`. Kite's depth does include an order count.
- **Limits, Basic plan** [M]: 2 connections per user.

  | Mode | Max keys, this mode alone | Max keys when several modes are active |
  |---|---|---|
  | LTPC | 5,000 | 2,000 |
  | Option Greeks | 3,000 | 2,000 |
  | Full | 2,000 | 1,500 |

- **Limits, Plus plan** [M]: 5 connections. `full_d30` is Plus-only: **50 keys** alone, 1,500 combined.
  - Staff say each d30 connection takes at most 50 instruments ([thread](https://community.upstox.com/t/market-depth-30-increase-limit-for-more-than-50-instruments/13398)).
  - One user found that a 2nd and 3rd d30 socket connected but received no data [L] ([thread](https://community.upstox.com/t/subscribe-to-full-d30-mode-websocket/12469)). **Plan for 50 d30 keys per account in total.**
  - The connection limit is per client account, not per app [M] ([thread](https://community.upstox.com/t/market-data-feed-v3-multiple-web-socket-connections/10465)). It is therefore shared with your existing agent.
- **Update rate** [M/L]: updates are pushed when data changes, not on a fixed timer.
  - Staff: data is sent "whenever the LTP changes" and tick-by-tick is "not yet enabled". One developer measured about 180–200 messages a minute on Nifty ([thread](https://community.upstox.com/t/websocket-steam-not-feeding-tick-by-tick-data/11186), [thread](https://community.upstox.com/t/what-is-the-time-between-each-tick/3775)).
  - **Judgment:** treat the feed as conflated snapshots. Trades between two messages can only be inferred from changes in last-trade quantity and volume-today.

### 1.2 Orders
- **Endpoints** [H]:
  - Place, modify and cancel: `/v3/order/place|modify|cancel`.
  - Multi-order (v2): up to **25 orders per request**, each line carrying a `correlation_id` of 20 characters or fewer [M] ([doc](https://upstox.com/developer/api-documentation/place-multi-order)).
  - Exit all positions: `/v2/order/positions/exit`.
  - Order book, order history and trades.
- **Faster order host** [M]: place, modify and cancel can go to the HFT host `api-hft.upstox.com`. Multi-order cannot ([thread](https://community.upstox.com/t/multi-order-with-hft-end-point/12132)).
  - Upstox advertises under 45 ms from their server receiving the order to the exchange's acknowledgement.
  - The v3 response reports `metadata.latency` in milliseconds ([doc](https://upstox.com/developer/api-documentation/v3/place-order)).
- **Auto-slicing** [H/M]: set `slice=true` and an order above the exchange's freeze quantity is split automatically.
  - Docs: at most 25 orders per request. The help centre says 20 slices. Brokerage is charged on each slice. OCO is not allowed with slicing.
  - Whether a MARKET order can be sliced is contradictory across sources [L].
- **Order types and validity** [H]: MARKET, LIMIT, SL, SL-M; validity DAY or IOC; plus disclosed quantity, `tag` and `is_amo`. Product: `I` (intraday), `D` (delivery), `MTF` [M].
  - MTF orders work live but not in sandbox [L] ([thread](https://community.upstox.com/t/place-mtf-order-via-api-75-funds-from-upstox-feature/9280)).
- **SL-M is rejected on option contracts** (error UDAPI100500, blocked since September 2021) [M].
- **Market price protection, from 1 Apr 2026** [M]: MARKET and SL-M orders get protection, with an optional `market_protection` parameter ([notice](https://community.upstox.com/t/important-new-sebi-exchange-mandates-for-api-trading-effective-1st-april-2026/14822)).
  - Upstox's MPP terms describe a band of 0.5%–25%, applied automatically to stock options.
  - The field's exact type and allowed values are not confirmed [L]. Test in sandbox.
- **GTT (v3)** [H]: SINGLE or MULTIPLE type, up to 3 legs (ENTRY, TARGET, STOPLOSS), product I or D. GTTs always execute as LIMIT orders [M].
  - An ENTRY leg is mandatory, so GTT cannot be used to protect a position you already hold [M].
  - A `trailing_gap` field exists, but users reported in December 2025 that it did not trail [L] ([thread](https://community.upstox.com/t/automated-upstox-v3-api-and-made-trade-bot-gtt-order-with-trailing-sl-is-not-at-all-working/13011)).
- **No native bracket order. Cover order (CO) is listed in the order models but not usable in practice** [L].
- **Order updates:**
  - Portfolio stream websocket [H]. Update types are order, position, holding and gtt; only order updates are on by default ([thread](https://community.upstox.com/t/portfolio-stream-feed-websocket-client/12689)).
  - Webhook postback [M]: covers only orders placed through the API app, and is unsigned.
- **Rate limits** [M/L]:
  - Forum staff: 25 requests/second, 250/minute, 1,000 per 30 minutes for orders and standard APIs ([thread](https://community.upstox.com/t/rate-limits-on-api-usage/3384)). The marketing page says "50 orders/sec, unlimited modifications" ([page](https://upstox.com/trading-api/)).
  - Multi-order has its own, unpublished limit.
  - Breaching a limit returns HTTP 429 (error UDAPI10005), and **rejected orders also count**.
  - The 10 orders/second regulatory cap sits on top of all of this.
- **HTTP success does not mean the order was accepted.** The API returns success and the RMS rejection (for example, insufficient margin) arrives afterwards [M] ([thread](https://community.upstox.com/t/order-placing-api-returns-status-success-even-when-order-failed-due-to-margin-shortfall/5949)).

### 1.3 Historical data
- **Historical candles V3** [H]: path `/v3/historical-candle/{key}/{unit}/{interval}/{to}/{from}`. Custom intervals: minutes 1–300, hours 1–5, plus days, weeks and months. A separate intraday endpoint serves the current day.
  - Minute and hour data go back to January 2022; day and above to January 2000 [M] ([launch post](https://community.upstox.com/t/get-historical-data-in-any-time-frame-you-wished-we-built-new-releases-at-upstox-api/8845)).
  - A minute-interval request may span at most about 1 month (UDAPI1088 above that; use 30-day chunks) [M].
- **Expired instruments (Plus only)** [H/M]:
  - Endpoints for expiries, expired option and future contracts, and expired candles.
  - Expired contract keys look like `NSE_FO|53806|24-04-2025`.
  - Per-request window per the SDK: 1-minute bars up to 1 month; 30-minute and daily bars up to 1 year.
  - Coverage starts around October 2024; there is nothing for MCX; users report gaps (missing weekly Nifty contracts; SENSEX for February 2026) [L] ([backtesting doc](https://upstox.com/developer/api-documentation/backtesting)).
- **No historical tick or depth API** [H]. No such endpoint appears in the SDK.

### 1.4 Analytics and reference data
- **Option chain** (`/v2/option/chain`), **option-greek quote** (`/v3/market-quote/option-greek`), and LTP, OHLC and full quotes [H].
  - Full quote takes up to 500 instruments and returns 5-level depth. There is no 30-level REST quote [M].
  - OI, change in OI, PCR and max pain endpoints [M], already used by your existing Upstox data skill.
- **Brokerage** `GET /v2/charges/brokerage` and **margin** `POST /v2/charges/margin` (JSON body with an `instruments[]` list) [H].
- **Instrument master** [M]: gzipped JSON files at `assets.upstox.com/.../{complete|NSE|BSE|MCX}.json.gz`, rebuilt around 06:00 IST.
  - Key formats: `NSE_EQ|<ISIN>` for equities; `NSE_FO|<exchange_token>` for derivatives.
  - Index keys are inconsistent: some APIs use `NSE_INDEX|Nifty 50`, others numeric ([thread](https://community.upstox.com/t/when-instrument-file-get-updated/5289)).

### 1.5 Authentication and operations
- **Daily access token** [M]: valid until 03:30 IST the next day. No refresh tokens are issued.
  - The **Access Token Request** flow: your server calls the API, you approve in the Upstox app or on WhatsApp, and the token is delivered to your notifier webhook ([doc](https://upstox.com/developer/api-documentation/access-token-request)).
  - Upstox says it does not support fully automating login.
- **Analytics Token** [M]: valid 1 year, read-only GET access, covers market data, the websocket feed and historical candles. It cannot place orders ([doc](https://upstox.com/developer/api-documentation/analytics-token/)).
- **Static IP** [M]: mandatory for place, modify and cancel. Since 10 Apr 2026 there are user-level static-IP endpoints, with changes allowed at most once a week ([doc](https://upstox.com/developer/api-documentation/announcements/static-ip-apis/)).
  - Apps that are registered as exchange "algo" products must send an `X-Algo-Name` header. A self-built algo staying under 10 orders/second does not need one [M].
- **Sandbox** [H/M]: exists, via the `sandbox=True` SDK flag. It covers only place, modify and cancel (v3).
  - It validates requests but creates **no fills, positions or funds** [M] ([thread](https://community.upstox.com/t/sandbox-vs-prod-data-credentials-and-migration/10369)).
  - It is good for testing request formats, **useless as a paper broker**.
- **Pricing** [M]:
  - Plus activation is currently free, but Plus brokerage is **₹30 per order versus ₹20 on Basic** ([T&C](https://upstox.com/files/terms-and-condition/plus-pack.pdf)).
  - The ₹10 API-order promotion ended 31 Mar 2026; the current API rate is unclear [L].
- **SDK** [H]: Python `MarketDataStreamerV3` and `PortfolioDataStreamer` (thread-based).

---

## 2. Zerodha Kite Connect

- **Feed** [H/M]: binary websocket with three modes: `ltp` (8-byte packets), `quote` (44 bytes) and `full` (184 bytes).
  - `full` carries **5 depth levels, each with an order count**, plus OI and exchange timestamps.
  - Limits: 3,000 instruments per connection, 3 connections per API key [M].
  - 20-level depth is not available through the API, and the feed is snapshot-based: "1-second snapshot", or 1–4 per second at a 250 ms minimum [M] ([thread](https://kite.trade/forum/discussion/comment/49927)).
  - No greeks in the feed and **no option-chain API** (none in the SDK routes [H]). Greeks and IV would have to be computed ourselves.
  - The ticker also delivers order updates (`on_order_update`) [H], as do HTTP postbacks.
- **Orders** [H, from SDK source]:
  - Varieties: `regular`, `co`, `amo`, `iceberg`, `auction`. Validity: DAY, IOC, TTL. Products: MIS, CNC, NRML, CO.
  - Parameters `market_protection` (−1 = automatic, or a custom 1–100%), `algo_id` and `tag`.
  - `place_autoslice_order` (`autoslice=true`) returns a parent ID plus a list of children.
  - GTT: single or two-leg (OCO).
  - Margin calculation for single orders and baskets; virtual contract note (charges).
  - No bracket order.
- **Market protection** [M]: a protection value of 0 is rejected for MARKET and SL-M orders, and omitting the field does **not** default to −1. Leftover quantity can stay open ([thread](https://kite.trade/forum/discussion/15912/preparing-to-comply-with-sebis-retail-algo-rules-static-ip-ratelimits-order-types)).
- **Rate limits** [M]:
  - 10 orders/second, 400/minute, 5,000/day, counted per account. Older posts say 200/minute and 3,000/day.
  - Quote API 1 request/second; historical 3/second; everything else 10/second. Breaching returns HTTP 429 ([thread](https://kite.trade/forum/discussion/comment/52868/)).
- **Historical** [M]:
  - Maximum window per request: 1-minute bars 60 days; 3–10 minute bars 100 days; 15–30 minute bars 200 days; hourly 400 days; daily 2,000 days.
  - **No expired options**. Expired futures are available only as daily candles, using `continuous=1` ([Zerodha support](https://support.zerodha.com/category/trading-and-markets/charts-and-orders/charts/articles/historical-data-for-expired-f-o-contract)).
  - No tick history.
- **Authentication** [M]: manual login every day (TOTP two-factor). The token expires around 06:00 IST. Kite says automating login goes against exchange rules ([thread](https://kite.trade/forum/discussion/13663/changing-access-token-expiry-to-midnight-instead-of-6am)).
  - **Only order endpoints check the static IP.** The websocket and data APIs work from any IP. You can register one primary and one secondary IP ([Zerodha support](https://support.zerodha.com/category/trading-and-markets/general-kite/kite-api/articles/static-ip)).
- **No sandbox** [M].
- **Pricing** [M]: Connect costs ₹500 per month per app and now includes live and historical data. The **Personal API is free** and covers orders, GTT and portfolio, but has no market data ([Zerodha support](https://support.zerodha.com/category/trading-and-markets/general-kite/kite-api/articles/what-are-the-charges-for-kite-apis)).
- **Instrument master** [M]: a daily CSV from `/instruments`. Each row has a Kite-internal `instrument_token`, the `exchange_token` and a compact `tradingsymbol`.

---

## 3. Regulatory overlay: SEBI retail algo framework, in force since 1 Apr 2026 [M]

Sources: [Zerodha overview](https://zerodha.com/z-connect/general/a-comprehensive-overview-of-nses-circular-on-the-new-retail-algo-trading-framework), [Zerodha newsletter](https://inthemoneybyzerodha.substack.com/p/sebi-algo-trading-changes-april-2026)

- Up to **10 orders/second per client, per exchange segment**: no strategy registration needed, and orders carry a generic exchange algo ID. Above 10/second the strategy must be registered with the exchange.
- Static IP is mandatory for orders: one primary plus one backup, changes at most weekly.
- One API key may be used for unregistered algos.
- Sessions must end before the next trading day.
- MARKET and SL-M orders require market protection.

**Design implications (judgment):**
- One **OrderGateway process per broker account**, enforcing a token bucket of about 8 orders/second across *all* systems trading that account.
- The gateway must run on the static-IP host. AWS Mumbai (ap-south-1) with an Elastic IP is the obvious choice, because it is also where the broker servers are.

---

## 4. What this means for 1–10 minute scalping

**Feed connection budget on one Upstox Plus account (judgment):**

| Connection | Mode | Keys | Purpose |
|---|---|---|---|
| C1 | `full_d30` | ≤50 | Today's focus list (5–15 names) plus index futures |
| C2 | `full` (5-level) | 100–300 | Candidates, sector leaders, F&O underlyings |
| C3 | `ltpc` | ~500 | Nifty 500 universe breadth, relative strength, RVOL |
| C4 | `option_greeks` | as needed | Later F&O phase |
| C5 | Reserve | — | Existing agent, or a hot-standby reconnect |

- Promote and demote names between d30 and full with `change_mode`, with a minimum stay of about 5 minutes so they don't flap.
- Combined-mode limits (2,000 / 1,500 / 1,500) are not binding at these sizes.

**REST budget is the real bottleneck.** If the 1,000 per 30 minutes figure holds, that is about 0.55 requests/second sustained, possibly shared with the existing agent.
- Polling the option chain for 20 stocks every minute would use 60% of it. So greeks and OI should come from the websocket; REST is only for snapshots every 3–5 minutes.
- **Backfill estimate:** Nifty 500 1-minute bars back to January 2022 is about 500 × 57 months ≈ 28,500 requests, roughly 14 hours under that limit. Run it as a weekend job.
- Kite historical at 3 requests/second could do the same backfill in about 1–2 hours. One ₹500 Kite Connect month would buy a deeper backfill plus a second vendor to cross-check candles.

**Paper fill realism (judgment):**
- Market orders: walk the d30 book.
- Limit orders: count as filled only when price trades through the limit, or when traded volume at the price exceeds the queue quantity seen at the moment we placed it.
- Add a latency model of feed conflation (100–500 ms) plus order round-trip (50–150 ms from a Mumbai VM).
- The paper adapter must also reproduce each target broker's rejections: SL-M on options, freeze-quantity slicing, tick-size and circuit limits, MPP leftovers, and the 10 orders/second cap.

**Recorder (judgment):**
- Persist every raw protobuf frame from day 1 of paper trading.
- Rough size: 50 d30 keys × about 4 messages/second × 22,500 seconds × about 1.2 KB ≈ 5 GB a day raw, about 1 GB a day zstd-compressed.
- This becomes the only realistic replay dataset for scalping unless you buy tick history from a vendor (GDFL, TrueData, or NSE's own data).

**Cost sensitivity** [estimate; check with the brokerage API]:
- On a ₹4 lakh intraday round trip, statutory charges are about ₹150 (STT 0.025% on the sell side, plus exchange, stamp and GST), on top of ₹40–60 brokerage.
- The ₹30-versus-₹20 brokerage gap costs about ₹400 a day at 20 round trips. That's roughly ₹8.8k a month, close to 0.9% of capital.

---

## 5. Adapter normalization and capability flags

**What the abstraction must normalize:**

| Area | Upstox | Kite | What the adapter does |
|---|---|---|---|
| Symbol | `NSE_EQ\|ISIN`, `NSE_FO\|exch_token` | numeric `instrument_token` + `tradingsymbol` | Canonical `InstrumentId` (exchange, segment, exchange_token), plus ISIN for equities; rebuilt daily from both masters; carries lot size, tick size and freeze quantity |
| Depth | 5 or 30 levels, no order count | 5 levels with order count | `Level(price, qty, orders: Optional[int])`; flag `depth_levels` |
| Timestamps | `ltt` (last trade time) + server `currentTs` | `last_trade_time` + `exchange_timestamp` | Store exchange time, broker time and local receive time; measure feed lag |
| Order status | lowercase strings ("open", "trigger pending", "put order req received"…) [M] | uppercase versions of the same family [M] | Map to: PENDING_NEW, OPEN, TRIGGER_PENDING, PARTIALLY_FILLED (derived from filled quantity > 0), FILLED, CANCEL_PENDING, CANCELLED, REJECTED, MODIFY_PENDING |
| Rejections | UDAPI codes plus raw RMS message | text exceptions | Normalized reject enum (MARGIN, PRICE_BAND, ORDER_TYPE_NOT_ALLOWED, RATE_LIMIT, IP_BLOCKED…) plus the raw text |
| Slicing | `slice=true`, list of `order_ids` | `autoslice`, parent ID plus children | Logical parent order → child fills; fill-weighted average price |
| Market orders | MPP automatic or parameter | `market_protection` required | Prefer marketable LIMIT/IOC with our own price cap |
| Bracket | GTT with 3 legs (ENTRY required) | GTT OCO, CO variety | **Synthetic bracket in our order manager**: entry → exchange-resident SL plus target limit; our code handles OCO and over-fill flattening |
| Idempotency | `tag`, `correlation_id` (multi-order) | `tag` | Encode a short client order ID in `tag` so a crash can be reconciled from the order book |

**Capability flags sketch:**
```yaml
broker_caps:
  upstox: {order_types: [LIMIT,MARKET,SL,SL_M], sl_m_options: false, validity: [DAY,IOC],
           autoslice: {native: true, max_children: 25}, multi_order: 25, gtt: [single, three_leg_entry_required],
           market_protection: auto_or_param, order_stream: [ws, webhook], latency_in_response: true,
           sandbox: schema_only, ops_cap: 10}
  kite:   {validity: [DAY,IOC,TTL], iceberg: true, autoslice: {native: true}, multi_order: false,
           gtt: [single, oco], market_protection: required_param, order_stream: [ws, postback], sandbox: none}
data_caps:
  upstox: {depth_max: 30, depth_orders: false, depth30_keys: 50, conns: 5, tbt: false, greeks_in_feed: true,
           option_chain_api: true, expired_fo_candles: true, min_bar: 1m}
  kite:   {depth_max: 5, depth_orders: true, conns: 3, keys_per_conn: 3000, tbt: false, greeks_in_feed: false,
           option_chain_api: false, expired_options: false}
```

**How strategies use the flags:**
- Each strategy declares what it requires, for example `requires: {depth_max: ">=20", tbt: false}`.
- At startup a negotiator checks those requirements against the configured adapters. It then either runs the strategy, switches it to a degraded variant (such as a 5-level-depth version), or refuses to start.
- A `CompositeDataRouter` picks a provider per capability: depth30 and option chain from Upstox, a backup LTP feed from Kite.
- `paper` is a full `BrokerAdapter` configured to copy one live broker (`paper.emulate: upstox|kite`), so paper results carry over to live.

---

## 6. Which broker for data and which for execution

- **Data: Upstox, clearly.**
  - Only it has 30-level depth, greeks in the feed, REST analytics, expired F&O contracts, custom-interval history and a 24x7 read-only token.
  - Kite is the secondary feed. It cross-checks prices, and its per-level order counts help detect spoofing.
- **Execution: build both adapters.**
  - **If the existing options agent is on the same Upstox account, I recommend Zerodha for the new system's executions.** That isolates the two agents' margin, kill switches, order-rate budgets and app or token conflicts. It is also cheaper per order, and the Personal API is free.
  - Otherwise use Upstox, with one shared TokenService and one OrderGateway serving both agents.
  - Either way, stops sit at the exchange as SL (limit) orders, because SL-M is rejected on options. GTT is used only for swing positions held overnight.

---

## 7. Open questions for you

1. Does the existing options-selling agent trade **the same Upstox account and app**? This decides whether the new system executes on Zerodha or shares a gateway and token with it.
2. Do you have a funded Zerodha account, and are you willing to split the ₹10 lakh capital between brokers?
3. Can you approve a token on your phone every trading morning, around 08:30–08:50, for Upstox's approval flow and/or Kite's TOTP login? Who approves when you are travelling? The fallback is no trading that day.
4. Are you OK hosting on a Mumbai cloud VM with an Elastic IP, at roughly ₹2–4k a month, given that both brokers must whitelist that IP?
5. What brokerage does your contract note show per API order on Plus: ₹10, ₹20 or ₹30?
6. Is your 50-instrument 30-depth allowance already used by the existing agent or other tools?
7. For scalping research, will you pay for vendor tick history, or accept 4–8 weeks of our own recording before the first scalping backtests?
8. For overnight swing trades: CNC (no leverage) or MTF (leverage, plus interest and eligibility rules)? This sets the product mapping and margin checks.
9. Should the Phase-2 F&O plans assume stock-option scalping? That brings in the SL-M ban, automatic protection and freeze-quantity slicing on day one.