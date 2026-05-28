# IBKR Backtest Setup Plan

## Objective
Create a modular Python project to backtest trading strategies using yfinance data, with a clear path to live trading via the IBKR Web API.

## Architecture

```
stocks/
├── src/
│   ├── __init__.py
│   ├── config.py                  # Tickers, date range, Ticker list, date range, initial capital, commission, slippage
│   ├── data/
│   │   ├── __init__.py
│   │   └── fetcher.py             # yfinance OHLCV data fetching -> dict[str, DataFrame] via yfinance
│   ├── strategies/
│   │   ├── __init__.py
│   │   ├── base.py                # Abstract Strategy base class on_bar(data, positions) -> signal
│   │   └── sma_crossover.py       # Example: SMA crossover strategy
│   ├── backtest/
│   │   ├── __init__.py
│   │   ├── engine.py              # Event-driven backtest loop
│   │   └── metrics.py             # Performance metrics (win rate, DD, etc.)
│   └── broker/
│       ├── __init__.py
│       ├── base.py                # Abstract Broker interface
│       └── ibkr.py                # IBKR Web API client (for live later)
├── scripts/
│   ├── run_backtest.py            # Entry point for backtesting. Wires everything together and prints/saves results
│   └── run_live.py                # Entry point for live trading (future)
└── requirements.txt
```

## Component Design

### 1. `config.py`
- Ticker list, date range, initial capital
- Commission model (fixed per share or percentage)
- Slippage model (fixed or percentage)
- IBKR credentials (for live mode)

### 2. `data/fetcher.py`
- `fetch_ohlcv(tickers, start, end) -> dict[str, pd.DataFrame]`
- Wraps `yfinance.download()`
- Returns clean OHLCV DataFrames with no lookahead bias
- Optional caching to disk

### 3. `strategies/base.py`
```python
class Strategy(ABC):
    def __init__(self, params: dict):
        self.params = params
    
    @abstractmethod
    def on_bar(self, date: datetime, data: dict[str, pd.Series], 
               positions: dict) -> list[Signal]:
        ...
```

- `Signal` = namedtuple with (ticker, action: BUY/SELL/EXIT, quantity, order_type, limit_price)
- Subclass for each strategy (SMA crossover, RSI, etc.)

### 4. `backtest/engine.py` (Event-Driven)
- Iterates bars chronologically
- For each bar: call strategy.on_bar() → process signals → execute orders → update portfolio
- Tracks: cash, positions, equity curve, trade log
- Handles: market orders, limit orders, stop-losses, partial fills (stubbed)
- Commission & slippage applied per fill

### 5. `backtest/metrics.py`
- Win Rate, Profit Factor, Max Drawdown
- Monthly/Yearly Returns table
- Sharpe Ratio, CAGR (bonus)
- Summary print + optional CSV/plot output

### 6. `broker/ibkr.py` (Future)
- Authentication via IBKR Web API (OAuth / session-based)
- `/iserver/marketdata/snapshot` for live market data
- `/iserver/account/{id}/orders` for order placement
- Portfolio/positions queries
- Implement the same `Broker` interface as backtest engine for swap-in

## Execution Flow

```
run_backtest.py
  └─ config.py
  └─ data/fetcher.py (yfinance → OHLCV)
  └─ strategies/sma_crossover.py (instantiate with params)
  └─ backtest/engine.py (run event loop)
  └─ backtest/metrics.py (print results)
```

## Implementation Order

1. `requirements.txt` + directory structure
2. `src/config.py`
3. `src/data/fetcher.py`
4. `src/strategies/base.py`
5. `src/strategies/sma_crossover.py`
6. `src/backtest/engine.py`
7. `src/backtest/metrics.py`
8. `scripts/run_backtest.py` → verify
9. `src/broker/base.py`
10. `src/broker/ibkr.py`
11. `scripts/run_live.py` (future)
