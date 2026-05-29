# Stocks

Track stock prices, evaluate fundamentals, and backtest trading strategies.

## Usage

```bash
# Install dependencies
uv sync

# Run SMA crossover backtest on default tickers
uv run python scripts/run_backtest.py
```

### Configuration

All backtest settings live in [`config.json`](config.json) at the project root. Copy [`config.example.json`](config.example.json) if you need a fresh template.

| Key | Description |
|-----|-------------|
| `tickers` | Symbols to fetch and trade |
| `start_date`, `end_date` | Date range (`YYYY-MM-DD`) |
| `interval` | Bar size: `1d`, `5m`, `15m`, `30m`, etc. |
| `data_provider` | `yfinance`, `alphavantage`, `stockdata`, `alpaca`, or `local` |
| `data_dir` | Folder for local CSV/TXT files (default `data`; used when `data_provider` is `local`) |
| `initial_capital`, `commission_*`, `slippage_pct` | Backtest economics |
| `output_dir` | Where equity curve CSV is written |
| `strategy` | `name` + `params` for the strategy class |

**Data providers** (`data_provider` in `config.json`):

| Value | Intervals | Env var | Notes |
|-------|-----------|---------|-------|
| `yfinance` | `1d`, `5m`, `15m`, `30m`, etc. | — | No API key required |
| `alphavantage` | `1d` only (free tier) | `ALPHA_VANTAGE_API_KEY` | ~100 daily bars per ticker, ~5 req/min |
| `stockdata` | `1d`, `5m`, `15m`, `30m`, `1h` | `STOCKS_DATA_API_KEY` | US stocks (IEX); minute data chunked in 7-day windows |
| `alpaca` | `1d`, `5m`, `15m`, `30m`, `1h` | `APCA_API_KEY_ID`, `APCA_API_SECRET_KEY` | Native bar timeframes; free tier uses IEX feed |
| `local` | `1m`, `5m`, `15m`, `30m`, `1h`, `1d` | — | Reads `data/` CSV/TXT; resamples from 1-minute files |

Copy `.env.example` to `.env` and add API keys as needed.

**Local files example** (FirstRateData-style files in `data/`):

```json
"data_provider": "local",
"data_dir": "data",
"interval": "5m",
"start_date": "2023-01-01",
"end_date": "2023-09-29",
"tickers": ["AAPL", "MSFT"]
```

Filename conventions: `{TICKER}_1min_firstratedata.csv` or `{TICKER}_full_1min.txt`. Available symbols include AAPL, MSFT, META, AMZN, TSLA, SPY, QQQ, DIA, EEM, VXX, SPX, DJI, NDX, RUT, VIX. Local files currently cover roughly 2022-09 through 2023-09.

StockData.org returns 1-minute bars and resamples to `5m`/`15m`/`30m`; long intraday ranges use multiple API calls (cached in `.cache/`).

### Strategies

Set `strategy.name` and `strategy.params` in `config.json`. Available strategies (registered in `scripts/run_backtest.py`):

| Name | Description | Key params |
|------|-------------|------------|
| `SMACrossover` | Golden/death cross on two SMAs | `short_window`, `long_window` |
| `SMACrossoverTakeProfit` | SMA crossover + profit target exit | `short_window`, `long_window`, `profit_target_pct` |
| `MeanReversionZScore` | Oversold z-score + flat/up trend; sell on reversion / TP / SL | `lookback_window`, `trend_window`, `volatility_window`, `profit_vol_fraction`, `stop_vol_fraction`, `profit_target_pct` / `stop_loss_pct` (optional overrides) |
| `MeanReversionPct` | Price % below SMA + flat/up trend; sell on SMA / TP / SL | `lookback_window`, `trend_window`, `entry_pct`, `volatility_window`, `profit_vol_fraction`, `stop_vol_fraction`, optional fixed TP/SL |
| `MeanReversionRSI` | Oversold RSI + flat/up trend; sell on RSI / TP / SL | `rsi_period`, `trend_window`, `volatility_window`, `profit_vol_fraction`, `stop_vol_fraction`, optional fixed TP/SL |

**Mean reversion (z-score)** — good default for intraday bars:

```json
"strategy": {
  "name": "MeanReversionZScore",
  "params": {
    "lookback_window": 50,
    "trend_window": 100,
    "entry_z_score": -2.0,
    "exit_z_score": 0.0,
    "max_downward_trend_pct": 1.0,
    "volatility_window": 20,
    "profit_vol_fraction": 1.5,
    "stop_vol_fraction": 1.0
  }
}
```

`lookback_window` drives the z-score indicator; `trend_window` drives the trend filter (defaults to `lookback_window` if omitted). Take-profit and stop-loss default to `profit_vol_fraction ×` and `stop_vol_fraction ×` rolling return volatility over `volatility_window` (locked at entry). Set `profit_target_pct` or `stop_loss_pct` to override with fixed percents.

**Mean reversion (percent deviation):**

```json
"strategy": {
  "name": "MeanReversionPct",
  "params": {
    "lookback_window": 50,
    "trend_window": 100,
    "entry_pct": -2.0,
    "max_downward_trend_pct": 1.0,
    "volatility_window": 20,
    "profit_vol_fraction": 1.5,
    "stop_vol_fraction": 1.0
  }
}
```

**Mean reversion (RSI):**

```json
"strategy": {
  "name": "MeanReversionRSI",
  "params": {
    "rsi_period": 14,
    "trend_window": 50,
    "entry_rsi": 30,
    "exit_rsi": 50,
    "max_downward_trend_pct": 1.0,
    "volatility_window": 20,
    "profit_vol_fraction": 1.5,
    "stop_vol_fraction": 1.0
  }
}
```

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

Register it in `STRATEGY_MAP` in `scripts/run_backtest.py`, then set `strategy.name` in `config.json`.

## Project Structure

```
src/
  config.py            # Loads config.json (schema + validation)
  data/fetcher.py      # OHLCV fetching (APIs + local files) + alignment
  data/alphavantage.py # Alpha Vantage API client (daily, free tier)
  data/stockdata.py    # StockData.org API client (intraday + EOD)
  data/alpaca.py       # Alpaca Market Data API (intraday + daily bars)
  data/local_files.py  # Local CSV/TXT 1-minute data (data/ directory)
  strategies/          # Pluggable strategies (extend base.py)
  backtest/engine.py   # Event-driven backtest loop
  backtest/metrics.py  # Win rate, drawdown, monthly returns
  broker/ibkr.py       # IBKR Web API client (for live trading)
scripts/
  run_backtest.py      # Entry point
  run_live.py          # Future: live trading
```


### References
source of the local intraday data: https://firstratedata.com/free-intraday-data 