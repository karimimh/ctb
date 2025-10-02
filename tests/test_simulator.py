from __future__ import annotations

import os
import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock

from Config import Config
from simulate import Kline, _align_to_interval, _is_divergence_valid


class SimulatorUtilsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.start = datetime(2024, 1, 1, tzinfo=timezone.utc)

    def _kline(self, offset_hours: int, low: float, high: float, close: float) -> Kline:
        ts = self.start + timedelta(hours=offset_hours)
        return Kline(
            open_time=ts,
            open_time_ms=int(ts.timestamp() * 1000),
            open=close,
            high=high,
            low=low,
            close=close,
            volume=100.0,
        )

    def test_is_divergence_valid_true_when_prices_stay_within_bounds(self) -> None:
        klines = [
            self._kline(0, low=90, high=110, close=100),
            self._kline(4, low=92, high=108, close=100),
            self._kline(8, low=93, high=109, close=101),
            self._kline(12, low=94, high=110, close=102),
        ]
        self.assertTrue(_is_divergence_valid(klines, 0, 3, stop_price=85, take_profit_price=115))

    def test_is_divergence_invalid_when_stop_breached(self) -> None:
        klines = [
            self._kline(0, low=90, high=110, close=100),
            self._kline(4, low=84, high=108, close=100),
            self._kline(8, low=93, high=109, close=101),
        ]
        self.assertFalse(_is_divergence_valid(klines, 0, 2, stop_price=85, take_profit_price=115))

    def test_is_divergence_invalid_when_take_profit_hit(self) -> None:
        klines = [
            self._kline(0, low=90, high=110, close=100),
            self._kline(4, low=92, high=120, close=105),
            self._kline(8, low=93, high=109, close=101),
        ]
        self.assertFalse(_is_divergence_valid(klines, 0, 2, stop_price=85, take_profit_price=115))

    def test_align_to_interval(self) -> None:
        dt = datetime(2024, 1, 1, 10, 30, tzinfo=timezone.utc)
        aligned = _align_to_interval(dt, 4)
        self.assertEqual(aligned.hour, 8)
        self.assertEqual(aligned.minute, 0)
        self.assertEqual(aligned.tzinfo, timezone.utc)


class ConfigTests(unittest.TestCase):
    def test_load_defaults_when_env_empty(self) -> None:
        with mock.patch.dict(os.environ, {}, clear=True):
            cfg = Config.load()
        self.assertEqual(cfg.initial_capital, 1000.0)
        self.assertEqual(cfg.timeframe, "4h")
        self.assertEqual(cfg.timeframe_hours, 4)
        self.assertAlmostEqual(cfg.capital_per_trade, 0.25)
        self.assertFalse(cfg.sandbox)

    def test_load_overrides_from_env(self) -> None:
        overrides = {
            "SIM_INITIAL_CAPITAL": "1500",
            "SIM_TIMEFRAME": "6h",
            "SIM_CAPITAL_PER_TRADE": "0.5",
            "SIM_DEFAULT_DAYS": "180",
            "SIM_SYMBOLS_LIMIT": "25",
            "SIM_SANDBOX": "true",
            "BINANCE_API_KEY": "abc",
            "BINANCE_API_SECRET": "xyz",
        }
        with mock.patch.dict(os.environ, overrides, clear=True):
            cfg = Config.load()
        self.assertEqual(cfg.initial_capital, 1500.0)
        self.assertEqual(cfg.timeframe_hours, 6)
        self.assertAlmostEqual(cfg.capital_per_trade, 0.5)
        self.assertEqual(cfg.default_days, 180)
        self.assertEqual(cfg.default_symbols_limit, 25)
        self.assertTrue(cfg.sandbox)
        self.assertEqual(cfg.binance_api_key, "abc")
        self.assertEqual(cfg.binance_api_secret, "xyz")


if __name__ == "__main__":
    unittest.main()
