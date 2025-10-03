from __future__ import annotations

"""Application configuration loader.

This module centralises environment driven configuration so that strategy
simulators and (future) live components share a single definition of runtime
settings. All environment variables are optional; sane defaults are provided.

Groups (prefix comments in ``.env.example`` mirror this):
    Core:
        TIMEFRAME               Candle interval (Binance syntax) default '4h'
        INITIAL_CAPITAL         Starting equity (float) default 10_000
        DEFAULT_DAYS            Default lookback window (int, default 365)
        DEFAULT_SYMBOLS_LIMIT   Max symbols to request (int, default 40)
        SANDBOX                 Use sandbox endpoints if available (bool, default false)

    Exchange credentials (optional – leave blank for public data mode):
        BINANCE_API_KEY
        BINANCE_API_SECRET

    Email notifications (optional; not required for simulations):
        SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS, EMAIL_FROM, EMAIL_TO, STARTTLS

    Breakout strategy tuning (``BR_`` prefix): see ``.env.example`` for a full list.

Usage example::

        from config import Config
        cfg = Config.load()  # automatically loads .env if present
        print(cfg.initial_capital)

Utility helpers ``Config.as_dict()`` and ``Config.describe()`` are provided to
aid debugging / logging without manually enumerating fields.
"""

from dataclasses import dataclass, asdict
import os
from typing import List, Optional

try:
    # python-dotenv is an optional dependency (listed in requirements.txt)
    from dotenv import load_dotenv  # type: ignore
except Exception:  # pragma: no cover

    def load_dotenv(*_args, **_kwargs):  # type: ignore
        return False


_TIMEFRAME_TO_HOURS = {
    # Minutes
    "1m": 1 / 60,
    "3m": 3 / 60,
    "5m": 5 / 60,
    "15m": 15 / 60,
    "30m": 30 / 60,
    # Hours
    "1h": 1,
    "2h": 2,
    "4h": 4,
    "6h": 6,
    "8h": 8,
    "12h": 12,
    # Days / Weeks / Months
    "1d": 24,
    "3d": 72,
    "1w": 24 * 7,
    # Approximate month as 30 days (sufficient for backtest bucketing)
    "1M": 24 * 30,
}


def _get_env(key: str, default: str | None = None) -> Optional[str]:
    v = os.getenv(key)
    if v is None or v == "":
        return default
    return v


def _get_env_int(key: str, default: int) -> int:
    v = _get_env(key)
    if v is None:
        return default
    try:
        return int(v)
    except ValueError:  # pragma: no cover - defensive
        return default


def _get_env_float(key: str, default: float) -> float:
    v = _get_env(key)
    if v is None:
        return default
    try:
        return float(v)
    except ValueError:  # pragma: no cover - defensive
        return default


def _get_env_bool(key: str, default: bool) -> bool:
    v = _get_env(key)
    if v is None:
        return default
    return v.lower() in {"1", "true", "t", "yes", "y"}


@dataclass(slots=True)
class BreakoutSettings:
    channel_lookback: int
    fast_ema_period: int
    slow_ema_period: int
    atr_period: int
    entry_atr_buffer: float
    stop_atr_mult: float
    reward_risk: float
    min_atr_pct: float
    risk_per_trade_pct: float
    trail_activate_rr: float
    trail_lock_rr: float
    trail_atr_mult: float
    max_hold_candles: int
    max_open_positions: int
    min_trade_allocation: float

    @classmethod
    def from_env(cls, prefix: str = "BR_") -> "BreakoutSettings":
        gei = _get_env_int
        gef = _get_env_float
        return cls(
            channel_lookback=gei(f"{prefix}CHANNEL_LOOKBACK", 20),
            fast_ema_period=gei(f"{prefix}FAST_EMA", 21),
            slow_ema_period=gei(f"{prefix}SLOW_EMA", 100),
            atr_period=gei(f"{prefix}ATR_PERIOD", 14),
            entry_atr_buffer=gef(f"{prefix}ENTRY_ATR_BUFFER", 0.10),
            stop_atr_mult=gef(f"{prefix}STOP_ATR_MULT", 2.0),
            reward_risk=gef(f"{prefix}REWARD_RISK", 3.0),
            min_atr_pct=gef(f"{prefix}MIN_ATR_PCT", 0.002),
            risk_per_trade_pct=gef(f"{prefix}RISK_PER_TRADE_PCT", 0.01),
            trail_activate_rr=gef(f"{prefix}TRAIL_ACTIVATE_RR", 1.5),
            trail_lock_rr=gef(f"{prefix}TRAIL_LOCK_RR", 0.75),
            trail_atr_mult=gef(f"{prefix}TRAIL_ATR_MULT", 1.5),
            max_hold_candles=gei(f"{prefix}MAX_HOLD_CANDLES", 400),
            max_open_positions=gei(f"{prefix}MAX_OPEN_POSITIONS", 6),
            min_trade_allocation=gef(f"{prefix}MIN_TRADE_ALLOCATION", 10.0),
        )

    def as_dict(self) -> dict:  # lightweight introspection
        return asdict(self)


@dataclass(slots=True)
class Config:
    timeframe: str
    initial_capital: float
    default_days: int
    default_symbols_limit: int
    sandbox: bool
    binance_api_key: Optional[str]
    binance_api_secret: Optional[str]
    # Optional email settings (may be None if not configured)
    smtp_host: Optional[str] = None
    smtp_port: Optional[int] = None
    smtp_user: Optional[str] = None
    smtp_pass: Optional[str] = None
    email_from: Optional[str] = None
    email_to: Optional[List[str]] = None
    starttls: bool = True
    breakout: BreakoutSettings | None = None

    # --- Derived helpers ---
    @property
    def timeframe_hours(self) -> int:
        hours = _TIMEFRAME_TO_HOURS.get(self.timeframe)
        if hours is None:
            supported = ", ".join(sorted(_TIMEFRAME_TO_HOURS.keys()))
            raise ValueError(
                f"Unsupported timeframe '{self.timeframe}'. Supported: {supported}"
            )
        # For sub-hour intervals we still return at least 1 hour for alignment logic
        return int(hours) if hours >= 1 else 1

    # Convenience / logging helpers -------------------------------------------------
    def as_dict(self, redact_secrets: bool = True) -> dict:
        d = asdict(self)
        if redact_secrets:
            if d.get("binance_api_key"):
                d["binance_api_key"] = "***redacted***"
            if d.get("binance_api_secret"):
                d["binance_api_secret"] = "***redacted***"
            if d.get("smtp_pass"):
                d["smtp_pass"] = "***redacted***"
        # Break breakout nested dataclass into dict
        if isinstance(self.breakout, BreakoutSettings):
            d["breakout"] = self.breakout.as_dict()
        return d

    def describe(self) -> str:
        kv = self.as_dict()
        return ", ".join(f"{k}={v}" for k, v in kv.items())

    @classmethod
    def load(cls, env_file: str | None = None) -> "Config":
        """Load configuration from environment (optionally loading a .env file).

        Args:
            env_file: Path to a .env file. If omitted we attempt to load '.env' in
                      the current working directory. If the file does not exist
                      this is silently ignored.
        """
        # Load .env exactly once; python-dotenv quietly ignores missing file.
        load_dotenv(dotenv_path=env_file, override=False)

        timeframe = _get_env("TIMEFRAME", "4h") or "4h"
        initial_capital = _get_env_float("INITIAL_CAPITAL", 10_000.0)
        default_days = _get_env_int("DEFAULT_DAYS", 365)
        default_symbols_limit = _get_env_int("DEFAULT_SYMBOLS_LIMIT", 40)
        sandbox = _get_env_bool("SANDBOX", False)
        binance_api_key = _get_env("BINANCE_API_KEY")
        binance_api_secret = _get_env("BINANCE_API_SECRET")

        smtp_host = _get_env("SMTP_HOST")
        smtp_port_raw = _get_env("SMTP_PORT")
        smtp_port = int(smtp_port_raw) if smtp_port_raw and smtp_port_raw.isdigit() else None
        smtp_user = _get_env("SMTP_USER")
        smtp_pass = _get_env("SMTP_PASS")
        email_from = _get_env("EMAIL_FROM")
        email_to_raw = _get_env("EMAIL_TO")
        email_to = [e.strip() for e in email_to_raw.split(",") if e.strip()] if email_to_raw else None
        starttls = _get_env_bool("STARTTLS", True)

        breakout = BreakoutSettings.from_env()

        return cls(
            timeframe=timeframe,
            initial_capital=initial_capital,
            default_days=default_days,
            default_symbols_limit=default_symbols_limit,
            sandbox=sandbox,
            binance_api_key=binance_api_key,
            binance_api_secret=binance_api_secret,
            smtp_host=smtp_host,
            smtp_port=smtp_port,
            smtp_user=smtp_user,
            smtp_pass=smtp_pass,
            email_from=email_from,
            email_to=email_to,
            starttls=starttls,
            breakout=breakout,
        )

__all__ = ["Config", "BreakoutSettings"]
