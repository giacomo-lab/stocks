# Stocks

Track stock prices, evaluate fundamentals, and backtest trading strategies.

## Usage

```bash
# Install dependencies
pip install -r requirements.txt

# Run SMA crossover backtest on default tickers
python scripts/run_backtest.py
```

### Configuration

Edit `src/config.py` to set tickers, date range, initial capital, commission, and slippage.

### Adding a Strategy

Create a subclass of `Strategy` in `src/strategies/`:

```python
from src.strategies.base import Signal, Strategy

class MyStrategy(Strategy):
    def on_bar(self, date, data, positions, cash, equity):
        price = data["AAPL"]["adj_close"]
        if price > 150 and "AAPL" not in positions:
            return [Signal("AAPL", "BUY", -1, "MARKET", None)]
        return []
```

Swap it in `scripts/run_backtest.py`:

```python
strategy = MyStrategy()
```

## Project Structure

```
src/
  config.py            # Backtest settings
  data/fetcher.py      # yfinance data fetching + alignment
  strategies/          # Pluggable strategies (extend base.py)
  backtest/engine.py   # Event-driven backtest loop
  backtest/metrics.py  # Win rate, drawdown, monthly returns
  broker/ibkr.py       # IBKR Web API client (for live trading)
scripts/
  run_backtest.py      # Entry point
  run_live.py          # Future: live trading
```
