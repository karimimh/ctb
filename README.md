# RSI Divergence Crypto Trading Simulator

This project simulates a long-only RSI divergence strategy over Binance USDC pairs on 4H candles. The simulator follows the business rules outlined in `INSTRUCTIONS.md`:

- Start with $1,000 of capital.
- Trade at most four assets simultaneously, allocating up to 25% of equity per position.
- Evaluate bullish RSI divergences where the second swing low occurred between 8 and 40 hours before the current candle.
- Enter via limit order at the midpoint between the second swing low and its candle close.
- Cancel entry orders that are not filled within three candles (12 hours).
- Manage an initial stop 5% beneath the second swing low and take profit 10% above entry; close positions after 30 candles if neither is hit.

The simulator replays historical 4H candles from the previous 365 days, printing order placement, fills, exits, and the final profit summary.

## Requirements

- Python 3.11+
- [`requests`](https://docs.python-requests.org/) for Binance REST access
- [`python-dotenv`](https://pypi.org/project/python-dotenv/) for loading environment variables from `.env`

Install dependencies with:

```bash
python -m pip install -r requirements.txt
```

## Configuration

Copy `.env.example` to `.env` and tweak the parameters before running the simulator:

- `SIM_INITIAL_CAPITAL`, `SIM_CAPITAL_PER_TRADE`, `SIM_MAX_OPEN_POSITIONS`, and `SIM_MIN_TRADE_ALLOCATION` control portfolio sizing.
- `SIM_TIMEFRAME` (currently `4h`), RSI/detection settings (`SIM_RSI_PERIOD`, `SIM_SWING_K`), and divergence window limits (`SIM_OPPORTUNITY_MIN_CANDLES`, `SIM_OPPORTUNITY_MAX_CANDLES`) drive signal selection.
- `SIM_STOP_LOSS_PCT`, `SIM_TAKE_PROFIT_PCT`, `SIM_MAX_ENTRY_WAIT_CANDLES`, and `SIM_MAX_HOLD_CANDLES` define trade management rules.
- `SIM_DEFAULT_DAYS` and `SIM_SYMBOLS_LIMIT` provide default backtest scope when CLI flags are omitted.
- `BINANCE_API_KEY`, `BINANCE_API_SECRET`, and `SIM_SANDBOX` configure exchange connectivity.

Command-line options can override many of these values at runtime (for example, `--days` or `--symbols-limit`).

## Usage

Fetch data from Binance and run the simulation:

```bash
python simulate.py --days 365
```

Optional arguments:

- `--symbols-limit N` – restrict the number of USDC symbols to backtest (useful to keep API calls manageable during development).
- `--api-key` / `--api-secret` – supply Binance API credentials if you need signed endpoints (not required for public kline data).
- `--sandbox` – target the Binance sandbox environment.

The script prints each significant event and a final equity summary.

## Running Tests

Basic utility tests are provided and can be executed with:

```bash
python -m unittest
```

## Notes & Assumptions

- Entry orders wait a maximum of three candles for a fill; this was chosen as a sensible default because the requirement only specified "within MAX_ENTRY_WAIT_SPAN" without a value.
- If a candle hits both stop-loss and take-profit levels, the simulator prioritises the stop-loss to model a conservative fill order.
- When sufficient historical data is unavailable for a symbol, it is skipped.
