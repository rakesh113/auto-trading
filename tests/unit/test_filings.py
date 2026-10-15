from __future__ import annotations

from datetime import date

import httpx

from trader.intel.filings import BseFilings, Filing, FilingStore, NseFilings

NSE_ROW = {"symbol": "SUBEXLTD", "sm_name": "Subex Limited", "desc": "Awarding of order(s)/contract(s)",
           "attchmntText": "Subex has received an order worth Rs 120 crore", "seq_id": "106812001",
           "exchdisstime": "09-Oct-2026 11:02:03", "an_dt": "09-Oct-2026 11:02:01", "sm_isin": "INE754A01055",
           "attchmntFile": "https://nsearchives.nseindia.com/x.pdf"}
BSE_ROW = {"NEWSID": "8c5e", "SCRIP_CD": 532348, "NEWSSUB": "Subex Ltd - 532348 - Award of Order",
           "DT_TM": "2026-10-09T11:02:30.837", "HEADLINE": "Subex has received an order worth Rs 120 crore",
           "CATEGORYNAME": "Company Update", "ATTACHMENTNAME": "a.pdf", "MORE": ""}


def transport() -> httpx.MockTransport:
    def h(req: httpx.Request) -> httpx.Response:
        if "corporate-announcements" in req.url.path:
            return httpx.Response(200, json=[NSE_ROW])
        if "AnnSubCategoryGetData" in req.url.path:
            return httpx.Response(200, json={"Table": [BSE_ROW]})
        return httpx.Response(200, text="<html></html>")

    return httpx.MockTransport(h)


async def test_parse_nse_and_bse() -> None:
    (n,) = await NseFilings(transport=transport()).fetch(5, date(2026, 10, 9))
    assert n.symbol == "SUBEXLTD" and n.isin == "INE754A01055" and not n.routine and n.first_seen_ns == 5
    (b,) = await BseFilings(transport=transport()).fetch(6, date(2026, 10, 9))
    assert b.symbol == "532348" and b.exchange == "BSE" and b.attachment.endswith("a.pdf")


def _f(key: str, cat: str, head: str, seen: int, isin: str = "INE1") -> Filing:
    return Filing("NSE", key, "X", isin, "X Ltd", cat, head, "", "", seen, seen)


def test_routine_filter() -> None:
    assert _f("1", "Certificate under SEBI (Depositories and Participants) Regulations, 2018", "", 1).routine
    assert _f("2", "Copy of Newspaper Publication", "", 1).routine
    assert not _f("3", "Awarding of order(s)/contract(s)", "", 1).routine
    assert not _f("4", "Outcome of Board Meeting", "Financial results", 1).routine
    assert not _f("5", "Acquisition", "Medicine maker acquisition", 1).routine  # 'cin' inside a word


def test_store_dedupes_and_windows(tmp_path) -> None:
    s = FilingStore(tmp_path / "f.sqlite")
    a = _f("1", "Acquisition", "Buys Y", 100)
    assert s.add(a, "NSE:EQ:X") and not s.add(a, "NSE:EQ:X")
    cross = Filing("BSE", "z", "500", "INE1", "X", "Company Update", "Buys Y", "", "", 150, 150)
    assert s.add(cross, "NSE:EQ:X")  # stored, but marked routine as a cross-listed duplicate
    assert [k for *_x, k in s.material_candidates(0, 1000)] == ["NSE:1"]
    assert s.material_candidates(100, 1000) == []  # window excludes first_seen == since


def test_backfilled_old_news_is_not_fresh(tmp_path) -> None:
    s = FilingStore(tmp_path / "f.sqlite")
    old = Filing("NSE", "9", "X", "INE9", "X", "Acquisition", "Old deal", "", "", ts_exchange_ns=0,
                 first_seen_ns=int(3600e9))
    fresh = Filing("NSE", "10", "Y", "INE10", "Y", "Acquisition", "New deal", "", "", ts_exchange_ns=int(3590e9),
                   first_seen_ns=int(3600e9))
    s.add(old, "NSE:EQ:X")
    s.add(fresh, "NSE:EQ:Y")
    assert [k for *_x, k in s.material_candidates(0, int(4000e9), max_age_s=600)] == ["NSE:10"]
