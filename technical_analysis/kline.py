from dataclasses import dataclass
from datetime import datetime, timezone
from typing import List


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
