from __future__ import annotations
from typing import Dict, List, Sequence
from ctb.technical_analysis.divergence import DivergenceSignal, find_latest_divergence
from ctb.technical_analysis.indicators import rsi


def evaluate_symbol(symbol: str, timeframe: str, closes: Sequence[float],
                    rsi_period: int, swing_k: int) -> DivergenceSignal | None:
    rsi_vals = rsi(closes, period=rsi_period)
    return find_latest_divergence(symbol,
                                  timeframe,
                                  closes,
                                  rsi_vals,
                                  k=swing_k)


def run_strategy(symbols: Sequence[str],
                 klines_by_symbol_and_tf: Dict[str, Dict[str, List[List]]],
                 rsi_period: int, swing_k: int) -> list[DivergenceSignal]:
    signals: list[DivergenceSignal] = []
    for symbol in symbols:
        per_tf = klines_by_symbol_and_tf.get(symbol, {})
        for timeframe, klines in per_tf.items():
            closes = [float(k[4]) for k in klines]
            sig = evaluate_symbol(symbol, timeframe, closes, rsi_period,
                                  swing_k)
            if sig:
                signals.append(sig)
    return signals
