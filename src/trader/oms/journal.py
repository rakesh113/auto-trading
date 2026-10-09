"""Append-only journal in SQLite (WAL): every signal, risk decision, order and fill (design §10).

Replay writes its own journal; `digest()` hashes the decision stream so two runs of
the same day can be compared exactly (the replay-parity check).
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any

import msgspec

_enc = msgspec.json.Encoder()


def _default(o: Any) -> Any:
    if hasattr(o, "__struct_fields__"):
        return {f: getattr(o, f) for f in o.__struct_fields__}
    return str(o)


class Journal:
    def __init__(self, path: Path | None) -> None:
        self.path = path
        self._db: sqlite3.Connection | None = None
        if path is not None:
            path.parent.mkdir(parents=True, exist_ok=True)
            self._db = sqlite3.connect(path, isolation_level=None, check_same_thread=False)
            self._db.execute("PRAGMA journal_mode=WAL")
            self._db.execute("PRAGMA synchronous=NORMAL")
            self._db.execute("CREATE TABLE IF NOT EXISTS events (seq INTEGER PRIMARY KEY, ts_ns INTEGER, "
                             "book TEXT, kind TEXT, data TEXT)")
        self._hash = hashlib.sha256()
        self.count = 0

    def write(self, ts_ns: int, book: str, kind: str, data: dict[str, Any]) -> None:
        payload = json.dumps(data, default=_default, sort_keys=True, separators=(",", ":"))
        self._hash.update(f"{ts_ns}|{book}|{kind}|{payload}\n".encode())
        self.count += 1
        if self._db is not None:
            self._db.execute("INSERT INTO events (ts_ns, book, kind, data) VALUES (?,?,?,?)",
                             (ts_ns, book, kind, payload))

    def digest(self) -> str:
        return self._hash.hexdigest()

    def rows(self, kind: str | None = None) -> list[tuple[int, str, str, dict[str, Any]]]:
        if self._db is None:
            return []
        q = "SELECT ts_ns, book, kind, data FROM events" + (" WHERE kind=?" if kind else "") + " ORDER BY seq"
        cur = self._db.execute(q, (kind,) if kind else ())
        return [(ts, b, k, json.loads(d)) for ts, b, k, d in cur]

    def close(self) -> None:
        if self._db is not None:
            self._db.close()
            self._db = None
