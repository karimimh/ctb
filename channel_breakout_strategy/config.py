from dataclasses import dataclass
from typing import Optional

__all__ = ["BreakoutSettings", "Config"]


@dataclass
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


@dataclass
class Config:
    # Core simulation parameters (populate minimally; extend as needed)
    initial_capital: float
    timeframe: str
    timeframe_hours: int
    default_days: int
    default_symbols_limit: int
    sandbox: bool
    binance_api_key: Optional[str]
    binance_api_secret: Optional[str]
    breakout: Optional[BreakoutSettings]

    @classmethod
    def load(cls) -> "Config":  # Placeholder loader; replace with real config source
        # In a real application, load from a file (YAML/JSON/env). Here we provide sane defaults.
        default_breakout = BreakoutSettings(
            channel_lookback=120,
            fast_ema_period=9,
            slow_ema_period=26,
            atr_period=14,
            entry_atr_buffer=0.1,
            stop_atr_mult=2.0,
            reward_risk=3.0,
            min_atr_pct=0.002,
            risk_per_trade_pct=0.01,
            trail_activate_rr=2.0,
            trail_lock_rr=1.0,
            trail_atr_mult=1.5,
            max_hold_candles=500,
            max_open_positions=10,
            min_trade_allocation=25.0,
        )
        return cls(
            initial_capital=10_000.0,
            timeframe="1h",
            timeframe_hours=1,
            default_days=120,
            default_symbols_limit=50,
            sandbox=True,
            binance_api_key=None,
            binance_api_secret=None,
            breakout=default_breakout,
        )
