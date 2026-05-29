"""Mean-reversion (regression to the mean) strategies — long-only."""

from datetime import datetime

import pandas as pd

from src.strategies.base import Signal, Strategy


def _rolling_mean(prices: list[float], window: int) -> float:
    window_prices = prices[-window:]
    return sum(window_prices) / window


def _z_score(prices: list[float], window: int) -> float | None:
    window_prices = prices[-window:]
    mean = sum(window_prices) / window
    variance = sum((p - mean) ** 2 for p in window_prices) / window
    std = variance**0.5
    if std == 0:
        return None
    return (prices[-1] - mean) / std


def _rsi(prices: list[float], period: int) -> float | None:
    """Wilder-smoothed RSI; needs at least period + 1 prices."""
    if len(prices) < period + 1:
        return None

    changes = [prices[i] - prices[i - 1] for i in range(1, len(prices))]
    gains = [c if c > 0 else 0.0 for c in changes]
    losses = [-c if c < 0 else 0.0 for c in changes]

    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period

    for i in range(period, len(changes)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period

    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))


def _trend_pct(prices: list[float], window: int) -> float:
    """Percent change from start to end of the lookback window."""
    first = prices[-window]
    return (prices[-1] / first - 1) * 100


def _trend_allows_entry(trend_pct: float, max_downward_trend_pct: float) -> bool:
    """Allow entry when trend is flat-ish or upward."""
    return trend_pct >= -max_downward_trend_pct


def _rolling_return_vol_pct(prices: list[float], window: int) -> float | None:
    """Std dev of bar-to-bar % returns over the last `window` returns."""
    if len(prices) < window + 1:
        return None

    start = len(prices) - window
    returns = [
        (prices[i] / prices[i - 1] - 1) * 100 for i in range(start, len(prices))
    ]
    mean = sum(returns) / len(returns)
    variance = sum((r - mean) ** 2 for r in returns) / len(returns)
    std = variance**0.5
    return std if std > 0 else None


def _resolve_vol_scaled_pct(
    fixed_pct: float | None,
    prices: list[float],
    volatility_window: int,
    vol_fraction: float,
) -> float | None:
    """Fixed override, or vol_fraction × rolling return volatility (%)."""
    if fixed_pct is not None:
        return fixed_pct
    vol = _rolling_return_vol_pct(prices, volatility_window)
    if vol is None:
        return None
    scaled = vol_fraction * vol
    return scaled if scaled > 0 else None


def _resolve_profit_target_pct(
    fixed_pct: float | None,
    prices: list[float],
    volatility_window: int,
    profit_vol_fraction: float,
) -> float | None:
    return _resolve_vol_scaled_pct(
        fixed_pct, prices, volatility_window, profit_vol_fraction
    )


def _resolve_stop_loss_pct(
    fixed_pct: float | None,
    prices: list[float],
    volatility_window: int,
    stop_vol_fraction: float,
) -> float | None:
    return _resolve_vol_scaled_pct(
        fixed_pct, prices, volatility_window, stop_vol_fraction
    )


def _set_entry_risk_targets(
    ticker: str,
    prices: list[float],
    volatility_window: int,
    profit_target_pct: float | None,
    profit_vol_fraction: float,
    stop_loss_pct: float | None,
    stop_vol_fraction: float,
    entry_profit_target: dict[str, float | None],
    entry_stop_loss: dict[str, float | None],
) -> None:
    """Lock take-profit and stop-loss at entry (vol-based unless overridden)."""
    entry_profit_target[ticker] = _resolve_profit_target_pct(
        profit_target_pct, prices, volatility_window, profit_vol_fraction
    )
    entry_stop_loss[ticker] = _resolve_stop_loss_pct(
        stop_loss_pct, prices, volatility_window, stop_vol_fraction
    )


def _min_history_bars(
    indicator_window: int,
    trend_window: int,
    *,
    rsi: bool = False,
    volatility_window: int = 0,
) -> int:
    """Bars required before indicator, trend, and volatility are valid."""
    indicator_need = indicator_window + 1 if rsi else indicator_window
    vol_need = volatility_window + 1 if volatility_window else 0
    return max(indicator_need, trend_window, vol_need)


def _clear_position(
    ticker: str,
    in_position: set[str],
    entry_price: dict[str, float],
    entry_profit_target: dict[str, float | None],
    entry_stop_loss: dict[str, float | None],
) -> None:
    in_position.discard(ticker)
    entry_price.pop(ticker, None)
    entry_profit_target.pop(ticker, None)
    entry_stop_loss.pop(ticker, None)


def _stop_loss_hit(
    price: float, entry: float, stop_loss_pct: float | None
) -> bool:
    if stop_loss_pct is None:
        return False
    loss_pct = (price / entry - 1) * 100
    return loss_pct <= -stop_loss_pct


def _take_profit_hit(
    price: float, entry: float, profit_target_pct: float | None
) -> bool:
    if profit_target_pct is None:
        return False
    profit_pct = (price / entry - 1) * 100
    return profit_pct >= profit_target_pct


def _exit_if_risk_targets(
    ticker: str,
    price: float,
    entry: float,
    entry_stop_loss: dict[str, float | None],
    entry_profit_target: dict[str, float | None],
    in_position: set[str],
    entry_price: dict[str, float],
    signals: list[Signal],
) -> bool:
    """Exit on stop-loss or take-profit; return True if position was closed."""
    stop_loss_pct = entry_stop_loss.get(ticker)
    profit_target_pct = entry_profit_target.get(ticker)

    if _stop_loss_hit(price, entry, stop_loss_pct):
        _clear_position(
            ticker, in_position, entry_price, entry_profit_target, entry_stop_loss
        )
        signals.append(Signal(ticker, "SELL", -1, "MARKET", None))
        return True

    if _take_profit_hit(price, entry, profit_target_pct):
        _clear_position(
            ticker, in_position, entry_price, entry_profit_target, entry_stop_loss
        )
        signals.append(Signal(ticker, "SELL", -1, "MARKET", None))
        return True

    return False


class MeanReversionZScore(Strategy):
    """Buy when z-score is below entry threshold; sell when it reverts to mean."""

    description = (
        "Regression to the mean (z-score) – buys when price is unusually far "
        "below the rolling mean (lookback_window) only if trend_window trend "
        "is flat or upward; take-profit and stop-loss default to vol_fraction × "
        "return volatility unless profit_target_pct or stop_loss_pct is set."
    )

    def __init__(
        self,
        lookback_window: int = 50,
        trend_window: int | None = None,
        entry_z_score: float = -2.0,
        exit_z_score: float = 0.0,
        max_downward_trend_pct: float = 1.0,
        volatility_window: int = 20,
        profit_vol_fraction: float = 1.0,
        stop_vol_fraction: float = 1.0,
        profit_target_pct: float | None = None,
        stop_loss_pct: float | None = None,
    ):
        resolved_trend = trend_window if trend_window is not None else lookback_window
        super().__init__(
            params={
                "lookback_window": lookback_window,
                "trend_window": resolved_trend,
                "entry_z_score": entry_z_score,
                "exit_z_score": exit_z_score,
                "max_downward_trend_pct": max_downward_trend_pct,
                "volatility_window": volatility_window,
                "profit_vol_fraction": profit_vol_fraction,
                "stop_vol_fraction": stop_vol_fraction,
                "profit_target_pct": profit_target_pct,
                "stop_loss_pct": stop_loss_pct,
            }
        )
        self.lookback_window = lookback_window
        self.trend_window = resolved_trend
        self.entry_z_score = entry_z_score
        self.exit_z_score = exit_z_score
        self.max_downward_trend_pct = max_downward_trend_pct
        self.volatility_window = volatility_window
        self.profit_vol_fraction = profit_vol_fraction
        self.stop_vol_fraction = stop_vol_fraction
        self.profit_target_pct = profit_target_pct
        self.stop_loss_pct = stop_loss_pct
        self._price_history: dict[str, list[float]] = {}
        self._in_position: set[str] = set()
        self._entry_price: dict[str, float] = {}
        self._entry_profit_target: dict[str, float | None] = {}
        self._entry_stop_loss: dict[str, float | None] = {}

    def on_bar(
        self,
        date: datetime,
        data: dict[str, pd.Series],
        positions: dict,
        cash: float,
        equity: float,
    ) -> list[Signal]:
        signals: list[Signal] = []

        for ticker, series in data.items():
            if pd.isna(series.get("adj_close")):
                continue

            price = float(series["adj_close"])

            if ticker not in self._price_history:
                self._price_history[ticker] = []
            self._price_history[ticker].append(price)

            prices = self._price_history[ticker]
            if len(prices) < _min_history_bars(
                self.lookback_window,
                self.trend_window,
                volatility_window=self.volatility_window,
            ):
                continue

            z = _z_score(prices, self.lookback_window)
            if z is None:
                continue

            if ticker in self._in_position:
                entry = self._entry_price.get(ticker, price)
                if _exit_if_risk_targets(
                    ticker,
                    price,
                    entry,
                    self._entry_stop_loss,
                    self._entry_profit_target,
                    self._in_position,
                    self._entry_price,
                    signals,
                ):
                    continue

                if z >= self.exit_z_score:
                    _clear_position(
                        ticker,
                        self._in_position,
                        self._entry_price,
                        self._entry_profit_target,
                        self._entry_stop_loss,
                    )
                    signals.append(Signal(ticker, "SELL", -1, "MARKET", None))
            elif z < self.entry_z_score:
                trend = _trend_pct(prices, self.trend_window)
                if not _trend_allows_entry(trend, self.max_downward_trend_pct):
                    continue
                self._in_position.add(ticker)
                self._entry_price[ticker] = price
                _set_entry_risk_targets(
                    ticker,
                    prices,
                    self.volatility_window,
                    self.profit_target_pct,
                    self.profit_vol_fraction,
                    self.stop_loss_pct,
                    self.stop_vol_fraction,
                    self._entry_profit_target,
                    self._entry_stop_loss,
                )
                signals.append(Signal(ticker, "BUY", -1, "MARKET", None))

        return signals


class MeanReversionPct(Strategy):
    """Buy when price is X% below rolling SMA; sell when price reverts to SMA."""

    description = (
        "Regression to the mean (percent deviation) – buys when price deviates "
        "entry_pct below a rolling SMA (lookback_window) only if trend_window "
        "trend is flat or upward; take-profit and stop-loss default to vol_fraction × "
        "return volatility unless profit_target_pct or stop_loss_pct is set."
    )

    def __init__(
        self,
        lookback_window: int = 50,
        trend_window: int | None = None,
        entry_pct: float = -2.0,
        max_downward_trend_pct: float = 1.0,
        volatility_window: int = 20,
        profit_vol_fraction: float = 1.0,
        stop_vol_fraction: float = 1.0,
        profit_target_pct: float | None = None,
        stop_loss_pct: float | None = None,
    ):
        resolved_trend = trend_window if trend_window is not None else lookback_window
        super().__init__(
            params={
                "lookback_window": lookback_window,
                "trend_window": resolved_trend,
                "entry_pct": entry_pct,
                "max_downward_trend_pct": max_downward_trend_pct,
                "volatility_window": volatility_window,
                "profit_vol_fraction": profit_vol_fraction,
                "stop_vol_fraction": stop_vol_fraction,
                "profit_target_pct": profit_target_pct,
                "stop_loss_pct": stop_loss_pct,
            }
        )
        self.lookback_window = lookback_window
        self.trend_window = resolved_trend
        self.entry_pct = entry_pct
        self.max_downward_trend_pct = max_downward_trend_pct
        self.volatility_window = volatility_window
        self.profit_vol_fraction = profit_vol_fraction
        self.stop_vol_fraction = stop_vol_fraction
        self.profit_target_pct = profit_target_pct
        self.stop_loss_pct = stop_loss_pct
        self._price_history: dict[str, list[float]] = {}
        self._in_position: set[str] = set()
        self._entry_price: dict[str, float] = {}
        self._entry_profit_target: dict[str, float | None] = {}
        self._entry_stop_loss: dict[str, float | None] = {}

    def on_bar(
        self,
        date: datetime,
        data: dict[str, pd.Series],
        positions: dict,
        cash: float,
        equity: float,
    ) -> list[Signal]:
        signals: list[Signal] = []

        for ticker, series in data.items():
            if pd.isna(series.get("adj_close")):
                continue

            price = float(series["adj_close"])

            if ticker not in self._price_history:
                self._price_history[ticker] = []
            self._price_history[ticker].append(price)

            prices = self._price_history[ticker]
            if len(prices) < _min_history_bars(
                self.lookback_window,
                self.trend_window,
                volatility_window=self.volatility_window,
            ):
                continue

            sma = _rolling_mean(prices, self.lookback_window)
            entry_threshold = sma * (1 + self.entry_pct / 100)

            if ticker in self._in_position:
                entry = self._entry_price.get(ticker, price)
                if _exit_if_risk_targets(
                    ticker,
                    price,
                    entry,
                    self._entry_stop_loss,
                    self._entry_profit_target,
                    self._in_position,
                    self._entry_price,
                    signals,
                ):
                    continue

                if price >= sma:
                    _clear_position(
                        ticker,
                        self._in_position,
                        self._entry_price,
                        self._entry_profit_target,
                        self._entry_stop_loss,
                    )
                    signals.append(Signal(ticker, "SELL", -1, "MARKET", None))
            elif price <= entry_threshold:
                trend = _trend_pct(prices, self.trend_window)
                if not _trend_allows_entry(trend, self.max_downward_trend_pct):
                    continue
                self._in_position.add(ticker)
                self._entry_price[ticker] = price
                _set_entry_risk_targets(
                    ticker,
                    prices,
                    self.volatility_window,
                    self.profit_target_pct,
                    self.profit_vol_fraction,
                    self.stop_loss_pct,
                    self.stop_vol_fraction,
                    self._entry_profit_target,
                    self._entry_stop_loss,
                )
                signals.append(Signal(ticker, "BUY", -1, "MARKET", None))

        return signals


class MeanReversionRSI(Strategy):
    """Buy on oversold RSI; sell when RSI normalizes."""

    description = (
        "Regression to the mean (RSI) – buys when RSI (rsi_period) is oversold "
        "only if trend_window trend is flat or upward; take-profit and stop-loss "
        "default to vol_fraction × return volatility unless overridden."
    )

    def __init__(
        self,
        rsi_period: int = 14,
        trend_window: int | None = None,
        entry_rsi: float = 30.0,
        exit_rsi: float = 50.0,
        max_downward_trend_pct: float = 1.0,
        volatility_window: int = 20,
        profit_vol_fraction: float = 1.0,
        stop_vol_fraction: float = 1.0,
        profit_target_pct: float | None = None,
        stop_loss_pct: float | None = None,
    ):
        resolved_trend = trend_window if trend_window is not None else rsi_period
        super().__init__(
            params={
                "rsi_period": rsi_period,
                "trend_window": resolved_trend,
                "entry_rsi": entry_rsi,
                "exit_rsi": exit_rsi,
                "max_downward_trend_pct": max_downward_trend_pct,
                "volatility_window": volatility_window,
                "profit_vol_fraction": profit_vol_fraction,
                "stop_vol_fraction": stop_vol_fraction,
                "profit_target_pct": profit_target_pct,
                "stop_loss_pct": stop_loss_pct,
            }
        )
        self.rsi_period = rsi_period
        self.trend_window = resolved_trend
        self.entry_rsi = entry_rsi
        self.exit_rsi = exit_rsi
        self.max_downward_trend_pct = max_downward_trend_pct
        self.volatility_window = volatility_window
        self.profit_vol_fraction = profit_vol_fraction
        self.stop_vol_fraction = stop_vol_fraction
        self.profit_target_pct = profit_target_pct
        self.stop_loss_pct = stop_loss_pct
        self._price_history: dict[str, list[float]] = {}
        self._in_position: set[str] = set()
        self._entry_price: dict[str, float] = {}
        self._entry_profit_target: dict[str, float | None] = {}
        self._entry_stop_loss: dict[str, float | None] = {}

    def on_bar(
        self,
        date: datetime,
        data: dict[str, pd.Series],
        positions: dict,
        cash: float,
        equity: float,
    ) -> list[Signal]:
        signals: list[Signal] = []

        for ticker, series in data.items():
            if pd.isna(series.get("adj_close")):
                continue

            price = float(series["adj_close"])

            if ticker not in self._price_history:
                self._price_history[ticker] = []
            self._price_history[ticker].append(price)

            prices = self._price_history[ticker]
            if len(prices) < _min_history_bars(
                self.rsi_period,
                self.trend_window,
                rsi=True,
                volatility_window=self.volatility_window,
            ):
                continue

            rsi = _rsi(prices, self.rsi_period)
            if rsi is None:
                continue

            if ticker in self._in_position:
                entry = self._entry_price.get(ticker, price)
                if _exit_if_risk_targets(
                    ticker,
                    price,
                    entry,
                    self._entry_stop_loss,
                    self._entry_profit_target,
                    self._in_position,
                    self._entry_price,
                    signals,
                ):
                    continue

                if rsi >= self.exit_rsi:
                    _clear_position(
                        ticker,
                        self._in_position,
                        self._entry_price,
                        self._entry_profit_target,
                        self._entry_stop_loss,
                    )
                    signals.append(Signal(ticker, "SELL", -1, "MARKET", None))
            elif rsi <= self.entry_rsi:
                trend = _trend_pct(prices, self.trend_window)
                if not _trend_allows_entry(trend, self.max_downward_trend_pct):
                    continue
                self._in_position.add(ticker)
                self._entry_price[ticker] = price
                _set_entry_risk_targets(
                    ticker,
                    prices,
                    self.volatility_window,
                    self.profit_target_pct,
                    self.profit_vol_fraction,
                    self.stop_loss_pct,
                    self.stop_vol_fraction,
                    self._entry_profit_target,
                    self._entry_stop_loss,
                )
                signals.append(Signal(ticker, "BUY", -1, "MARKET", None))

        return signals
