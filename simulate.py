from __future__ import annotations

from api.binance_client import BinanceClient
from config import Config, BreakoutSettings
from strategies.breakout_trend import BreakoutSignal, generate_breakout_signals
"""Dedicated simulator for the breakout / trend-following strategy.

Usage (after setting up environment like the main simulator):
  python3 simulate_breakout.py --days 365 --symbols-limit 40

This simulator reuses general connectivity / timeframe config from the
existing `Config` class but has its own environment-tunable parameters
prefixed with BR_. We keep it separate from the original `simulate.py`
to allow rapid iteration without destabilising other strategies.

DISCLAIMER: This is a research backtest harness. Historical results
do NOT guarantee future returns. Use at your own risk.
"""

import argparse
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Dict, Iterable, List, Optional

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logger.addHandler(handler)

BreakoutConfig = BreakoutSettings  # backward compatibility alias


# --- Data structures ------------------------------------------------------


@dataclass(frozen=True)
class Kline:
    open_time: datetime
    open_time_ms: int
    open: float
    high: float
    low: float
    close: float
    volume: float

    @classmethod
    def from_binance(cls, raw: List[float]) -> "Kline":  # raw list from API
        ts = int(raw[0])
        return cls(
            open_time=datetime.fromtimestamp(ts / 1000, tz=timezone.utc),
            open_time_ms=ts,
            open=float(raw[1]),
            high=float(raw[2]),
            low=float(raw[3]),
            close=float(raw[4]),
            volume=float(raw[5]),
        )


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


# --- Helper functions -----------------------------------------------------


def _datetime_to_ms(dt: datetime) -> int:
    return int(dt.timestamp() * 1000)


def _align_to_interval(dt: datetime, hours: int) -> datetime:
    return dt - timedelta(
        hours=dt.hour % hours,
        minutes=dt.minute,
        seconds=dt.second,
        microseconds=dt.microsecond,
    )


def _build_timeline(start: datetime, end: datetime,
                    step_hours: int) -> List[datetime]:
    timeline: List[datetime] = []
    cur = start
    while cur <= end:
        timeline.append(cur)
        cur += timedelta(hours=step_hours)
    return timeline


def fetch_symbol_universe(client: BinanceClient,
                          limit: Optional[int]) -> List[str]:
    symbols = client.fetch_symbols_usdc(limit=limit)
    return sorted(symbols)


def download_klines(client: BinanceClient, symbols: Iterable[str],
                    interval: str, start_ms: int,
                    end_ms: int) -> Dict[str, List[List[float]]]:
    out: Dict[str, List[List[float]]] = {}
    for symbol in symbols:
        print(f"Downloading klines for {symbol}")
        data = client.fetch_klines_range(symbol, interval, start_ms, end_ms)
        if data:
            out[symbol] = data
    return out


def prepare_symbol_data(klines_by_symbol: Dict[str, List[List[float]]],
                        start_ms: int,
                        bcfg: BreakoutSettings) -> Dict[str, SymbolData]:
    symbol_data: Dict[str, SymbolData] = {}
    for symbol, rows in klines_by_symbol.items():
        klines = [Kline.from_binance(r) for r in rows if int(r[0]) >= start_ms]
        if len(klines) < max(bcfg.slow_ema_period, bcfg.channel_lookback) + 10:
            continue
        closes = [k.close for k in klines]
        highs = [k.high for k in klines]
        lows = [k.low for k in klines]
        # Quick pre-check so we don't waste time generating signals on flat series
        if max(closes) - min(closes) == 0:
            continue
        breakouts = generate_breakout_signals(
            closes,
            highs,
            lows,
            fast_ema_period=bcfg.fast_ema_period,
            slow_ema_period=bcfg.slow_ema_period,
            atr_period=bcfg.atr_period,
            channel_lookback=bcfg.channel_lookback,
            entry_atr_buffer=bcfg.entry_atr_buffer,
            stop_atr_mult=bcfg.stop_atr_mult,
            reward_risk=bcfg.reward_risk,
            min_atr_pct=bcfg.min_atr_pct,
        )
        time_to_index = {k.open_time_ms: i for i, k in enumerate(klines)}
        symbol_data[symbol] = SymbolData(symbol=symbol,
                                         klines=klines,
                                         time_to_index=time_to_index,
                                         breakouts=breakouts)
    return symbol_data


# --- Simulator ------------------------------------------------------------


class BreakoutSimulator:

    def __init__(self, symbol_data: Dict[str,
                                         SymbolData], timeline: List[datetime],
                 base_cfg: Config, bcfg: BreakoutSettings) -> None:
        self.symbol_data = symbol_data
        self.timeline = timeline
        self.base_cfg = base_cfg
        self.bcfg = bcfg
        self.cash = base_cfg.initial_capital
        self.positions: Dict[str, Position] = {}
        self.realized_pnl = 0.0

    # --- Accounting helpers ---
    def portfolio_value(self) -> float:
        v = self.cash
        for p in self.positions.values():
            v += p.last_price * p.quantity
        return v

    # --- Core methods ---
    def _maybe_enter(self, symbol: str, idx: int, now: datetime) -> None:
        if symbol in self.positions:
            return
        data = self.symbol_data[symbol]
        sig = None
        for s in reversed(data.breakouts):
            if s.index == idx:
                sig = s
                break
            if s.index < idx:
                break  # breakouts are chronological
        if not sig:
            return
        entry = sig.entry_price
        stop = sig.stop_price
        risk_per_unit = entry - stop
        if risk_per_unit <= 0:
            return
        equity = self.portfolio_value()
        risk_capital = equity * self.bcfg.risk_per_trade_pct
        qty = risk_capital / risk_per_unit
        cost = qty * entry
        if cost > self.cash:
            qty = self.cash / entry
            cost = qty * entry
        if cost < self.bcfg.min_trade_allocation:
            return
        tp = sig.reward_risk_target
        self.cash -= cost
        self.positions[symbol] = Position(
            symbol=symbol,
            entry_price=entry,
            quantity=qty,
            entry_index=idx,
            stop_loss=stop,
            take_profit=tp,
            last_price=entry,
            initial_risk=risk_per_unit,
        )
        logger.info(
            f"{now.isoformat()} ENTER {symbol} qty {qty:.6f} @ {entry:.5f} stop {stop:.5f} tp {tp:.5f} risk {risk_per_unit:.5f}"
        )

    def _manage_position(self, symbol: str, idx: int, now: datetime) -> None:
        pos = self.positions.get(symbol)
        if not pos:
            return
        kline = self.symbol_data[symbol].klines[idx]
        pos.last_price = kline.close
        exit_price: float | None = None
        exit_reason: str | None = None
        # Hard SL / TP
        if kline.low <= pos.stop_loss:
            exit_price = pos.stop_loss
            exit_reason = "stop-loss"
        elif kline.high >= pos.take_profit:
            exit_price = pos.take_profit
            exit_reason = "take-profit"
        else:
            # Trailing activation
            rr_unrealized = (kline.close - pos.entry_price) / pos.initial_risk
            if rr_unrealized >= self.bcfg.trail_activate_rr:
                pos.active_trailing = True
            if pos.active_trailing:
                # Trail to either locked RR or ATR-based dynamic barrier
                # Compute ATR locally (avoid recomputing arrays) – approximate with rolling high/low range
                # For accuracy you could pre-store ATR; here acceptable to reuse initial risk * ratio
                # We re-calc adaptive trailing stop: max(current stop, entry + lock_rr * risk, close - atr_mult * risk)
                lock_price = pos.entry_price + self.bcfg.trail_lock_rr * pos.initial_risk
                dynamic_price = kline.close - self.bcfg.trail_atr_mult * pos.initial_risk
                new_stop = max(pos.stop_loss, lock_price, dynamic_price)
                if new_stop > pos.stop_loss:
                    pos.stop_loss = new_stop
            held = idx - pos.entry_index
            if held >= self.bcfg.max_hold_candles:
                exit_price = kline.close
                exit_reason = "max-hold"
        if exit_price is not None:
            proceeds = exit_price * pos.quantity
            pnl = proceeds - pos.entry_price * pos.quantity
            self.cash += proceeds
            self.realized_pnl += pnl
            logger.info(
                f"{now.isoformat()} EXIT {symbol} @ {exit_price:.5f} ({exit_reason}) pnl {pnl:.2f}"
            )
            del self.positions[symbol]

    def run(self) -> SimulationResult:
        if not self.timeline:
            raise ValueError("Timeline empty")
        for now in self.timeline:
            ms = _datetime_to_ms(now)
            # Which symbols have a candle at this time
            idx_by_symbol = {
                sym: data.time_to_index.get(ms)
                for sym, data in self.symbol_data.items()
            }
            idx_by_symbol = {
                s: i
                for s, i in idx_by_symbol.items() if i is not None
            }
            if not idx_by_symbol:
                continue
            # Entries first
            # Respect max open positions (no partial skipping across ordering for now)
            free_slots = self.bcfg.max_open_positions - len(self.positions)
            if free_slots > 0:
                for sym, i in idx_by_symbol.items():
                    if len(self.positions) >= self.bcfg.max_open_positions:
                        break
                    self._maybe_enter(sym, i, now)
            # Management
            for sym, i in idx_by_symbol.items():
                self._manage_position(sym, i, now)
        final_equity = self.portfolio_value()
        logger.info(
            f"Breakout Simulation complete: equity {final_equity:.2f} cash {self.cash:.2f} realized {self.realized_pnl:.2f}"
        )
        return SimulationResult(
            final_equity=final_equity,
            cash=self.cash,
            realized_pnl=self.realized_pnl,
            open_positions=len(self.positions),
        )


# --- Entrypoint -----------------------------------------------------------


def run_breakout_simulation(
    days: Optional[int] = None,
    symbols_limit: Optional[int] = None,
    api_key: Optional[str] = None,
    api_secret: Optional[str] = None,
    sandbox: Optional[bool] = None,
) -> SimulationResult:
    base_cfg = Config.load()
    days = base_cfg.default_days if days is None else days
    symbols_limit = base_cfg.default_symbols_limit if symbols_limit is None else symbols_limit
    api_key = base_cfg.binance_api_key if api_key is None else api_key
    api_secret = base_cfg.binance_api_secret if api_secret is None else api_secret
    sandbox = base_cfg.sandbox if sandbox is None else sandbox
    if not base_cfg.breakout:
        raise RuntimeError("Breakout settings missing from configuration")
    bcfg = base_cfg.breakout
    timeframe_hours = base_cfg.timeframe_hours
    now = datetime.now(timezone.utc)
    base_time = now - timedelta(
        minutes=now.minute, seconds=now.second, microseconds=now.microsecond)
    end_time = _align_to_interval(base_time, timeframe_hours)
    start_time = end_time - timedelta(days=days)
    timeline = _build_timeline(start_time, end_time, timeframe_hours)
    client = BinanceClient(api_key=api_key,
                           api_secret=api_secret,
                           sandbox=sandbox)
    symbols = fetch_symbol_universe(client, symbols_limit)
    start_ms = _datetime_to_ms(start_time)
    end_ms = _datetime_to_ms(end_time)
    klines_by_symbol = download_klines(client, symbols, base_cfg.timeframe,
                                       start_ms, end_ms)
    if not klines_by_symbol:
        raise RuntimeError("No klines downloaded; aborting")
    symbol_data = prepare_symbol_data(klines_by_symbol, start_ms, bcfg)
    if not symbol_data:
        raise RuntimeError("No symbol data after preparation")
    sim = BreakoutSimulator(symbol_data, timeline, base_cfg, bcfg)
    return sim.run()


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Breakout strategy simulator")
    p.add_argument("--days",
                   type=int,
                   default=None,
                   help="Backtest period in days")
    p.add_argument("--symbols-limit",
                   type=int,
                   default=None,
                   help="Limit number of USDC symbols")
    p.add_argument("--api-key", type=str, default=None, help="Binance API key")
    p.add_argument("--api-secret",
                   type=str,
                   default=None,
                   help="Binance API secret")
    p.add_argument("--sandbox",
                   action="store_true",
                   help="Use Binance sandbox")
    return p.parse_args()


def main() -> None:
    args = parse_args()
    try:
        result = run_breakout_simulation(
            days=args.days,
            symbols_limit=args.symbols_limit,
            api_key=args.api_key,
            api_secret=args.api_secret,
            sandbox=True if args.sandbox else None,
        )
        logger.info(
            "Breakout Final equity: %.2f | Realized PnL: %.2f | Cash: %.2f",
            result.final_equity,
            result.realized_pnl,
            result.cash,
        )
        if result.open_positions:
            logger.warning("%d open positions remain at end",
                           result.open_positions)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Breakout simulation failed")
        raise SystemExit(f"Breakout simulation failed: {exc}") from exc


if __name__ == "__main__":
    main()
