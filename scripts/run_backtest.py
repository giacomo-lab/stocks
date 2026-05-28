import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.config import BacktestConfig
from src.data.fetcher import align_data, fetch_ohlcv
from src.strategies.sma_crossover import SMACrossover
from src.strategies.sma_crossover_tp import SMACrossoverTakeProfit
from src.backtest.engine import BacktestEngine
from src.backtest.metrics import compute_metrics, print_metrics


STRATEGY_MAP = {
    "SMACrossover": SMACrossover,
    "SMACrossoverTakeProfit": SMACrossoverTakeProfit,
}


def main():
    config_path = os.path.join(os.path.dirname(__file__), "..", "config.json")
    config = BacktestConfig.from_json(config_path)

    print(f"Fetching data for {len(config.tickers)} tickers: {config.tickers}")
    print(f"Period: {config.start_date} to {config.end_date} (Interval: {config.interval})\n")

    data = fetch_ohlcv(
        tickers=config.tickers,
        start=config.start_date,
        end=config.end_date,
        interval=config.interval,
    )

    if not data:
        print("No data fetched. Exiting.")
        return

    dates, prices = align_data(data)
    if prices.empty:
        print("No aligned price data. Exiting.")
        return

    print(f"Aligned on {len(dates)} trading periods, {len(prices.columns)} tickers\n")

    # Load strategy dynamically
    strat_name = config.strategy.get("name", "SMACrossover")
    strat_class = STRATEGY_MAP.get(strat_name)
    if not strat_class:
        print(f"[ERROR] Strategy '{strat_name}' not found in STRATEGY_MAP.")
        print(f"Available strategies: {', '.join(STRATEGY_MAP.keys())}")
        return
    
    strat_params = config.strategy.get("params", {})
    strategy = strat_class(**strat_params)
    
    # Print strategy info
    print(f"Strategy: {strat_name}")
    if strategy.description:
        print(f"  {strategy.description}\n")

    engine = BacktestEngine(
        initial_capital=config.initial_capital,
        commission_per_share=config.commission_per_share,
        commission_min=config.commission_min,
        slippage_pct=config.slippage_pct,
    )

    result = engine.run(strategy, prices, data)
    
    # Pass the config to the result so metrics can access the interval
    result.config = {
        "initial_capital": config.initial_capital,
        "interval": config.interval
    }
    
    metrics = compute_metrics(result)
    print_metrics(metrics)

    os.makedirs(config.output_dir, exist_ok=True)
    equity_path = os.path.join(config.output_dir, "equity_curve.csv")
    result.equity_curve.to_csv(equity_path)
    print(f"\nEquity curve saved to {equity_path}")


if __name__ == "__main__":
    main()