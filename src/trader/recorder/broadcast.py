"""Local fan-out of raw feed frames (one Upstox connection owner, many consumers).

Upstox allows 5 websocket connections per account and the recorder uses 4, so the
trading process cannot open its own. Instead the recorder re-publishes every raw
record on 127.0.0.1 and `LocalFrameFeed` (trader.adapters.local.feed) decodes them
exactly as replay decodes bronze files — so live and replay see identical input.

Wire format per record: ``uint16 stream_len | stream | int64 ts | uint16 kind | uint32 len | payload``.
Slow clients are dropped rather than slowing the recorder.
"""

from __future__ import annotations

import asyncio
import struct

import structlog

from trader.ports.infra import RawRecorder

log = structlog.get_logger(__name__)

DEFAULT_PORT = 47011
REC = struct.Struct("<qHI")
SLEN = struct.Struct("<H")
_MAX_BUFFER = 64 * 2**20


def pack(stream: str, kind: int, ts: int, payload: bytes) -> bytes:
    s = stream.encode()
    return SLEN.pack(len(s)) + s + REC.pack(ts, kind, len(payload)) + payload


async def read_record(reader: asyncio.StreamReader) -> tuple[str, int, int, bytes]:
    (n,) = SLEN.unpack(await reader.readexactly(SLEN.size))
    stream = (await reader.readexactly(n)).decode()
    ts, kind, ln = REC.unpack(await reader.readexactly(REC.size))
    return stream, kind, ts, await reader.readexactly(ln)


class FrameBroadcaster(RawRecorder):
    """A RawRecorder that forwards every record to local subscribers, then to `inner`."""

    def __init__(self, inner: RawRecorder, *, port: int = DEFAULT_PORT) -> None:
        self.inner = inner
        self.port = port
        self._clients: set[asyncio.StreamWriter] = set()
        self._server: asyncio.base_events.Server | None = None
        self.dropped_clients = 0

    async def start(self) -> None:
        self._server = await asyncio.start_server(self._on_client, "127.0.0.1", self.port)
        log.info("broadcast.listening", port=self.port)

    async def _on_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        self._clients.add(writer)
        log.info("broadcast.client_connected", peer=str(writer.get_extra_info("peername")))
        try:
            await reader.read()  # clients never send; returns on disconnect
        finally:
            self._clients.discard(writer)
            writer.close()

    def write(self, stream: str, kind: int, ts_recv_ns: int, payload: bytes) -> None:
        self.inner.write(stream, kind, ts_recv_ns, payload)
        if not self._clients:
            return
        rec = pack(stream, kind, ts_recv_ns, payload)
        for w in list(self._clients):
            if w.transport.get_write_buffer_size() > _MAX_BUFFER:
                self.dropped_clients += 1
                log.warning("broadcast.slow_client_dropped")
                self._clients.discard(w)
                w.close()
                continue
            w.write(rec)

    def close(self) -> None:
        for w in list(self._clients):
            w.close()
        self._clients.clear()
        if self._server is not None:
            self._server.close()
        self.inner.close()
