## Explaining RSI-Divergence Strategy

We want to write the code to simulate trading crypto usdc pairs in binance using the rsi_divergence strategy.

The trading should happen as follows:

- We have a 1000 dollars capital.
- We assume we are at the time of 365 days before.
- We trade on the 4H chart.
- We should allocate at most 25% of our capital to each trade. And hence we can hold at most 4 assets at time.
- We watch the market (All usdc symbols) and look for all symbols with (bullish) rsi divergence that are still valid. i.e. they happened just recently meaning if we are at time t (which is the start time of new candle), the second price minimum is happened at the candle with start time t-8H or before that until t-40H (i.e.TRADE_OPPORTUNITY_WINDOW_SPAN times 4H). Also we should not have passed our stop-loss (SL) which is 5% below P2. We should also not have passed our take-profit (TP) which is 10% above P2.
- Then we enter the trade as follows:
  We place a limit order at half distance between the low of the second local minimum and its close. Then if not filled within MAX_ENTRY_WAIT_SPAN we cancel it. Otherwise (it filled) we place a limit order at 10% above entry for taking profit. No asset should be hold more than MAX_HOLD_CANDLES=30. (market sell the asset if we reached 30 4H candle holds). Also if we hit the SL instead of going up when holding asset, we cancel take-profit order and market sell the asset.

## Explaining Simulator Implementation

The simulator should instead of making real trades on the exchange, simulate the orders by looking at price action history. The simulator should assume we are at time now - 365 days. then fetch the previous (4H) klines of every symbol. Then assuming we are at time t (which is the start time for the first 4H candle), we scan all symbols to see if there are valid divergences (as explained in INSTRUCTIONS.md file). Then if there are any, put buy orders for at most 4 of them. then move one candle to future. If there are orders needed to be done based on our strategy instructed, we place them and if we have capital we scan the symbols again. we move forward one candle at a time until we reach today. we should print orders that happen at each candle and when a symbol is bought and sold we should print its profit. At the end also we should print the overall profit.
