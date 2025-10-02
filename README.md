# Crypto Trading Simulator (RSI Divergence & Multi-Factor Strategy)

This project simulates crypto trading strategies over Binance USDC pairs on multi-hour candles. The original implementation focuses on a long-only RSI divergence strategy. A new optional, more advanced *multi-factor trend + RSI* strategy has been added (see "Advanced Strategy"). The simulator follows the business rules outlined in `INSTRUCTIONS.md` for the baseline divergence method:

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

Baseline divergence strategy variables:

- `SIM_INITIAL_CAPITAL`, `SIM_CAPITAL_PER_TRADE`, `SIM_MAX_OPEN_POSITIONS`, `SIM_MIN_TRADE_ALLOCATION`
- `SIM_TIMEFRAME` (e.g. `4h`), `SIM_RSI_PERIOD`, `SIM_SWING_K`
- `SIM_OPPORTUNITY_MIN_CANDLES`, `SIM_OPPORTUNITY_MAX_CANDLES`
- `SIM_STOP_LOSS_PCT`, `SIM_TAKE_PROFIT_PCT`, `SIM_MAX_ENTRY_WAIT_CANDLES`, `SIM_MAX_HOLD_CANDLES`
- `SIM_DEFAULT_DAYS`, `SIM_SYMBOLS_LIMIT`
- `BINANCE_API_KEY`, `BINANCE_API_SECRET`, `SIM_SANDBOX`

Advanced multi-factor strategy extra variables (now included in `Config`):

- `SIM_FAST_EMA` (default 21) & `SIM_SLOW_EMA` (default 100): trend filters (fast above slow required for longs)
- `SIM_ATR_PERIOD` (default 14): volatility metric period
- `SIM_ATR_STOP_MULT` (default 2.5): ATR multiple (part of adaptive stop distance)
- `SIM_RR` (default 2.0): reward:risk target multiple used to project take-profit hint
- `SIM_MIN_ATR_PCT` (default 0.002): minimum ATR/price ratio filter to avoid ultra-low volatility symbols

These new parameters power `multi_factor_trend_rsi.py`, which combines:
1. Bullish RSI divergence OR oversold RSI reversal
2. Trend confirmation (EMA fast > EMA slow)
3. Volatility sanity check (ATR relative threshold)
4. Adaptive stop (ATR-based) and target derived from reward:risk multiple.

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

To experiment with the advanced strategy you can import and call `ctb.strategies.multi_factor_trend_rsi.run_strategy` similarly to the existing divergence strategy. (The current simulator loop still focuses on divergence fills; integrating multi-factor signal execution end-to-end would require extending the order generation logic to use ATR-based dynamic stops/targets.)

## Running Tests

Basic utility tests are provided and can be executed with:

```bash
python -m unittest
```

## Notes & Assumptions

- Entry orders wait a maximum of three candles for a fill; this was chosen as a sensible default because the requirement only specified "within MAX_ENTRY_WAIT_SPAN" without a value.
- If a candle hits both stop-loss and take-profit levels, the simulator prioritises the stop-loss to model a conservative fill order.
- When sufficient historical data is unavailable for a symbol, it is skipped.
- Advanced strategy signals currently act as an extension point; full execution (dynamic position sizing by volatility, trailing stops) can be added in a subsequent iteration.
