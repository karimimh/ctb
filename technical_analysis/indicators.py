from __future__ import annotations
from typing import Sequence, List
import math

__all__ = [
    "rsi",
    "ema",
    "atr",
]


def rsi(prices: Sequence[float], period: int = 14) -> List[float]:
    """Compute Relative Strength Index (RSI) using Wilder's smoothing.

    Returns list same length as prices filled with NaN until the first
    computable value at index == period.
    """
    if period <= 0:
        raise ValueError("period must be positive")
    n = len(prices)
    if n == 0:
        return []
    if n < period + 1:
        return [float('nan')] * n
    gains: List[float] = [0.0] * n
    losses: List[float] = [0.0] * n
    for i in range(1, n):
        delta = prices[i] - prices[i - 1]
        if delta > 0:
            gains[i] = delta
        elif delta < 0:
            losses[i] = -delta
    avg_gain = sum(gains[1:period + 1]) / period
    avg_loss = sum(losses[1:period + 1]) / period
    rs_values: List[float] = [float('nan')] * n
    rsi_values: List[float] = [float('nan')] * n
    rs = avg_gain / avg_loss if avg_loss != 0 else math.inf
    rs_values[period] = rs
    rsi_values[period] = 100 - (100 / (1 + rs)) if avg_loss != 0 else 100.0
    for i in range(period + 1, n):
        gain = gains[i]
        loss = losses[i]
        avg_gain = (avg_gain * (period - 1) + gain) / period
        avg_loss = (avg_loss * (period - 1) + loss) / period
        rs = avg_gain / avg_loss if avg_loss != 0 else math.inf
        rs_values[i] = rs
        rsi_values[i] = 100 - (100 / (1 + rs)) if avg_loss != 0 else 100.0
    return rsi_values


def ema(values: Sequence[float], period: int) -> List[float]:
    """Exponential moving average. Returns list of same length, leading values NaN until first EMA."""
    if period <= 0:
        raise ValueError("period must be positive")
    n = len(values)
    if n == 0:
        return []
    result: List[float] = [float('nan')] * n
    if n < period:
        return result
    # Seed with simple average
    seed = sum(values[:period]) / period
    result[period - 1] = seed
    k = 2 / (period + 1)
    prev = seed
    for i in range(period, n):
        price = values[i]
        prev = price * k + prev * (1 - k)
        result[i] = prev
    return result


def atr(highs: Sequence[float], lows: Sequence[float], closes: Sequence[float], period: int = 14) -> List[float]:
    """Average True Range (Wilder)."""
    if not (len(highs) == len(lows) == len(closes)):
        raise ValueError("Input sequences must have the same length")
    n = len(highs)
    if n == 0:
        return []
    trs: List[float] = [float('nan')] * n
    for i in range(1, n):
        high = highs[i]
        low = lows[i]
        prev_close = closes[i - 1]
        tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
        trs[i] = tr
    if period <= 0:
        raise ValueError("period must be positive")
    if n < period + 1:
        return [float('nan')] * n
    atr_values: List[float] = [float('nan')] * n
    first_atr = sum([tr for tr in trs[1:period + 1]]) / period
    atr_values[period] = first_atr
    for i in range(period + 1, n):
        prev_atr = atr_values[i - 1]
        current_tr = trs[i]
        atr_values[i] = (prev_atr * (period - 1) + current_tr) / period
    return atr_values
