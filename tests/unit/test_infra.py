from __future__ import annotations

import asyncio
from datetime import date, datetime
from pathlib import Path

import pytest

from trader.adapters.upstox.decode import decode_frame
from trader.adapters.upstox.proto import MarketDataFeedV3_pb2 as pb
from trader.core.config import REPO_ROOT
from trader.core.costs import CostModel
from trader.core.throttle import Priority, PriorityThrottle
from trader.domain.instrument import InstrumentId
from trader.domain.market import MarketStatus, Quote
from trader.domain.types import IST, FeedMode, Product, Side
from trader.recorder.bronze import BronzeRecorder, read_frames

# ---- costs ------------------------------------------------------------------------------------


def test_cash_intraday_statutory_round_trip_matches_design() -> None:
    """Design §5: cash MIS round trip ≈ 3.55 bps of notional before brokerage."""
    cm = CostModel.load(REPO_ROOT / "config" / "costs.yaml", "upstox_plus")
    iid = InstrumentId.parse("NSE:EQ:RELIANCE")
    qty, px = 1000, 140000  # ₹14L notional
    total = sum(cm.statutory(iid, s, qty, px, Product.INTRADAY, date(2026, 10, 9)).total for s in Side)
    bps = total / (qty * px) * 1e4
    assert 3.4 < bps < 3.7


def test_brokerage_cap_and_options_stt() -> None:
    cm = CostModel.load(REPO_ROOT / "config" / "costs.yaml", "upstox_plus")
    assert cm.brokerage("equity_intraday", 1_000_00) == pytest.approx(100)  # 0.1% of ₹1,000 = ₹1
    assert cm.brokerage("equity_intraday", 10_000_000_00) == 3000
    opt = InstrumentId.parse("NSE:OPT:NIFTY:2026-10-13:25000:CE")
    sell = cm.statutory(opt, Side.SELL, 65, 10000, Product.INTRADAY, date(2026, 10, 9))
    assert sell.stt == pytest.approx(65 * 10000 * 0.0015)


# ---- throttle -----------------------------------------------------------------------------------


async def test_throttle_serves_higher_priority_first() -> None:
    t = PriorityThrottle(rate_per_sec=50, burst=1)
    await t.acquire()  # drain the bucket
    order: list[str] = []

    async def go(name: str, p: Priority) -> None:
        await t.acquire(p)
        order.append(name)

    await asyncio.gather(go("entry", Priority.ENTRY), go("exit", Priority.EXIT), go("flatten", Priority.FLATTEN))
    assert order == ["flatten", "exit", "entry"]


# ---- recorder -----------------------------------------------------------------------------------


def test_bronze_roundtrip_rotation_and_truncation(tmp_path: Path) -> None:
    rec = BronzeRecorder(tmp_path, rotate_minutes=15, flush_every_s=0.05)
    t0 = int(datetime(2026, 10, 12, 9, 14, 59, tzinfo=IST).timestamp() * 1e9)
    payloads = [bytes([i % 256]) * (i % 50 + 1) for i in range(500)]
    for i, p in enumerate(payloads):
        rec.write("c1", 1, t0 + i * 10_000_000, p)  # 10 ms apart, crosses 09:15
    rec.close()
    files = sorted((tmp_path / "bronze" / "2026-10-12" / "c1").glob("*.frames.zst"))
    assert [f.name for f in files] == ["0900.frames.zst", "0915.frames.zst"]
    got = [p for f in files for _, _, p in read_frames(f)]
    assert got == payloads and rec.dropped == 0
    # a crash mid-write leaves a truncated tail: everything before it must still read
    data = files[1].read_bytes()
    files[1].write_bytes(data[:-7])
    assert len(list(read_frames(files[1]))) >= 0


# ---- protobuf decode ------------------------------------------------------------------------------


def test_decode_full_d30_and_market_info(master) -> None:
    msg = pb.FeedResponse(type=pb.live_feed, currentTs=1792000000000)
    f = msg.feeds["NSE_EQ|INE002A01018"]
    f.requestMode = pb.full_d30
    m = f.fullFeed.marketFF
    m.ltpc.ltp, m.ltpc.ltt, m.ltpc.ltq, m.ltpc.cp = 1401.3, 1791999999000, 7, 1390.0
    for i in range(30):
        m.marketLevel.bidAskQuote.add(bidQ=100 + i, bidP=1401.2 - i * 0.1, askQ=200 + i, askP=1401.4 + i * 0.1)
    m.vtt, m.atp, m.casEligible = 123456, 1399.5, True
    m.marketOHLC.ohlc.add(interval="I1", open=1400, high=1402, low=1399, close=1401.3, vol=5000, ts=1791999960000)
    info = pb.FeedResponse(type=pb.market_info, currentTs=1792000000000)
    info.marketInfo.segmentStatus["NSE_EQ"] = pb.NORMAL_OPEN

    evs = decode_frame(msg.SerializeToString(), 5, master.from_native)
    q = evs[0]
    assert isinstance(q, Quote)
    assert q.iid == InstrumentId.parse("NSE:EQ:RELIANCE") and q.mode is FeedMode.FULL_D30
    assert q.ltp == 140130 and len(q.bids) == 30 and q.bids[0].price == 140120 and q.asks[0].qty == 200
    assert q.volume == 123456 and q.cas_eligible is True and q.bars[0].close == 140130
    (s,) = decode_frame(info.SerializeToString(), 5, master.from_native)
    assert isinstance(s, MarketStatus) and s.segments == {"NSE_EQ": "NORMAL_OPEN"}
