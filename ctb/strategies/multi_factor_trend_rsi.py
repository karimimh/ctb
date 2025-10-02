from __future__ import annotations
"""Multi-factor trading strategy.

Core ideas:
- Primary signal: bullish RSI divergence (existing logic) OR RSI oversold reversal.
- Trend filter: price above long EMA (bullish bias) for long entries.
- Volatility filter: ATR must be above a minimum threshold (avoid dead markets) and
  position size scales inversely with ATR (higher ATR -> smaller size risk parity style).
- Adaptive stop: multiple of ATR below entry; take-profit via RR ratio or trailing stop.

This module only prepares signals (it does not run simulation). It returns a list of
StrategySignal objects that downstream simulator can interpret (extension point).
"""
from dataclasses import dataclass
from typing import Sequence, List, Dict, Optional
import math

from ctb.technical_analysis.indicators import rsi, ema, atr
from ctb.technical_analysis.divergence import find_latest_divergence, DivergenceSignal


@dataclass
class StrategySignal:
    symbol: str
    timeframe: str
    index: int  # candle index
    kind: str   # 'long'
    reason: str
    entry_hint: float
    stop_hint: float
    target_hint: float
    risk_multiple: float  # (target_hint - entry)/ (entry-stop)


def _last(values: Sequence[float]) -> float:
    for v in reversed(values):
        if not math.isnan(v):
            return v
    return float('nan')


def evaluate_symbol(symbol: str, timeframe: str, opens: Sequence[float], highs: Sequence[float],
                    lows: Sequence[float], closes: Sequence[float],
                    rsi_period: int = 14, fast_ema: int = 21, slow_ema: int = 100,
                    atr_period: int = 14, atr_stop_mult: float = 2.5,
                    rr_target: float = 2.0, min_atr_pct: float = 0.002) -> Optional[StrategySignal]:
    if len(closes) < max(rsi_period, slow_ema, atr_period) + 5:
        return None
    rsi_vals = rsi(closes, period=rsi_period)
    fast = ema(closes, fast_ema)
    slow = ema(closes, slow_ema)
    atr_vals = atr(highs, lows, closes, period=atr_period)
    last_close = closes[-1]
    last_rsi = _last(rsi_vals)
    last_fast = _last(fast)
    last_slow = _last(slow)
    last_atr = _last(atr_vals)
    if any(math.isnan(x) for x in (last_rsi, last_fast, last_slow, last_atr)):
        return None
    # Trend filter
    if last_fast < last_slow:
        return None
    # Volatility filter (relative to price)
    if last_atr / last_close < min_atr_pct:
        return None
    divergence = find_latest_divergence(symbol, timeframe, closes, rsi_vals, k=2)
    signal_reason = None
    if divergence and divergence.kind == 'bullish' and divergence.candle_index < len(closes) - 1:
        signal_reason = 'bullish_divergence'
        ref_low = divergence.price_last
    else:
        # Alternative oversold bounce: RSI crossed up from <30 to >35 and price above fast EMA
        if last_rsi > 35:
            for i in range(len(rsi_vals) - 2, -1, -1):
                if not math.isnan(rsi_vals[i]) and rsi_vals[i] < 30:
                    signal_reason = 'rsi_reversal'
                    ref_low = min(lows[i:])  # crude recent low
                    break
    if not signal_reason:
        return None
    stop = ref_low - last_atr * atr_stop_mult * 0.5  # place slightly below reference with ATR cushion
    risk = last_close - stop
    if risk <= 0:
        return None
    target = last_close + risk * rr_target
    return StrategySignal(
        symbol=symbol,
        timeframe=timeframe,
        index=len(closes) - 1,
        kind='long',
        reason=signal_reason,
        entry_hint=last_close,
        stop_hint=stop,
        target_hint=target,
        risk_multiple=rr_target,
    )


def run_strategy(symbols: Sequence[str], klines_by_symbol_and_tf: Dict[str, Dict[str, List[List]]],
                 **kwargs) -> List[StrategySignal]:
    signals: List[StrategySignal] = []
    for symbol in symbols:
        per_tf = klines_by_symbol_and_tf.get(symbol, {})
        for timeframe, klines in per_tf.items():
            opens = [float(k[1]) for k in klines]
            highs = [float(k[2]) for k in klines]
            lows = [float(k[3]) for k in klines]
            closes = [float(k[4]) for k in klines]
            sig = evaluate_symbol(symbol, timeframe, opens, highs, lows, closes, **kwargs)
            if sig:
                signals.append(sig)
    return signals
