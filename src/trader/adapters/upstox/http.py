"""Thin async Upstox REST client on httpx (no SDK, by owner decision).

* Rate-limited below the shared per-account limit (design §11).
* GETs retry on 429/5xx/network errors with backoff. Order-mutating calls never
  retry: an ambiguous outcome is surfaced as `UpstoxTimeout` so the OMS can mark the
  order UNKNOWN and reconcile by tag (design §10).
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

import httpx
import structlog

log = structlog.get_logger(__name__)


class UpstoxError(Exception):
    def __init__(self, status: int, code: str, message: str, payload: Any = None) -> None:
        super().__init__(f"HTTP {status} {code}: {message}")
        self.status = status
        self.code = code
        self.message = message
        self.payload = payload


class UpstoxTimeout(Exception):
    """The request may or may not have reached Upstox."""


class _RateLimiter:
    def __init__(self, per_sec: float) -> None:
        self._interval = 1.0 / per_sec
        self._next = 0.0
        self._lock = asyncio.Lock()

    async def wait(self) -> None:
        async with self._lock:
            now = time.monotonic()
            if self._next > now:
                await asyncio.sleep(self._next - now)
                now = self._next
            self._next = now + self._interval


class UpstoxHttp:
    def __init__(
        self,
        token: str,
        *,
        api_base: str = "https://api.upstox.com",
        hft_base: str = "https://api-hft.upstox.com",
        timeout_s: float = 10.0,
        rest_per_sec: float = 10.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.api_base = api_base.rstrip("/")
        self.hft_base = hft_base.rstrip("/")
        self._limiter = _RateLimiter(rest_per_sec)
        self._client = httpx.AsyncClient(
            headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
            timeout=timeout_s,
            transport=transport,
            http2=False,
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    @staticmethod
    def _raise_for(resp: httpx.Response) -> Any:
        try:
            body = resp.json()
        except ValueError:
            body = None
        if resp.status_code < 400 and (not isinstance(body, dict) or body.get("status") != "error"):
            return body
        code, msg = "", resp.text[:300]
        if isinstance(body, dict) and body.get("errors"):
            e = body["errors"][0]
            code = str(e.get("errorCode") or e.get("error_code") or "")
            msg = str(e.get("message") or msg)
        raise UpstoxError(resp.status_code, code, msg, body)

    async def get(self, path: str, *, params: dict[str, Any] | None = None, retries: int = 3,
                  base: str | None = None) -> Any:
        url = (base or self.api_base) + path
        delay = 0.5
        for attempt in range(retries + 1):
            await self._limiter.wait()
            try:
                resp = await self._client.get(url, params=params)
            except httpx.TransportError as e:
                if attempt == retries:
                    raise UpstoxTimeout(f"GET {path}: {e!r}") from e
            else:
                if resp.status_code == 429 or resp.status_code >= 500:
                    if attempt == retries:
                        return self._raise_for(resp)
                else:
                    return self._raise_for(resp)
            log.warning("upstox.get.retry", path=path, attempt=attempt + 1)
            await asyncio.sleep(delay)
            delay = min(delay * 2, 8.0)
        raise AssertionError("unreachable")

    async def send(self, method: str, path: str, *, json: Any = None, params: dict[str, Any] | None = None,
                   hft: bool = False) -> Any:
        """Single attempt. Use for anything that changes state at the broker."""
        await self._limiter.wait()
        url = (self.hft_base if hft else self.api_base) + path
        try:
            resp = await self._client.request(method, url, json=json, params=params)
        except (httpx.TimeoutException, httpx.NetworkError, httpx.RemoteProtocolError) as e:
            raise UpstoxTimeout(f"{method} {path}: {e!r}") from e
        return self._raise_for(resp)
