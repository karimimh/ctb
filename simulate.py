from __future__ import annotations

import argparse
import logging
import math
import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Dict, Iterable, List, Optional

from pathlib import Path

from Config import Config
from ctb.api.binance_client import BinanceClient
from ctb.technical_analysis.divergence import DivergenceSignal, find_divergences
from ctb.technical_analysis.indicators import rsi


LOG_FILE_ENV_VAR = "SIM_LOG_FILE"
DEFAULT_LOG_FILE = Path(os.getenv(LOG_FILE_ENV_VAR, "simulation.log")).expanduser()

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
logger.propagate = False

_logging_configured = False


def configure_logging(log_file: Path | str = DEFAULT_LOG_FILE) -> None:
	global _logging_configured
	if _logging_configured:
		return
	log_path = Path(log_file)
	log_path.parent.mkdir(parents=True, exist_ok=True)
	file_handler = logging.FileHandler(log_path, mode="a", encoding="utf-8")
	file_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
	logger.addHandler(file_handler)
	_logging_configured = True


configure_logging()


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
	def from_binance(cls, raw: List[float]) -> "Kline":
		open_time_ms = int(raw[0])
		open_time = datetime.fromtimestamp(open_time_ms / 1000, tz=timezone.utc)
		return cls(
			open_time=open_time,
			open_time_ms=open_time_ms,
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
	divergences: List[DivergenceSignal]
	time_to_index: Dict[int, int]
	used_divergences: set[int] = field(default_factory=set)


@dataclass
class PendingOrder:
	symbol: str
	allocation: float
	entry_price: float
	placed_index: int
	expiry_index: int
	stop_loss: float
	take_profit: float
	divergence_index: int


@dataclass
class Position:
	symbol: str
	entry_price: float
	quantity: float
	entry_index: int
	stop_loss: float
	take_profit: float
	divergence_index: int
	last_price: float


@dataclass
class SimulationResult:
	final_equity: float
	cash: float
	realized_pnl: float
	open_positions: int
	pending_orders: int


def _datetime_to_ms(dt: datetime) -> int:
	return int(dt.timestamp() * 1000)


def _format_time(dt: datetime) -> str:
	return dt.strftime("%Y-%m-%d %H:%M")


def _align_to_interval(dt: datetime, hours: int) -> datetime:
	remainder = dt.hour % hours
	aligned = dt - timedelta(hours=remainder, minutes=dt.minute, seconds=dt.second, microseconds=dt.microsecond)
	return aligned


def _build_timeline(start: datetime, end: datetime, step_hours: int) -> List[datetime]:
	timeline: List[datetime] = []
	current = start
	while current <= end:
		timeline.append(current)
		current += timedelta(hours=step_hours)
	return timeline


def _is_divergence_valid(klines: List[Kline], divergence_idx: int, current_idx: int,
						 stop_price: float, take_profit_price: float) -> bool:
	if current_idx <= divergence_idx:
		return False
	for i in range(divergence_idx + 1, current_idx):
		candle = klines[i]
		if candle.low <= stop_price or candle.high >= take_profit_price:
			return False
	return True


class RSIDivergenceSimulator:
	def __init__(self, symbol_data: Dict[str, SymbolData], timeline: List[datetime],
			 config: Config) -> None:
		self.symbol_data = symbol_data
		self.timeline = timeline
		self.config = config
		self.cash = config.initial_capital
		self.pending_orders: List[PendingOrder] = []
		self.positions: Dict[str, Position] = {}
		self.realized_pnl = 0.0

	def _log(self, message: str) -> None:
		logger.info(message)

	def portfolio_value(self) -> float:
		value = self.cash
		for pos in self.positions.values():
			value += pos.last_price * pos.quantity
		return value

	def _available_slots(self) -> int:
		return self.config.max_open_positions - (len(self.positions) + len(self.pending_orders))

	def _cancel_expired_orders(self, symbol: str, current_idx: int, current_time: datetime) -> None:
		to_cancel = [order for order in self.pending_orders
				 if order.symbol == symbol and current_idx > order.expiry_index]
		for order in to_cancel:
			self.pending_orders.remove(order)
			self.cash += order.allocation
			self._log(f"{_format_time(current_time)} cancel BUY {symbol} @ {order.entry_price:.4f} (expired)")

	def _pick_divergence(self, data: SymbolData, current_idx: int) -> Optional[DivergenceSignal]:
		for divergence in reversed(data.divergences):
			if divergence.kind != 'bullish':
				continue
			if divergence.candle_index in data.used_divergences:
				continue
			if divergence.candle_index >= current_idx:
				continue
			age = current_idx - divergence.candle_index
			if self.config.opportunity_min_candles <= age <= self.config.opportunity_max_candles:
				return divergence
		return None

	def _scan_for_opportunities(self, symbol: str, current_idx: int, current_time: datetime) -> None:
		if self._available_slots() <= 0:
			return
		if symbol in self.positions:
			return
		if any(order.symbol == symbol for order in self.pending_orders):
			return
		data = self.symbol_data[symbol]
		divergence = self._pick_divergence(data, current_idx)
		if not divergence:
			return
		if divergence.candle_index >= len(data.klines):
			return
		divergence_candle = data.klines[divergence.candle_index]
		stop_price = divergence_candle.low * (1 - self.config.stop_loss_pct)
		tp_price = divergence_candle.low * (1 + self.config.take_profit_pct)
		if not _is_divergence_valid(data.klines, divergence.candle_index, current_idx, stop_price, tp_price):
			return
		entry_price = (divergence_candle.low + divergence_candle.close) / 2
		equity = self.portfolio_value()
		allocation = min(self.cash, equity * self.config.capital_per_trade)
		if allocation < self.config.min_trade_allocation:
			return
		expiry_idx = current_idx + self.config.max_entry_wait_candles
		order = PendingOrder(
			symbol=symbol,
			allocation=allocation,
			entry_price=entry_price,
			placed_index=current_idx,
			expiry_index=expiry_idx,
			stop_loss=stop_price,
			take_profit=entry_price * (1 + self.config.take_profit_pct),
			divergence_index=divergence.candle_index,
		)
		self.cash -= allocation
		self.pending_orders.append(order)
		data.used_divergences.add(divergence.candle_index)
		self._log(
			f"{_format_time(current_time)} place BUY {symbol} @ {entry_price:.4f} "
			f"risk {stop_price:.4f} target {order.take_profit:.4f} alloc {allocation:.2f}"
		)

	def _process_pending_orders(self, symbol: str, current_idx: int,
								kline: Kline, current_time: datetime) -> None:
		orders = [order for order in self.pending_orders if order.symbol == symbol]
		for order in orders:
			if kline.low <= order.entry_price:
				quantity = order.allocation / order.entry_price
				position = Position(
					symbol=symbol,
					entry_price=order.entry_price,
					quantity=quantity,
					entry_index=current_idx,
					stop_loss=order.stop_loss,
					take_profit=order.take_profit,
					divergence_index=order.divergence_index,
					last_price=kline.close,
				)
				self.positions[symbol] = position
				self.pending_orders.remove(order)
				self._log(
					f"{_format_time(current_time)} filled BUY {symbol} qty {quantity:.6f} "
					f"@ {order.entry_price:.4f}"
				)

	def _process_positions(self, symbol: str, current_idx: int,
						   kline: Kline, current_time: datetime) -> None:
		position = self.positions.get(symbol)
		if not position:
			return
		position.last_price = kline.close
		exit_price: Optional[float] = None
		exit_reason: Optional[str] = None
		if kline.low <= position.stop_loss:
			exit_price = position.stop_loss
			exit_reason = "stop-loss"
		elif kline.high >= position.take_profit:
			exit_price = position.take_profit
			exit_reason = "take-profit"
		else:
			candles_held = current_idx - position.entry_index
			if candles_held >= self.config.max_hold_candles:
				exit_price = kline.close
				exit_reason = "max-hold"
		if exit_price is not None:
			proceeds = exit_price * position.quantity
			self.cash += proceeds
			pnl = proceeds - position.entry_price * position.quantity
			self.realized_pnl += pnl
			self._log(
				f"{_format_time(current_time)} exit {symbol} @ {exit_price:.4f} "
				f"({exit_reason}) pnl {pnl:.2f}"
			)
			del self.positions[symbol]

	def run(self) -> SimulationResult:
		if not self.timeline:
			raise ValueError("Timeline is empty")
		for current_time in self.timeline:
			open_time_ms = _datetime_to_ms(current_time)
			symbols_with_candle = {
				symbol: data.time_to_index.get(open_time_ms)
				for symbol, data in self.symbol_data.items()
			}
			symbols_with_candle = {s: idx for s, idx in symbols_with_candle.items() if idx is not None}
			if not symbols_with_candle:
				continue
			for symbol, current_idx in symbols_with_candle.items():
				self._cancel_expired_orders(symbol, current_idx, current_time)
			for symbol, current_idx in symbols_with_candle.items():
				self._scan_for_opportunities(symbol, current_idx, current_time)
			for symbol, current_idx in symbols_with_candle.items():
				kline = self.symbol_data[symbol].klines[current_idx]
				self._process_pending_orders(symbol, current_idx, kline, current_time)
			for symbol, current_idx in symbols_with_candle.items():
				kline = self.symbol_data[symbol].klines[current_idx]
				self._process_positions(symbol, current_idx, kline, current_time)
		final_equity = self.portfolio_value()
		self._log(
			f"Simulation finished: final equity {final_equity:.2f} USD, "
			f"realized pnl {self.realized_pnl:.2f} USD"
		)
		return SimulationResult(
			final_equity=final_equity,
			cash=self.cash,
			realized_pnl=self.realized_pnl,
			open_positions=len(self.positions),
			pending_orders=len(self.pending_orders),
		)


def fetch_symbol_universe(client: BinanceClient, limit: Optional[int]) -> List[str]:
	symbols = client.fetch_symbols_usdc(limit=limit)
	return sorted(symbols)


def download_klines(client: BinanceClient, symbols: Iterable[str], interval: str,
					start_ms: int, end_ms: int) -> Dict[str, List[List[float]]]:
	klines: Dict[str, List[List[float]]] = {}
	for symbol in symbols:
		print(f"Downloading klines for {symbol}")
		data = client.fetch_klines_range(symbol, interval, start_ms, end_ms)
		if data:
			klines[symbol] = data
	return klines


def prepare_symbol_data(klines_by_symbol: Dict[str, List[List[float]]], start_ms: int,
					 config: Config) -> Dict[str, SymbolData]:
	symbol_data: Dict[str, SymbolData] = {}
	for symbol, rows in klines_by_symbol.items():
		klines = [Kline.from_binance(row) for row in rows if int(row[0]) >= start_ms]
		if len(klines) < config.rsi_period + 5:
			continue
		closes = [k.close for k in klines]
		rsi_values = rsi(closes, period=config.rsi_period)
		if all(math.isnan(val) for val in rsi_values):
			continue
		divergences = find_divergences(symbol, config.timeframe, closes, rsi_values, k=config.swing_k)
		if not divergences:
			divergences = []
		time_to_index = {kline.open_time_ms: idx for idx, kline in enumerate(klines)}
		symbol_data[symbol] = SymbolData(
			symbol=symbol,
			klines=klines,
			divergences=divergences,
			time_to_index=time_to_index,
		)
	return symbol_data


def run_simulation(config: Config, days: Optional[int] = None,
			   symbols_limit: Optional[int] = None,
			   api_key: Optional[str] = None,
			   api_secret: Optional[str] = None,
			   sandbox: Optional[bool] = None) -> SimulationResult:
	days = config.default_days if days is None else days
	symbols_limit = config.default_symbols_limit if symbols_limit is None else symbols_limit
	api_key = config.binance_api_key if api_key is None else api_key
	api_secret = config.binance_api_secret if api_secret is None else api_secret
	sandbox = config.sandbox if sandbox is None else sandbox
	timeframe_hours = config.timeframe_hours
	now = datetime.now(timezone.utc)
	base_time = now - timedelta(minutes=now.minute, seconds=now.second, microseconds=now.microsecond)
	end_time = _align_to_interval(base_time, timeframe_hours)
	start_time = end_time - timedelta(days=days)
	timeline = _build_timeline(start_time, end_time, timeframe_hours)
	client = BinanceClient(api_key=api_key, api_secret=api_secret, sandbox=sandbox)
	symbols = fetch_symbol_universe(client, symbols_limit)
	start_ms = _datetime_to_ms(start_time)
	end_ms = _datetime_to_ms(end_time)
	klines_by_symbol = download_klines(client, symbols, config.timeframe, start_ms, end_ms)
	if not klines_by_symbol:
		raise RuntimeError("No klines downloaded; aborting simulation")
	symbol_data = prepare_symbol_data(klines_by_symbol, start_ms, config)
	if not symbol_data:
		raise RuntimeError("No symbol data available after preparation")
	simulator = RSIDivergenceSimulator(symbol_data, timeline, config)
	return simulator.run()


def parse_args() -> argparse.Namespace:
	parser = argparse.ArgumentParser(description="Simulate RSI divergence trading strategy on Binance USDC pairs")
	parser.add_argument("--days", type=int, default=None, help="Backtest period in days (defaults to SIM_DEFAULT_DAYS)")
	parser.add_argument("--symbols-limit", type=int, default=None, help="Limit number of USDC symbols (defaults to SIM_SYMBOLS_LIMIT)")
	parser.add_argument("--api-key", type=str, default=None, help="Binance API key (only needed for private endpoints)")
	parser.add_argument("--api-secret", type=str, default=None, help="Binance API secret")
	parser.add_argument("--sandbox", action="store_true", help="Use Binance sandbox environment")
	return parser.parse_args()


def main() -> None:
	args = parse_args()
	config = Config.load()
	try:
		result = run_simulation(
			config=config,
			days=args.days,
			symbols_limit=args.symbols_limit,
			api_key=args.api_key,
			api_secret=args.api_secret,
			sandbox=True if args.sandbox else None,
		)
		logger.info(
			"Final equity: %.2f USD | Realized PnL: %.2f USD | Cash: %.2f USD",
			result.final_equity,
			result.realized_pnl,
			result.cash,
		)
		if result.open_positions or result.pending_orders:
			logger.warning(
				"%d open positions and %d pending orders remain at end of simulation",
				result.open_positions,
				result.pending_orders,
			)
	except Exception as exc:  # noqa: BLE001
		logger.exception("Simulation failed")
		raise SystemExit(f"Simulation failed: {exc}") from exc


if __name__ == "__main__":
	main()

