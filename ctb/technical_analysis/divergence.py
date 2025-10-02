from __future__ import annotations
from dataclasses import dataclass
from typing import List, Sequence, Literal
import math

@dataclass
class SwingPoint:
    index: int
    price: float
    rsi: float
    kind: Literal['high','low']  # 'high' or 'low'


def detect_swings(prices: Sequence[float], rsi_values: Sequence[float], k: int = 2) -> List[SwingPoint]:
    swings: List[SwingPoint] = []
    n = len(prices)
    for i in range(k, n - k):
        p = prices[i]
        is_high = all(p > prices[i - j] and p >= prices[i + j] for j in range(1, k+1))
        is_low = all(p < prices[i - j] and p <= prices[i + j] for j in range(1, k+1))
        if is_high:
            swings.append(SwingPoint(i, p, rsi_values[i], 'high'))
        elif is_low:
            swings.append(SwingPoint(i, p, rsi_values[i], 'low'))
    return swings

@dataclass
class DivergenceSignal:
    kind: Literal['bullish','bearish']
    symbol: str
    timeframe: str
    price_prev: float
    price_last: float
    rsi_prev: float
    rsi_last: float
    candle_index: int  # index of last swing


def find_latest_divergence(symbol: str, timeframe: str, closes: Sequence[float], rsi_values: Sequence[float], k: int = 2) -> DivergenceSignal | None:
    swings = detect_swings(closes, rsi_values, k=k)
    # Need at least two lows or two highs
    lows = [s for s in swings if s.kind == 'low']
    highs = [s for s in swings if s.kind == 'high']
    sig: DivergenceSignal | None = None
    if len(lows) >= 2:
        last_low, prev_low = lows[-1], lows[-2]
        if last_low.price < prev_low.price and last_low.rsi > prev_low.rsi:
            sig = DivergenceSignal('bullish', symbol, timeframe, prev_low.price, last_low.price, prev_low.rsi, last_low.rsi, last_low.index)
    if len(highs) >= 2:
        last_high, prev_high = highs[-1], highs[-2]
        if last_high.price > prev_high.price and last_high.rsi < prev_high.rsi:
            bearish = DivergenceSignal('bearish', symbol, timeframe, prev_high.price, last_high.price, prev_high.rsi, last_high.rsi, last_high.index)
            # Prefer the most recent divergence by candle index
            if sig is None or bearish.candle_index > sig.candle_index:
                sig = bearish
    return sig


def find_divergences(symbol: str, timeframe: str, closes: Sequence[float], rsi_values: Sequence[float], k: int = 2) -> List[DivergenceSignal]:
    """Return all detected divergences in chronological order.

    A divergence is formed by two consecutive swings of same kind (two lows for bullish, two highs for bearish)
    satisfying the usual price/RSI opposite direction criteria.
    """
    swings = detect_swings(closes, rsi_values, k=k)
    lows = [s for s in swings if s.kind == 'low']
    highs = [s for s in swings if s.kind == 'high']
    signals: List[DivergenceSignal] = []
    for i in range(1, len(lows)):
        prev_low, last_low = lows[i-1], lows[i]
        if last_low.price < prev_low.price and last_low.rsi > prev_low.rsi:
            signals.append(DivergenceSignal('bullish', symbol, timeframe, prev_low.price, last_low.price, prev_low.rsi, last_low.rsi, last_low.index))
    for i in range(1, len(highs)):
        prev_high, last_high = highs[i-1], highs[i]
        if last_high.price > prev_high.price and last_high.rsi < prev_high.rsi:
            signals.append(DivergenceSignal('bearish', symbol, timeframe, prev_high.price, last_high.price, prev_high.rsi, last_high.rsi, last_high.index))
    signals.sort(key=lambda s: s.candle_index)
    return signals
