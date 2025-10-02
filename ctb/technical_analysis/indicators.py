from __future__ import annotations
from typing import Sequence, List


def rsi(prices: Sequence[float], period: int = 14) -> List[float]:
    if period <= 0:
        raise ValueError("period must be positive")
    if len(prices) < period + 1:
        return [float('nan')] * len(prices)
    gains: List[float] = [0.0] * len(prices)
    losses: List[float] = [0.0] * len(prices)
    for i in range(1, len(prices)):
        delta = prices[i] - prices[i - 1]
        if delta > 0:
            gains[i] = delta
        else:
            losses[i] = -delta
    avg_gain = sum(gains[1:period+1]) / period
    avg_loss = sum(losses[1:period+1]) / period
    rs_values: List[float] = [float('nan')] * len(prices)
    rsi_values: List[float] = [float('nan')] * len(prices)

    rs_values[period] = avg_gain / avg_loss if avg_loss != 0 else float('inf')
    rsi_values[period] = 100 - (100 / (1 + rs_values[period])) if avg_loss != 0 else 100.0

    for i in range(period + 1, len(prices)):
        gain = gains[i]
        loss = losses[i]
        avg_gain = (avg_gain * (period - 1) + gain) / period
        avg_loss = (avg_loss * (period - 1) + loss) / period
        rs = avg_gain / avg_loss if avg_loss != 0 else float('inf')
        rs_values[i] = rs
        rsi_values[i] = 100 - (100 / (1 + rs)) if avg_loss != 0 else 100.0

    return rsi_values
