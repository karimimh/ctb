from collections.abc import Iterable
from datetime import datetime, timedelta, timezone
from typing import Dict, Iterable, List, Optional
import csv
from pathlib import Path

from api.binance_client import BinanceClient

# Binance kline raw format indices we use (documentation reference):
# 0 open time (ms), 1 open, 2 high, 3 low, 4 close, 5 volume, 6 close time, ... we only persist first 6 for now.
KLINE_HEADER = [
    "open_time", "open", "high", "low", "close", "volume", "close_time"
]


def fetch_symbol_universe(client: BinanceClient,
                          limit: Optional[int]) -> List[str]:
    symbols = client.fetch_symbols_usdc(limit=limit)
    return sorted(symbols)


def download_klines(client: BinanceClient, symbols: Iterable[str], interval: str, start_ms: int, end_ms: int,
                    save_dir: Optional[str] = None, save: bool = False) -> Dict[str, List[List[float]]]:
    """Download klines for symbols; optionally save each symbol to a CSV.

    CSV schema: open_time, open, high, low, close, volume, close_time (UTC ms)
    File name pattern: {symbol}_{interval}.csv
    """
    out: Dict[str, List[List[float]]] = {}
    path_dir: Optional[Path] = Path(save_dir).expanduser().resolve() if save_dir else None
    if save and path_dir:
        path_dir.mkdir(parents=True, exist_ok=True)
    for symbol in symbols:
        print(f"Downloading klines for {symbol}")
        data = client.fetch_klines_range(symbol, interval, start_ms, end_ms)
        if not data:
            continue
        out[symbol] = data
        if save and path_dir:
            fp = path_dir / f"{symbol}_{interval}.csv"
            # Write / overwrite
            with fp.open("w", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(KLINE_HEADER)
                for row in data:
                    # Row includes many more fields; keep first 7 if present
                    trimmed = row[:7] if len(row) >= 7 else row
                    writer.writerow(trimmed)
    return out


def load_klines_from_csv(directory: str, interval: str, symbols: Optional[Iterable[str]] = None) -> Dict[str, List[List[float]]]:
    """Load klines from CSV cache.

    Expects files named {symbol}_{interval}.csv with header KLINE_HEADER.
    Returns dict symbol -> list of raw kline arrays in Binance-compatible shape (at least first 6 fields).
    """
    result: Dict[str, List[List[float]]] = {}
    path_dir = Path(directory).expanduser().resolve()
    if not path_dir.exists():
        return result
    chosen = set(symbols) if symbols else None
    for fp in path_dir.glob(f"*_{interval}.csv"):
        symbol = fp.name.rsplit(f"_{interval}.csv", 1)[0]
        if chosen and symbol not in chosen:
            continue
        rows: List[List[float]] = []
        with fp.open("r", newline="") as f:
            reader = csv.DictReader(f)
            for line in reader:
                try:
                    open_time = int(line["open_time"])  # ms
                    open_ = float(line["open"])
                    high = float(line["high"])
                    low = float(line["low"])
                    close = float(line["close"])
                    volume = float(line["volume"])
                    close_time = int(line.get("close_time", open_time + 1))
                except (KeyError, ValueError):  # malformed row -> skip
                    continue
                # Reconstruct partial Binance row structure with placeholders for missing fields
                rows.append([
                    open_time,
                    f"{open_}",
                    f"{high}",
                    f"{low}",
                    f"{close}",
                    f"{volume}",
                    close_time,
                ])
        if rows:
            # Ensure sorted by open time
            rows.sort(key=lambda r: int(r[0]))
            result[symbol] = rows
    return result


def datetime_to_ms(dt: datetime) -> int:
    return int(dt.timestamp() * 1000)


def align_to_interval(dt: datetime, hours: int) -> datetime:
    return dt - timedelta(
        hours=dt.hour % hours,
        minutes=dt.minute,
        seconds=dt.second,
        microseconds=dt.microsecond,
    )


def build_timeline(start: datetime, end: datetime,
                   step_hours: int) -> List[datetime]:
    timeline: List[datetime] = []
    cur = start
    while cur <= end:
        timeline.append(cur)
        cur += timedelta(hours=step_hours)
    return timeline


def derive_timeline_from_klines(klines_by_symbol: Dict[str, List[List[float]]], step_hours: int) -> List[datetime]:
    """Given loaded klines determine a unified timeline based on min/max open time.

    We look across all symbols for the earliest and latest open_time (ms) and build
    an aligned hourly-step timeline. Assumes klines are already aligned to the given timeframe.
    """
    min_ms: Optional[int] = None
    max_ms: Optional[int] = None
    for rows in klines_by_symbol.values():
        if not rows:
            continue
        first = int(rows[0][0])
        last = int(rows[-1][0])
        if min_ms is None or first < min_ms:
            min_ms = first
        if max_ms is None or last > max_ms:
            max_ms = last
    if min_ms is None or max_ms is None:
        return []
    start = datetime.fromtimestamp(min_ms / 1000, tz=timezone.utc)
    end = datetime.fromtimestamp(max_ms / 1000, tz=timezone.utc)
    return build_timeline(start, end, step_hours)
