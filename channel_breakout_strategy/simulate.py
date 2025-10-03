from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, List

from api.binance_client import BinanceClient
from channel_breakout_strategy.config import Config
from channel_breakout_strategy.signal import generate_breakout_signals
from technical_analysis.kline import Kline
from utils.util import (align_to_interval, build_timeline, datetime_to_ms,
                        download_klines, fetch_symbol_universe,
                        load_klines_from_csv, derive_timeline_from_klines)

from .models import Position, SimulationResult, SymbolData

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logger.addHandler(handler)


def prepare_symbol_data(klines_by_symbol: Dict[str, List[List[float]]],
                        start_ms: int, cfg: Config) -> Dict[str, SymbolData]:
    symbol_data: Dict[str, SymbolData] = {}
    for symbol, rows in klines_by_symbol.items():
        klines = [Kline.from_binance(r) for r in rows if int(r[0]) >= start_ms]
        if len(klines) < max(cfg.slow_ema_period, cfg.channel_lookback) + 10:
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
            fast_ema_period=cfg.fast_ema_period,
            slow_ema_period=cfg.slow_ema_period,
            atr_period=cfg.atr_period,
            channel_lookback=cfg.channel_lookback,
            entry_atr_buffer=cfg.entry_atr_buffer,
            stop_atr_mult=cfg.stop_atr_mult,
            reward_risk=cfg.reward_risk,
            min_atr_pct=cfg.min_atr_pct,
        )
        time_to_index = {k.open_time_ms: i for i, k in enumerate(klines)}
        symbol_data[symbol] = SymbolData(symbol=symbol,
                                         klines=klines,
                                         time_to_index=time_to_index,
                                         breakouts=breakouts)
    return symbol_data


class BreakoutSimulator:

    def __init__(self, symbol_data: Dict[str, SymbolData],
                 timeline: List[datetime], cfg: Config) -> None:
        self.symbol_data = symbol_data
        self.timeline = timeline
        self.cfg = cfg
        self.cash = cfg.initial_capital
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
        risk_capital = equity * self.cfg.risk_per_trade_pct
        qty = risk_capital / risk_per_unit
        cost = qty * entry
        if cost > self.cash:
            qty = self.cash / entry
            cost = qty * entry
        if cost < self.cfg.min_trade_allocation:
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
            if rr_unrealized >= self.cfg.trail_activate_rr:
                pos.active_trailing = True
            if pos.active_trailing:
                # Trail to either locked RR or ATR-based dynamic barrier
                # Compute ATR locally (avoid recomputing arrays) – approximate with rolling high/low range
                # For accuracy you could pre-store ATR; here acceptable to reuse initial risk * ratio
                # We re-calc adaptive trailing stop: max(current stop, entry + lock_rr * risk, close - atr_mult * risk)
                lock_price = pos.entry_price + self.cfg.trail_lock_rr * pos.initial_risk
                dynamic_price = kline.close - self.cfg.trail_atr_mult * pos.initial_risk
                new_stop = max(pos.stop_loss, lock_price, dynamic_price)
                if new_stop > pos.stop_loss:
                    pos.stop_loss = new_stop
            held = idx - pos.entry_index
            if held >= self.cfg.max_hold_candles:
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
            ms = datetime_to_ms(now)
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
            free_slots = self.cfg.max_open_positions - len(self.positions)
            if free_slots > 0:
                for sym, i in idx_by_symbol.items():
                    if len(self.positions) >= self.cfg.max_open_positions:
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


def run_breakout_simulation() -> SimulationResult:
    cfg = Config.load()
    days = cfg.default_days
    symbols_limit = cfg.default_symbols_limit
    api_key = cfg.binance_api_key
    api_secret = cfg.binance_api_secret
    sandbox = cfg.sandbox
    if not cfg.breakout:
        raise RuntimeError("Breakout settings missing from configuration")
    timeframe_hours = cfg.timeframe_hours
    if cfg.load_klines_from_csv:
        # Load symbol list implicitly from directory (later could restrict)
        klines_by_symbol = load_klines_from_csv(cfg.kline_csv_dir,
                                                cfg.timeframe)
        if not klines_by_symbol:
            raise RuntimeError(
                f"No kline CSV files found in {cfg.kline_csv_dir} for interval {cfg.timeframe}"
            )
        # Build timeline from data range
        timeline = derive_timeline_from_klines(klines_by_symbol,
                                               timeframe_hours)
        if not timeline:
            raise RuntimeError(
                "Unable to derive timeline from loaded kline CSV files")
        # start_ms based on earliest candle
        start_ms = min(int(rows[0][0]) for rows in klines_by_symbol.values())
    else:
        now = datetime.now(timezone.utc)
        base_time = now - timedelta(
            minutes=now.minute,
            seconds=now.second,
            microseconds=now.microsecond)
        end_time = align_to_interval(base_time, timeframe_hours)
        start_time = end_time - timedelta(days=days)
        timeline = build_timeline(start_time, end_time, timeframe_hours)
        client = BinanceClient(api_key=api_key,
                               api_secret=api_secret,
                               sandbox=sandbox)
        symbols = fetch_symbol_universe(client, symbols_limit)
        start_ms = datetime_to_ms(start_time)
        end_ms = datetime_to_ms(end_time)
        klines_by_symbol = download_klines(client,
                                           symbols,
                                           cfg.timeframe,
                                           start_ms,
                                           end_ms,
                                           save_dir=cfg.kline_csv_dir,
                                           save=cfg.save_downloaded_klines)
    if not klines_by_symbol:
        raise RuntimeError("No klines downloaded; aborting")
    symbol_data = prepare_symbol_data(klines_by_symbol, start_ms, cfg)
    if not symbol_data:
        raise RuntimeError("No symbol data after preparation")
    sim = BreakoutSimulator(symbol_data, timeline, cfg)
    return sim.run()


def main() -> None:
    try:
        result = run_breakout_simulation()
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
