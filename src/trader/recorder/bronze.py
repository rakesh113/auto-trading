"""Bronze tier: raw venue frames, exactly as received (design D7, §11).

Layout: ``<data_dir>/bronze/<YYYY-MM-DD>/<stream>/<HHMM>.frames.zst``, rotated every
`rotate_minutes` (IST). Each record is::

    int64 ts_recv_ns | uint16 kind | uint32 length | payload

Files are zstd-compressed and flushed as a complete zstd frame every `flush_every_s`,
so a crash or power cut loses at most a couple of seconds and leaves every file
readable. Writes go through a queue to a background thread, so the feed never waits
on the disk.
"""

from __future__ import annotations

import queue
import struct
import threading
import time
from collections.abc import Iterator
from datetime import datetime
from pathlib import Path
from typing import BinaryIO

import structlog
import zstandard as zstd

from trader.domain.types import IST
from trader.ports.infra import RawRecorder

log = structlog.get_logger(__name__)

HEADER = struct.Struct("<qHI")
_STOP = object()


class _Segment:
    def __init__(self, path: Path, level: int) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self._fh: BinaryIO = open(path, "ab")  # noqa: SIM115 - closed in close()
        self._w = zstd.ZstdCompressor(level=level).stream_writer(self._fh, closefd=False)
        self.records = 0

    def write(self, ts: int, kind: int, payload: bytes) -> None:
        self._w.write(HEADER.pack(ts, kind, len(payload)))
        self._w.write(payload)
        self.records += 1

    def flush(self) -> None:
        self._w.flush(zstd.FLUSH_FRAME)
        self._fh.flush()

    def close(self) -> None:
        self._w.flush(zstd.FLUSH_FRAME)
        self._w.close()
        self._fh.close()


class BronzeRecorder(RawRecorder):
    def __init__(self, data_dir: Path, *, rotate_minutes: int = 15, zstd_level: int = 3,
                 flush_every_s: float = 2.0, max_queue: int = 1_000_000) -> None:
        self.root = Path(data_dir) / "bronze"
        self.rotate_minutes = rotate_minutes
        self.level = zstd_level
        self.flush_every_s = flush_every_s
        self._q: queue.Queue[object] = queue.Queue(maxsize=max_queue)
        self._segments: dict[str, tuple[str, _Segment]] = {}  # stream -> (window key, segment)
        self.dropped = 0
        self.written = 0
        self._thread = threading.Thread(target=self._run, name="bronze-recorder", daemon=True)
        self._thread.start()

    def path_for(self, stream: str, ts_ns: int) -> tuple[str, Path]:
        t = datetime.fromtimestamp(ts_ns / 1e9, IST)
        minute = (t.hour * 60 + t.minute) // self.rotate_minutes * self.rotate_minutes
        key = f"{t.date().isoformat()}/{minute // 60:02d}{minute % 60:02d}"
        day, hhmm = key.split("/")
        return key, self.root / day / stream / f"{hhmm}.frames.zst"

    def write(self, stream: str, kind: int, ts_recv_ns: int, payload: bytes) -> None:
        try:
            self._q.put_nowait((stream, kind, ts_recv_ns, payload))
        except queue.Full:
            self.dropped += 1

    def close(self) -> None:
        self._q.put(_STOP)
        self._thread.join(timeout=30)

    def _run(self) -> None:
        last_flush = time.monotonic()
        while True:
            try:
                item = self._q.get(timeout=self.flush_every_s)
            except queue.Empty:
                item = None
            if item is _STOP:
                break
            if item is not None:
                stream, kind, ts, payload = item  # type: ignore[misc]
                try:
                    self._segment(stream, ts).write(ts, kind, payload)
                    self.written += 1
                except OSError:
                    self.dropped += 1
                    log.exception("recorder.write_failed", stream=stream)
            if time.monotonic() - last_flush >= self.flush_every_s:
                for _, seg in self._segments.values():
                    seg.flush()
                last_flush = time.monotonic()
        for _, seg in self._segments.values():
            seg.close()
        self._segments.clear()

    def _segment(self, stream: str, ts: int) -> _Segment:
        key, path = self.path_for(stream, ts)
        cur = self._segments.get(stream)
        if cur is not None and cur[0] == key:
            return cur[1]
        if cur is not None:
            cur[1].close()
            log.info("recorder.rotated", stream=stream, path=str(cur[1].path), records=cur[1].records)
        seg = _Segment(path, self.level)
        self._segments[stream] = (key, seg)
        return seg


def read_frames(path: Path) -> Iterator[tuple[int, int, bytes]]:
    """Yield (ts_recv_ns, kind, payload). Tolerates a truncated tail from a crash."""
    with open(path, "rb") as fh:
        reader = zstd.ZstdDecompressor().stream_reader(fh, read_across_frames=True)
        buf = b""
        while True:
            try:
                chunk = reader.read(1 << 20)
            except zstd.ZstdError:
                break  # truncated final frame
            if not chunk:
                break
            buf += chunk
            off = 0
            while len(buf) - off >= HEADER.size:
                ts, kind, n = HEADER.unpack_from(buf, off)
                if len(buf) - off - HEADER.size < n:
                    break
                start = off + HEADER.size
                yield ts, kind, buf[start:start + n]
                off = start + n
            buf = buf[off:]
