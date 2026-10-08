"""Upstox V3 protobuf frames → normalized market events.

Kept separate from the websocket code so replay can decode recorded bronze frames
with exactly the same function as the live feed.
"""

from __future__ import annotations

from collections.abc import Callable

from trader.adapters.upstox.proto import MarketDataFeedV3_pb2 as pb
from trader.domain.instrument import InstrumentId
from trader.domain.market import Bar, DepthLevel, Greeks, MarketEvent, MarketStatus, Quote
from trader.domain.types import FeedMode

_MODE = {
    pb.ltpc: FeedMode.LTPC,
    pb.full_d5: FeedMode.FULL,
    pb.option_greeks: FeedMode.OPTION_GREEKS,
    pb.full_d30: FeedMode.FULL_D30,
}
_STATUS = {v.number: v.name for v in pb.MarketStatus.DESCRIPTOR.values}

Resolver = Callable[[str], InstrumentId | None]


def _p(x: float) -> int:
    return int(round(x * 100))


def _depth(levels) -> tuple[tuple[DepthLevel, ...], tuple[DepthLevel, ...]]:
    bids: list[DepthLevel] = []
    asks: list[DepthLevel] = []
    for q in levels:
        if q.bidQ > 0 and q.bidP > 0:
            bids.append(DepthLevel(_p(q.bidP), int(q.bidQ)))
        if q.askQ > 0 and q.askP > 0:
            asks.append(DepthLevel(_p(q.askP), int(q.askQ)))
    return tuple(bids), tuple(asks)


def _bars(ohlc) -> tuple[Bar, ...]:
    return tuple(
        Bar(interval=o.interval, ts_ms=int(o.ts), open=_p(o.open), high=_p(o.high), low=_p(o.low),
            close=_p(o.close), volume=int(o.vol))
        for o in ohlc
    )


def _greeks(g) -> Greeks:
    return Greeks(delta=g.delta, theta=g.theta, gamma=g.gamma, vega=g.vega, rho=g.rho)


def decode_frame(payload: bytes, ts_recv_ns: int, resolve: Resolver) -> list[MarketEvent]:
    msg = pb.FeedResponse()
    msg.ParseFromString(payload)
    out: list[MarketEvent] = []
    server_ms = int(msg.currentTs)
    if msg.type == pb.market_info or msg.HasField("marketInfo"):
        segs = {k: _STATUS.get(v, str(v)) for k, v in msg.marketInfo.segmentStatus.items()}
        if segs:
            out.append(MarketStatus(ts_server_ms=server_ms, ts_recv_ns=ts_recv_ns, segments=segs))
    snapshot = msg.type == pb.initial_feed
    for key, feed in msg.feeds.items():
        q = _quote(key, feed, server_ms, ts_recv_ns, resolve)
        if q is not None:
            q.snapshot = snapshot
            out.append(q)
    return out


def _quote(key: str, feed, server_ms: int, ts_recv_ns: int, resolve: Resolver) -> Quote | None:
    which = feed.WhichOneof("FeedUnion")
    mode = _MODE.get(feed.requestMode, FeedMode.LTPC)
    iid = resolve(key)
    if which == "ltpc":
        lt = feed.ltpc
        return Quote(iid=iid, native=key, mode=FeedMode.LTPC, ts_exch_ms=int(lt.ltt), ts_server_ms=server_ms,
                     ts_recv_ns=ts_recv_ns, ltp=_p(lt.ltp), ltq=int(lt.ltq), prev_close=_p(lt.cp),
                     iep=_p(lt.iep.value) if lt.HasField("iep") else None)
    if which == "firstLevelWithGreeks":
        f = feed.firstLevelWithGreeks
        lt = f.ltpc
        bids, asks = _depth([f.firstDepth])
        return Quote(iid=iid, native=key, mode=FeedMode.OPTION_GREEKS, ts_exch_ms=int(lt.ltt),
                     ts_server_ms=server_ms, ts_recv_ns=ts_recv_ns, ltp=_p(lt.ltp), ltq=int(lt.ltq),
                     prev_close=_p(lt.cp), bids=bids, asks=asks, volume=int(f.vtt), oi=f.oi, iv=f.iv,
                     greeks=_greeks(f.optionGreeks) if f.HasField("optionGreeks") else None)
    if which == "fullFeed":
        ff = feed.fullFeed
        if ff.WhichOneof("FullFeedUnion") == "indexFF":
            x = ff.indexFF
            lt = x.ltpc
            return Quote(iid=iid, native=key, mode=mode, ts_exch_ms=int(lt.ltt), ts_server_ms=server_ms,
                         ts_recv_ns=ts_recv_ns, ltp=_p(lt.ltp), ltq=int(lt.ltq), prev_close=_p(lt.cp),
                         bars=_bars(x.marketOHLC.ohlc))
        m = ff.marketFF
        lt = m.ltpc
        bids, asks = _depth(m.marketLevel.bidAskQuote)
        return Quote(iid=iid, native=key, mode=mode, ts_exch_ms=int(lt.ltt), ts_server_ms=server_ms,
                     ts_recv_ns=ts_recv_ns, ltp=_p(lt.ltp), ltq=int(lt.ltq), prev_close=_p(lt.cp),
                     bids=bids, asks=asks, atp=_p(m.atp), volume=int(m.vtt), oi=m.oi, iv=m.iv,
                     total_buy_qty=m.tbq, total_sell_qty=m.tsq,
                     greeks=_greeks(m.optionGreeks) if m.HasField("optionGreeks") else None,
                     bars=_bars(m.marketOHLC.ohlc),
                     iep=_p(m.iep) if m.iep else None, ieq=int(m.ieq) if m.ieq else None,
                     cas_eligible=m.casEligible)
    return None
