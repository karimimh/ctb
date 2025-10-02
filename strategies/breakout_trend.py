from __future__ import annotations

"""Breakout / Trend-Following Strategy Helpers.

This module provides pure functions to support a volatility-adjusted
channel breakout strategy that can be re-used by different simulators
or (later) live trading components.

Core idea (long-only for simplicity):
 1. Regime filter: fast EMA > slow EMA (uptrend confirmation).
 2. Volatility filter: ATR / close >= min_atr_pct.
 3. Breakout trigger: candle close breaks above the highest high of the
    previous `channel_lookback` completed candles, optionally plus an
    ATR buffer: entry_threshold = prior_high + atr * entry_atr_buffer.
 4. Initial stop: lowest low of the same lookback window - atr * stop_atr_mult.
 5. Take profit (static suggestion): entry + (entry - stop) * reward_risk.

We separate signal generation (when a breakout condition becomes true)
from position sizing / order management which the simulator handles.

DISCLAIMER: No profitability is guaranteed. This is a *research* tool.
Do NOT trade real capital based solely on these rules.
"""

from dataclasses import dataclass
from typing import List, Sequence
import math

from ctb.technical_analysis.indicators import ema, atr

@dataclass(slots=True)
class BreakoutSignal:
    index: int
    entry_price: float
    stop_price: float
    reward_risk_target: float  # suggested take profit (RR multiple)
    regime_fast: float
    regime_slow: float
    atr: float


def _rolling_high(values: Sequence[float], lookback: int) -> List[float]:
    n = len(values)
    out: List[float] = [math.nan] * n
    for i in range(lookback, n):
        window = values[i - lookback:i]
        out[i] = max(window)
    return out


def _rolling_low(values: Sequence[float], lookback: int) -> List[float]:
    n = len(values)
    out: List[float] = [math.nan] * n
    for i in range(lookback, n):
        window = values[i - lookback:i]
        out[i] = min(window)
    return out


def generate_breakout_signals(
    closes: Sequence[float],
    highs: Sequence[float],
    lows: Sequence[float],
    fast_ema_period: int,
    slow_ema_period: int,
    atr_period: int,
    channel_lookback: int,
    entry_atr_buffer: float,
    stop_atr_mult: float,
    reward_risk: float,
    min_atr_pct: float,
) -> List[BreakoutSignal]:
    """Scan price series and emit breakout signals.

    Returns a list of BreakoutSignal sorted by index. Each signal is *fire once* –
    multiple consecutive breakout closes won't emit duplicates until price
    first falls back below the channel high and re-breaks (implicit behavior
    because we only trigger on first close > threshold after having been below).
    """
    if not (len(closes) == len(highs) == len(lows)):
        raise ValueError("closes/highs/lows length mismatch")
    n = len(closes)
    if n == 0:
        return []
    fast = ema(closes, fast_ema_period)
    slow = ema(closes, slow_ema_period)
    atr_vals = atr(highs, lows, closes, period=atr_period)
    ch_high = _rolling_high(highs, channel_lookback)
    ch_low = _rolling_low(lows, channel_lookback)
    signals: List[BreakoutSignal] = []
    prev_above = False  # track whether we were already in breakout state
    for i in range(n):
        f = fast[i]
        s = slow[i]
        a = atr_vals[i]
        hh = ch_high[i]
        ll = ch_low[i]
        price = closes[i]
        if any(math.isnan(v) for v in (f, s, a, hh, ll)):
            continue
        if f <= s:
            prev_above = False
            continue
        if a / price < min_atr_pct:
            prev_above = False
            continue
        threshold = hh + a * entry_atr_buffer
        above = price > threshold
        if above and not prev_above:
            stop = ll - a * stop_atr_mult
            if stop >= price:  # invalid risk geometry
                prev_above = True
                continue
            rr_target = price + (price - stop) * reward_risk
            signals.append(
                BreakoutSignal(
                    index=i,
                    entry_price=price,
                    stop_price=stop,
                    reward_risk_target=rr_target,
                    regime_fast=f,
                    regime_slow=s,
                    atr=a,
                )
            )
        prev_above = above
    return signals


__all__ = [
    "BreakoutSignal",
    "generate_breakout_signals",
]
