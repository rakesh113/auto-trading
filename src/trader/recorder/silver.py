"""Silver tier and end-of-day housekeeping (design §11).

After each session:
  1. Decode the day's bronze frames once → Parquet (silver) + data-quality report.
  2. Delete bronze days older than `bronze_retention_days`, only if their silver exists.
  3. Copy new silver/reference/report files to `backup_dir`, if one is configured.

Silver layout: ``<data_dir>/silver/<YYYY-MM-DD>/<stream>.parquet``, one row per quote,
instruments resolved with that day's own master (point-in-time). Depth is stored as
list columns; prices are paise.
"""

from __future__ import annotations

import gzip
import json
import shutil
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq
import structlog

from trader.adapters.upstox.instruments import UpstoxInstrumentMaster
from trader.domain.market import MarketEvent, Quote
from trader.recorder.dq import analyze_day

log = structlog.get_logger(__name__)

SCHEMA = pa.schema([
    ("ts_recv_ns", pa.int64()), ("ts_server_ms", pa.int64()), ("ts_exch_ms", pa.int64()),
    ("native", pa.string()), ("iid", pa.string()), ("mode", pa.string()), ("snapshot", pa.bool_()),
    ("ltp", pa.int64()), ("ltq", pa.int64()), ("prev_close", pa.int64()),
    ("volume", pa.int64()), ("oi", pa.float64()), ("iv", pa.float64()), ("atp", pa.int64()),
    ("total_buy_qty", pa.float64()), ("total_sell_qty", pa.float64()),
    ("iep", pa.int64()), ("ieq", pa.int64()),
    ("bid_px", pa.list_(pa.int64())), ("bid_qty", pa.list_(pa.int64())),
    ("ask_px", pa.list_(pa.int64())), ("ask_qty", pa.list_(pa.int64())),
    ("delta", pa.float64()), ("theta", pa.float64()), ("gamma", pa.float64()), ("vega", pa.float64()),
    ("bar1m_ts", pa.int64()), ("bar1m_o", pa.int64()), ("bar1m_h", pa.int64()), ("bar1m_l", pa.int64()),
    ("bar1m_c", pa.int64()), ("bar1m_v", pa.int64()),
])
_BATCH = 100_000


class _StreamWriter:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.tmp = path.with_suffix(".parquet.part")
        self._w = pq.ParquetWriter(self.tmp, SCHEMA, compression="zstd", compression_level=6)
        self._rows: dict[str, list[Any]] = {f.name: [] for f in SCHEMA}
        self.count = 0

    def add(self, q: Quote) -> None:
        r = self._rows
        r["ts_recv_ns"].append(q.ts_recv_ns)
        r["ts_server_ms"].append(q.ts_server_ms)
        r["ts_exch_ms"].append(q.ts_exch_ms)
        r["native"].append(q.native)
        r["iid"].append(str(q.iid) if q.iid else None)
        r["mode"].append(q.mode.value)
        r["snapshot"].append(q.snapshot)
        r["ltp"].append(q.ltp)
        r["ltq"].append(q.ltq)
        r["prev_close"].append(q.prev_close)
        r["volume"].append(q.volume)
        r["oi"].append(q.oi)
        r["iv"].append(q.iv)
        r["atp"].append(q.atp)
        r["total_buy_qty"].append(q.total_buy_qty)
        r["total_sell_qty"].append(q.total_sell_qty)
        r["iep"].append(q.iep)
        r["ieq"].append(q.ieq)
        r["bid_px"].append([lv.price for lv in q.bids] if q.bids else None)
        r["bid_qty"].append([lv.qty for lv in q.bids] if q.bids else None)
        r["ask_px"].append([lv.price for lv in q.asks] if q.asks else None)
        r["ask_qty"].append([lv.qty for lv in q.asks] if q.asks else None)
        g = q.greeks
        r["delta"].append(g.delta if g else None)
        r["theta"].append(g.theta if g else None)
        r["gamma"].append(g.gamma if g else None)
        r["vega"].append(g.vega if g else None)
        bar = next((b for b in q.bars if b.interval == "I1"), None)
        r["bar1m_ts"].append(bar.ts_ms if bar else None)
        r["bar1m_o"].append(bar.open if bar else None)
        r["bar1m_h"].append(bar.high if bar else None)
        r["bar1m_l"].append(bar.low if bar else None)
        r["bar1m_c"].append(bar.close if bar else None)
        r["bar1m_v"].append(bar.volume if bar else None)
        self.count += 1
        if len(r["ts_recv_ns"]) >= _BATCH:
            self.flush()

    def flush(self) -> None:
        if self._rows["ts_recv_ns"]:
            self._w.write_table(pa.table(self._rows, schema=SCHEMA))
            self._rows = {f.name: [] for f in SCHEMA}

    def close(self) -> None:
        self.flush()
        self._w.close()
        self.tmp.replace(self.path)


def build_silver(data_dir: Path, day: date) -> dict[str, Any]:
    """Decode bronze for `day` into silver Parquet and return the data-quality report."""
    data_dir = Path(data_dir)
    out = data_dir / "silver" / day.isoformat()
    out.mkdir(parents=True, exist_ok=True)
    master = UpstoxInstrumentMaster(data_dir=data_dir, url="")
    resolve = None
    if master.path_for(day).exists():
        master.load_rows(json.loads(gzip.decompress(master.path_for(day).read_bytes())))
        resolve = master.from_native
    else:
        log.warning("silver.no_master", day=str(day))
    writers: dict[str, _StreamWriter] = {}

    def sink(stream: str, events: list[MarketEvent]) -> None:
        w = writers.get(stream)
        if w is None:
            w = writers[stream] = _StreamWriter(out / f"{stream}.parquet")
        for ev in events:
            if isinstance(ev, Quote):
                w.add(ev)

    try:
        report = analyze_day(data_dir, day, resolve=resolve, sink=sink)
    finally:
        for w in writers.values():
            w.close()
    report["silver_rows"] = {k: w.count for k, w in writers.items()}
    (out / "_SUCCESS").write_text(json.dumps(report["silver_rows"]), encoding="utf-8")
    reports = data_dir / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    (reports / f"dq-{day.isoformat()}.json").write_text(json.dumps(report, indent=1, default=str), encoding="utf-8")
    return report


def prune_bronze(data_dir: Path, today: date, keep_days: int) -> list[str]:
    """Delete bronze days older than `keep_days` whose silver conversion succeeded."""
    removed = []
    root = Path(data_dir) / "bronze"
    if not root.exists():
        return removed
    cutoff = today - timedelta(days=keep_days)
    for d in sorted(p for p in root.iterdir() if p.is_dir()):
        try:
            day = date.fromisoformat(d.name)
        except ValueError:
            continue
        if day < cutoff and (Path(data_dir) / "silver" / d.name / "_SUCCESS").exists():
            shutil.rmtree(d)
            removed.append(d.name)
    if removed:
        log.info("bronze.pruned", days=removed)
    return removed


def backup(data_dir: Path, dest: Path, subdirs: tuple[str, ...] = ("silver", "reference", "reports")) -> int:
    """Copy files missing (or changed in size) at `dest`. Returns the number copied."""
    copied = 0
    for sub in subdirs:
        src_root = Path(data_dir) / sub
        if not src_root.exists():
            continue
        for f in src_root.rglob("*"):
            if not f.is_file() or f.suffix == ".part":
                continue
            target = Path(dest) / sub / f.relative_to(src_root)
            if target.exists() and target.stat().st_size == f.stat().st_size:
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(f, target)
            copied += 1
    log.info("backup.done", dest=str(dest), copied=copied)
    return copied


def disk_free_gb(path: Path) -> float:
    return shutil.disk_usage(path).free / 2**30
