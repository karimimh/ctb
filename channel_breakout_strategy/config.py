from __future__ import annotations
from dataclasses import dataclass

__all__ = ["Config"]


@dataclass(slots=True)
class Config:
    # --- Exchange / data settings ---
    timeframe_hours: int = 4  # Candle interval size in hours
    timeframe: str = "4h"  # Binance kline interval string
    default_days: int = 365  # Default backtest lookback
    default_symbols_limit: int = 80  # Limit universe selection
    sandbox: bool = False  # Use Binance testnet (if supported)
    binance_api_key: str | None = None
    binance_api_secret: str | None = None

    # --- Strategy core parameters ---
    fast_ema_period: int = 21
    slow_ema_period: int = 100
    atr_period: int = 14
    channel_lookback: int = 20
    entry_atr_buffer: float = 0.10
    stop_atr_mult: float = 2.0
    reward_risk: float = 3.0
    min_atr_pct: float = 0.002

    # --- Position sizing / risk ---
    initial_capital: float = 1_000.0
    risk_per_trade_pct: float = 0.01
    min_trade_allocation: float = 10.0
    max_open_positions: int = 4

    # --- Trade management / trailing ---
    trail_activate_rr: float = 1.5
    trail_lock_rr: float = 0.75
    trail_atr_mult: float = 1.5
    max_hold_candles: int = 400

    # --- Feature flags ---
    breakout: bool = True

    # --- Kline CSV cache options ---
    # Directory where kline CSV files are stored / read from
    kline_csv_dir: str = "data/klines"
    # If True, after downloading klines from the exchange they will be written to CSV files
    save_downloaded_klines: bool = True
    # If True, skip downloading and instead load klines from CSV files found in kline_csv_dir
    load_klines_from_csv: bool = True

    @classmethod
    def load(cls) -> "Config":  # Simple loader (no env / files for now)
        return cls()
