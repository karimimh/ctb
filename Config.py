from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional


def _get_raw(key: str) -> Optional[str]:
    value = os.getenv(key)
    if value is None:
        return None
    value = value.strip()
    return value if value != "" else None


def _get_str(key: str, default: str) -> str:
    value = _get_raw(key)
    return value if value is not None else default


def _get_optional_str(key: str) -> Optional[str]:
    return _get_raw(key)


def _get_int(key: str, default: int) -> int:
    value = _get_raw(key)
    return int(value) if value is not None else default


def _get_optional_int(key: str) -> Optional[int]:
    value = _get_raw(key)
    return int(value) if value is not None else None


def _get_float(key: str, default: float) -> float:
    value = _get_raw(key)
    return float(value) if value is not None else default


def _get_bool(key: str, default: bool) -> bool:
    value = _get_raw(key)
    if value is None:
        return default
    return value.lower() in {"1", "true", "yes", "on"}


def _parse_timeframe_hours(value: str) -> int:
    value = value.strip().lower()
    if value.endswith("h"):
        number = value[:-1]
        if not number:
            raise ValueError("Timeframe value missing hour component")
        return int(number)
    raise ValueError(f"Unsupported timeframe format: {value}")


def _load_env_file() -> None:
    try:
        from dotenv import load_dotenv as _load_dotenv  # type: ignore[import-not-found]
    except ImportError:  # pragma: no cover - optional dependency
        return
    _load_dotenv(override=False)


@dataclass(slots=True)
class Config:
    initial_capital: float
    timeframe: str
    timeframe_hours: int
    rsi_period: int
    swing_k: int
    capital_per_trade: float
    max_open_positions: int
    stop_loss_pct: float
    take_profit_pct: float
    max_entry_wait_candles: int
    max_hold_candles: int
    opportunity_min_candles: int
    opportunity_max_candles: int
    min_trade_allocation: float
    default_days: int
    default_symbols_limit: Optional[int]
    binance_api_key: Optional[str]
    binance_api_secret: Optional[str]
    sandbox: bool
    # Advanced strategy parameters
    fast_ema_period: int
    slow_ema_period: int
    atr_period: int
    atr_stop_mult: float
    reward_risk: float
    min_atr_pct: float
    strategy_mode: str  # 'divergence' or 'multi_factor'
    risk_per_trade_pct: float  # only used in multi-factor mode (fraction of equity at risk)

    @classmethod
    def load(cls) -> "Config":
        _load_env_file()
        timeframe = _get_str("SIM_TIMEFRAME", "4h")
        timeframe_hours = _parse_timeframe_hours(timeframe)
        return cls(
            initial_capital=_get_float("SIM_INITIAL_CAPITAL", 1000.0),
            timeframe=timeframe,
            timeframe_hours=timeframe_hours,
            rsi_period=_get_int("SIM_RSI_PERIOD", 14),
            swing_k=_get_int("SIM_SWING_K", 2),
            capital_per_trade=_get_float("SIM_CAPITAL_PER_TRADE", 0.25),
            max_open_positions=_get_int("SIM_MAX_OPEN_POSITIONS", 4),
            stop_loss_pct=_get_float("SIM_STOP_LOSS_PCT", 0.05),
            take_profit_pct=_get_float("SIM_TAKE_PROFIT_PCT", 0.10),
            max_entry_wait_candles=_get_int("SIM_MAX_ENTRY_WAIT_CANDLES", 3),
            max_hold_candles=_get_int("SIM_MAX_HOLD_CANDLES", 30),
            opportunity_min_candles=_get_int("SIM_OPPORTUNITY_MIN_CANDLES", 2),
            opportunity_max_candles=_get_int("SIM_OPPORTUNITY_MAX_CANDLES", 10),
            min_trade_allocation=_get_float("SIM_MIN_TRADE_ALLOCATION", 10.0),
            default_days=_get_int("SIM_DEFAULT_DAYS", 365),
            default_symbols_limit=_get_optional_int("SIM_SYMBOLS_LIMIT"),
            binance_api_key=_get_optional_str("BINANCE_API_KEY"),
            binance_api_secret=_get_optional_str("BINANCE_API_SECRET"),
            sandbox=_get_bool("SIM_SANDBOX", False),
            fast_ema_period=_get_int("SIM_FAST_EMA", 21),
            slow_ema_period=_get_int("SIM_SLOW_EMA", 100),
            atr_period=_get_int("SIM_ATR_PERIOD", 14),
            atr_stop_mult=_get_float("SIM_ATR_STOP_MULT", 2.5),
            reward_risk=_get_float("SIM_RR", 2.0),
            min_atr_pct=_get_float("SIM_MIN_ATR_PCT", 0.002),
            strategy_mode=_get_str("SIM_STRATEGY", "divergence").lower(),
            risk_per_trade_pct=_get_float("SIM_RISK_PER_TRADE_PCT", 0.01),
        )


__all__ = ["Config"]
