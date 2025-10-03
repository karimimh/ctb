from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List

from technical_analysis.kline import Kline
from .signal import BreakoutSignal

__all__ = ["SymbolData", "Position", "SimulationResult"]


@dataclass
class SymbolData:
    symbol: str
    klines: List[Kline]
    time_to_index: Dict[int, int]
    breakouts: List[BreakoutSignal]


@dataclass
class Position:
    symbol: str
    entry_price: float
    quantity: float
    entry_index: int
    stop_loss: float
    take_profit: float
    last_price: float
    initial_risk: float  # entry - stop
    active_trailing: bool = False


@dataclass
class SimulationResult:
    final_equity: float
    cash: float
    realized_pnl: float
    open_positions: int
