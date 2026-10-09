"""NSE and BSE corporate announcements (design §11 filings and news).

* Polled every 5–10 s in market hours, 30–60 s in the evening (results season).
* Three timestamps per filing: exchange dissemination, our first-seen, and (for the
  record) the source's own sort time. `first_seen_ns` is what replay uses (no look-ahead).
* De-duplicated by (exchange, id); cross-listed duplicates collapse on ISIN + headline.
* Routine categories are dropped by rule before any model sees them.
* Scraped text is untrusted data: stored and passed to models only as delimited input.

NSE needs a cookie from its own pages before the JSON API answers; BSE needs a Referer.
NSE reportedly blocks cloud IP ranges, which is one reason ingestion runs on the laptop.
"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from dataclasses import asdict, dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

import httpx
import structlog

from trader.domain.types import IST

log = structlog.get_logger(__name__)

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/129.0 Safari/537.36", "Accept": "application/json, text/plain, */*",
      "Accept-Language": "en-US,en;q=0.9"}

ROUTINE = re.compile(
    r"certificate under (sebi )?\(?(depositories|dp)|reg(ulation)?\.? ?74 ?\(5\)|newspaper|trading window|"
    r"loss of share|duplicate share|investor (meet|presentation)|analysts?/institutional|con\. call|"
    r"change in (the )?corporate identification|\bcin\b|esop|esos|allotment of (securities|equity shares) under|"
    r"compliance certificate|closure of trading|book closure|record date|postal ballot|"
    r"statement of deviation|reg\.? ?32|shareholding pattern|voting results|scrutinizer|"
    r"intimation of (agm|egm)|notice of (agm|egm)|annual report|change in registrar|"
    r"certificate under reg|secretarial compliance", re.I)


@dataclass(frozen=True)
class Filing:
    exchange: str  # NSE | BSE
    id: str
    symbol: str  # NSE symbol, or BSE scrip code
    isin: str
    company: str
    category: str
    headline: str
    text: str
    attachment: str
    ts_exchange_ns: int
    first_seen_ns: int

    @property
    def key(self) -> str:
        return f"{self.exchange}:{self.id}"

    @property
    def content_hash(self) -> str:
        return hashlib.sha1(f"{self.isin}|{self.headline.lower().strip()}".encode()).hexdigest()[:16]

    @property
    def routine(self) -> bool:
        return bool(ROUTINE.search(f"{self.category} {self.headline}"))


def _ns(dt: datetime) -> int:
    return int(dt.timestamp() * 1e9)


class NseFilings:
    PAGE = "https://www.nseindia.com/companies-listing/corporate-filings-announcements"
    API = "https://www.nseindia.com/api/corporate-announcements"

    def __init__(self, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self._c = httpx.AsyncClient(timeout=20, headers=UA, follow_redirects=True, transport=transport)
        self._warm = False

    async def fetch(self, now_ns: int, day: date | None = None) -> list[Filing]:
        if not self._warm:
            await self._c.get(self.PAGE)
            self._warm = True
        params: dict[str, str] = {"index": "equities"}
        if day is not None:
            params |= {"from_date": day.strftime("%d-%m-%Y"), "to_date": day.strftime("%d-%m-%Y")}
        r = await self._c.get(self.API, params=params, headers={"Referer": self.PAGE})
        if r.status_code in (401, 403):
            self._warm = False  # cookie expired: re-warm next time
        r.raise_for_status()
        out = []
        for x in r.json():
            try:
                t = datetime.strptime(x.get("exchdisstime") or x["an_dt"], "%d-%b-%Y %H:%M:%S").replace(tzinfo=IST)
            except (KeyError, ValueError):
                continue
            out.append(Filing("NSE", str(x["seq_id"]), (x.get("symbol") or "").upper(), x.get("sm_isin") or "",
                              x.get("sm_name") or "", x.get("desc") or "", x.get("desc") or "",
                              x.get("attchmntText") or "", x.get("attchmntFile") or "", _ns(t), now_ns))
        return out


class BseFilings:
    API = "https://api.bseindia.com/BseIndiaAPI/api/AnnSubCategoryGetData/w"

    def __init__(self, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self._c = httpx.AsyncClient(timeout=20, headers=UA | {"Referer": "https://www.bseindia.com/",
                                                               "Origin": "https://www.bseindia.com"},
                                    transport=transport)

    async def fetch(self, now_ns: int, day: date) -> list[Filing]:
        d = day.strftime("%Y%m%d")
        r = await self._c.get(self.API, params={"pageno": 1, "strCat": "-1", "strPrevDate": d, "strScrip": "",
                                                "strSearch": "P", "strToDate": d, "strType": "C",
                                                "subcategory": "-1"})
        r.raise_for_status()
        out = []
        for x in (r.json() or {}).get("Table") or []:
            try:
                t = datetime.fromisoformat(x["DT_TM"][:19]).replace(tzinfo=IST)
            except (KeyError, ValueError):
                continue
            att = x.get("ATTACHMENTNAME") or ""
            url = f"https://www.bseindia.com/xml-data/corpfiling/AttachLive/{att}" if att else ""
            out.append(Filing("BSE", str(x["NEWSID"]), str(x.get("SCRIP_CD") or ""), "", (x.get("NEWSSUB") or "")[:120],
                              x.get("CATEGORYNAME") or "", x.get("HEADLINE") or x.get("NEWSSUB") or "",
                              x.get("MORE") or "", url, _ns(t), now_ns))
        return out


class FilingStore:
    """SQLite store shared by the intel process (writer) and the engine (reader)."""

    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self._db = sqlite3.connect(path, isolation_level=None, check_same_thread=False, timeout=10)
        self._db.execute("PRAGMA journal_mode=WAL")
        self._db.execute("""CREATE TABLE IF NOT EXISTS filings (key TEXT PRIMARY KEY, exchange TEXT, symbol TEXT,
            isin TEXT, iid TEXT, routine INTEGER, content_hash TEXT, first_seen_ns INTEGER, ts_exchange_ns INTEGER,
            data TEXT)""")
        self._db.execute("CREATE INDEX IF NOT EXISTS f_seen ON filings(first_seen_ns)")
        self._db.execute("""CREATE TABLE IF NOT EXISTS triage (key TEXT, model TEXT, ts_ns INTEGER, latency_ms REAL,
            cost_usd REAL, result TEXT, PRIMARY KEY (key, model))""")

    def add(self, f: Filing, iid: str | None) -> bool:
        """Insert if new (and not a cross-listed duplicate seen in the last hour). True if inserted."""
        dup = self._db.execute("SELECT 1 FROM filings WHERE content_hash=? AND isin<>'' AND first_seen_ns>?",
                               (f.content_hash, f.first_seen_ns - int(3600e9))).fetchone()
        cur = self._db.execute(
            "INSERT OR IGNORE INTO filings VALUES (?,?,?,?,?,?,?,?,?,?)",
            (f.key, f.exchange, f.symbol, f.isin, iid, int(f.routine or bool(dup)), f.content_hash, f.first_seen_ns,
             f.ts_exchange_ns, json.dumps(asdict(f))))
        return cur.rowcount == 1

    def seen(self, key: str) -> bool:
        return self._db.execute("SELECT 1 FROM filings WHERE key=?", (key,)).fetchone() is not None

    def material_candidates(self, since_ns: int, until_ns: int) -> list[tuple[str, int, str]]:
        """(iid, first_seen_ns, key) of non-routine filings on mapped instruments in a window."""
        cur = self._db.execute("SELECT iid, first_seen_ns, key FROM filings WHERE iid IS NOT NULL AND routine=0 "
                               "AND first_seen_ns>? AND first_seen_ns<=? ORDER BY first_seen_ns", (since_ns, until_ns))
        return list(cur)

    def record_triage(self, key: str, model: str, ts_ns: int, latency_ms: float, cost: float | None,
                      result: dict[str, Any]) -> None:
        self._db.execute("INSERT OR REPLACE INTO triage VALUES (?,?,?,?,?,?)",
                         (key, model, ts_ns, latency_ms, cost, json.dumps(result)))

    def get(self, key: str) -> Filing:
        (data,) = self._db.execute("SELECT data FROM filings WHERE key=?", (key,)).fetchone()
        return Filing(**json.loads(data))

    def close(self) -> None:
        self._db.close()
