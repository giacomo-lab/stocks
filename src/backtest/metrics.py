import numpy as np
import pandas as pd

from src.backtest.engine import BacktestResult


def compute_metrics(result: BacktestResult) -> dict:
    equity = result.equity_curve
    trades = result.trades
    initial_cap = result.config.get("initial_capital", 100_000)
    final_cap = result.config.get("final_capital", equity.iloc[-1] if len(equity) > 0 else initial_cap)

    metrics = {}
    
    # Store the interval for printing
    metrics["interval"] = result.config.get("interval", "1d")

    metrics["total_return_pct"] = ((final_cap / initial_cap) - 1) * 100

    returns = equity.pct_change().dropna() if len(equity) > 1 else pd.Series(dtype=float)
    years = (equity.index[-1] - equity.index[0]).days / 365.25 if len(equity) > 1 else 0
    if years > 0 and len(returns) > 0:
        cagr = (final_cap / initial_cap) ** (1 / years) - 1
    else:
        cagr = 0
    metrics["cagr_pct"] = cagr * 100

    if len(returns) > 1:
        sharpe = (returns.mean() / returns.std()) * np.sqrt(252) if returns.std() > 0 else 0
    else:
        sharpe = 0
    metrics["sharpe_ratio"] = sharpe

    metrics["max_drawdown_pct"] = _max_drawdown(equity)
    metrics["max_drawdown_periods"] = _max_drawdown_periods(equity)

    win_trades = [t for t in trades if t.pnl > 0]
    loss_trades = [t for t in trades if t.pnl <= 0]

    metrics["total_trades"] = len(trades)
    metrics["win_count"] = len(win_trades)
    metrics["loss_count"] = len(loss_trades)
    metrics["win_rate_pct"] = (len(win_trades) / len(trades) * 100) if trades else 0

    total_wins = sum(t.pnl for t in win_trades) if win_trades else 0
    total_losses = abs(sum(t.pnl for t in loss_trades)) if loss_trades else 0
    metrics["profit_factor"] = total_wins / total_losses if total_losses > 0 else float("inf")

    if trades:
        avg_win = np.mean([t.pnl for t in win_trades]) if win_trades else 0
        avg_loss = abs(np.mean([t.pnl for t in loss_trades])) if loss_trades else 0
        metrics["avg_win"] = avg_win
        metrics["avg_loss"] = avg_loss
        metrics["largest_win"] = max(t.pnl for t in trades)
        metrics["largest_loss"] = min(t.pnl for t in trades)

    metrics["monthly_returns"] = _monthly_returns(equity, initial_cap)
    metrics["yearly_returns"] = _yearly_returns(equity, initial_cap)

    return metrics


def print_metrics(metrics: dict):
    interval = metrics.get("interval", "1d")
    print("=" * 56)
    print(f"{'PERFORMANCE METRICS':^56}")
    print("=" * 56)
    print(f"  Total Return:          {metrics.get('total_return_pct', 0):>10.2f}%")
    print(f"  CAGR:                  {metrics.get('cagr_pct', 0):>10.2f}%")
    print(f"  Sharpe Ratio:          {metrics.get('sharpe_ratio', 0):>10.2f}")
    print(f"  Max Drawdown:          {metrics.get('max_drawdown_pct', 0):>10.2f}%")
    print(f"  Max DD Duration:       {metrics.get('max_drawdown_periods', 0):>10.0f} periods ({interval})")
    print("-" * 56)
    print(f"  Total Trades:          {metrics.get('total_trades', 0):>10}")
    print(f"  Wins / Losses:         {metrics.get('win_count', 0):>6} / {metrics.get('loss_count', 0):>6}")
    print(f"  Win Rate:              {metrics.get('win_rate_pct', 0):>10.2f}%")
    print(f"  Profit Factor:         {metrics.get('profit_factor', 0):>10.2f}")
    print(f"  Avg Win / Avg Loss:    {metrics.get('avg_win', 0):>8.2f} / {metrics.get('avg_loss', 0):>8.2f}")
    print(f"  Largest Win / Loss:    {metrics.get('largest_win', 0):>8.2f} / {metrics.get('largest_loss', 0):>8.2f}")
    print("=" * 56)

    monthly = metrics.get("monthly_returns")
    if monthly is not None and not monthly.empty:
        print("\nMonthly Returns (%):")
        print(monthly.to_string(float_format=lambda x: f"{x:.2f}"))

    yearly = metrics.get("yearly_returns")
    if yearly is not None and len(yearly) > 0:
        print("\nYearly Returns (%):")
        for yr, ret in yearly.items():
            print(f"  {yr}: {ret:>8.2f}%")


def _max_drawdown(equity: pd.Series) -> float:
    if len(equity) == 0:
        return 0.0
    rolling_max = equity.cummax()
    drawdown = (equity - rolling_max) / rolling_max
    return float(drawdown.min() * 100)

def _max_drawdown_periods(equity: pd.Series) -> int:
    if len(equity) == 0:
        return 0
    rolling_max = equity.cummax()
    drawdown = equity < rolling_max
    max_periods = 0
    current_periods = 0
    for is_dd in drawdown:
        if is_dd:
            current_periods += 1
            max_periods = max(max_periods, current_periods)
        else:
            current_periods = 0
    return max_periods


def _monthly_returns(equity: pd.Series, initial_cap: float) -> pd.DataFrame:
    if len(equity) < 2:
        return pd.DataFrame()

    monthly = equity.resample("ME").last()
    monthly_ret = monthly.pct_change().dropna() * 100

    years = sorted(set(d.year for d in monthly_ret.index))
    months = range(1, 13)
    table = pd.DataFrame(index=years, columns=[f"{m:02d}" for m in months])

    for date, ret in monthly_ret.items():
        table.loc[date.year, f"{date.month:02d}"] = float(ret)

    return table


def _yearly_returns(equity: pd.Series, initial_cap: float) -> dict[int, float]:
    if len(equity) < 2:
        return {}
    yearly = equity.resample("YE").last()
    yearly_ret = yearly.pct_change().dropna() * 100
    return {int(d.year): float(r) for d, r in yearly_ret.items()}