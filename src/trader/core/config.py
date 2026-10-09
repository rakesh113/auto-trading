"""Configuration: YAML layers + secrets from the environment.

Load order (later wins): config/base.yaml → config/profiles/<profile>.yaml →
config/local.yaml (git-ignored, optional). Secrets never live in YAML; YAML names the
environment variable and `secret()` reads it (populated from `.env`).

Adapter-specific settings live under `execution.settings.<venue>` (and the same for
feeds/notifiers). Each adapter validates its own block with its own pydantic model,
so adding a venue never requires editing this file.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Literal

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field, field_validator

from trader.domain.types import FeedMode

REPO_ROOT = Path(__file__).resolve().parents[3]
CONFIG_DIR = REPO_ROOT / "config"

Profile = Literal["replay", "paper", "shadow", "live"]


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class SystemCfg(_Model):
    name: str = "auto-trading"
    tag_prefix: str = "AT"  # identifies this system's orders at the broker (design D13)
    data_dir: Path = Path("D:/trading-data")
    log_level: str = "INFO"

    @field_validator("tag_prefix")
    @classmethod
    def _prefix(cls, v: str) -> str:
        if not re.fullmatch(r"[A-Z]{2,4}", v):
            raise ValueError("tag_prefix must be 2-4 uppercase letters")
        return v


class UpstoxCfg(_Model):
    analytics_token_env: str = "UPSTOX_ANALYTICS_TOKEN"  # read-only, 1 year: data
    access_token_env: str = "UPSTOX_ACCESS_TOKEN"  # daily: live orders only
    api_base: str = "https://api.upstox.com"
    hft_base: str = "https://api-hft.upstox.com"
    timeout_s: float = 10.0
    rest_per_sec: float = 10.0  # ≤ 50% of the shared account limit (design §11)
    instruments_url: str = "https://assets.upstox.com/market-quote/instruments/exchange/complete.json.gz"


class ConnectionCfg(_Model):
    name: str
    modes: list[FeedMode]


class FeedCfg(_Model):
    provider: str = "upstox"
    connections: list[ConnectionCfg] = Field(
        default_factory=lambda: [
            ConnectionCfg(name="c1_d30", modes=[FeedMode.FULL_D30]),
            ConnectionCfg(name="c2_full", modes=[FeedMode.FULL]),
            ConnectionCfg(name="c3_ltpc", modes=[FeedMode.LTPC]),
            ConnectionCfg(name="c4_greeks", modes=[FeedMode.OPTION_GREEKS]),
        ]
    )
    max_keys: dict[FeedMode, int] = Field(
        default_factory=lambda: {
            FeedMode.FULL_D30: 45,
            FeedMode.FULL: 1500,
            FeedMode.OPTION_GREEKS: 2000,
            FeedMode.LTPC: 2000,
        }
    )
    queue_size: int = 200_000
    stale_after_s: float = 5.0
    reconnect_max_backoff_s: float = 30.0


class InstrumentsCfg(_Model):
    provider: str = "upstox"


class ExecutionCfg(_Model):
    venue: str = "paper"
    settings: dict[str, dict[str, Any]] = Field(default_factory=dict)  # venue -> adapter settings


class ThrottleCfg(_Model):
    orders_per_sec: float = 5.0  # SEBI cap is 10/s for unregistered algos; we self-limit (design §4)
    burst: int = 5


class RecorderCfg(_Model):
    rotate_minutes: int = 15
    zstd_level: int = 3
    flush_every_s: float = 2.0
    bronze_retention_days: int = 30  # raw frames; silver Parquet is kept indefinitely
    backup_dir: Path | None = None  # e.g. an external drive or a synced folder; None disables
    min_free_gb: float = 50.0  # alert when the data drive drops below this
    broadcast_port: int = 47011  # local fan-out of raw frames to the trading process (0 disables)


class NotifierCfg(_Model):
    provider: str = "log"
    settings: dict[str, dict[str, Any]] = Field(default_factory=dict)


class LlmCfg(_Model):
    provider: str = "openrouter"
    api_key_env: str = "OPENROUTER_API_KEY"
    base_url: str = "https://openrouter.ai/api/v1"
    budget_inr_month: float = 8500
    budget_inr_day: float = 400
    usd_inr: float = 88.0
    routes: dict[str, dict[str, Any]] = Field(default_factory=dict)


class AppConfig(_Model):
    profile: Profile = "paper"
    system: SystemCfg = SystemCfg()
    upstox: UpstoxCfg = UpstoxCfg()
    feed: FeedCfg = FeedCfg()
    instruments: InstrumentsCfg = InstrumentsCfg()
    execution: ExecutionCfg = ExecutionCfg()
    throttle: ThrottleCfg = ThrottleCfg()
    recorder: RecorderCfg = RecorderCfg()
    notifier: NotifierCfg = NotifierCfg()
    llm: LlmCfg = LlmCfg()
    universe: dict[str, Any] = Field(default_factory=dict)  # see config/universe.yaml

    def venue_settings(self, venue: str | None = None) -> dict[str, Any]:
        return dict(self.execution.settings.get(venue or self.execution.venue, {}))


def _deep_merge(a: dict[str, Any], b: dict[str, Any]) -> dict[str, Any]:
    out = dict(a)
    for k, v in b.items():
        out[k] = _deep_merge(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
    return out


def _read_yaml(p: Path) -> dict[str, Any]:
    if not p.exists():
        return {}
    data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError(f"{p} must contain a mapping")
    return data


def load_config(
    profile: str | None = None,
    *,
    config_dir: Path = CONFIG_DIR,
    overrides: dict[str, Any] | None = None,
    env_file: Path | None = REPO_ROOT / ".env",
) -> AppConfig:
    if env_file is not None and env_file.exists():
        load_dotenv(env_file, override=False)
    data = _read_yaml(config_dir / "base.yaml")
    profile = profile or os.environ.get("TRADER_PROFILE") or data.get("profile") or "paper"
    data = _deep_merge(data, _read_yaml(config_dir / "profiles" / f"{profile}.yaml"))
    data = _deep_merge(data, _read_yaml(config_dir / "local.yaml"))
    data["universe"] = _deep_merge(_read_yaml(config_dir / "universe.yaml"), data.get("universe", {}))
    if overrides:
        data = _deep_merge(data, overrides)
    data["profile"] = profile
    return AppConfig.model_validate(data)


class MissingSecret(RuntimeError):
    pass


def secret(env_name: str) -> str:
    v = os.environ.get(env_name, "").strip()
    if not v or v.startswith("__PLACEHOLDER"):
        raise MissingSecret(f"environment variable {env_name} is not set (add it to .env)")
    return v
