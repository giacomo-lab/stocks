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
    stop_loss_pct: float | None,
    profit_target_pct: float | None,
    in_position: set[str],
    entry_price: dict[str, float],
    signals: list[Signal],
) -> bool:
    """Exit on stop-loss or take-profit; return True if position was closed."""
    if _stop_loss_hit(price, entry, stop_loss_pct):
        in_position.discard(ticker)
        entry_price.pop(ticker, None)
        signals.append(Signal(ticker, "SELL", -1, "MARKET", None))
        return True

    if _take_profit_hit(price, entry, profit_target_pct):
        in_position.discard(ticker)
        entry_price.pop(ticker, None)
        signals.append(Signal(ticker, "SELL", -1, "MARKET", None))
        return True

    return False


class MeanReversionZScore(Strategy):
    """Buy when z-score is below entry threshold; sell when it reverts to mean."""

    description = (
        "Regression to the mean (z-score) – buys when price is unusually far "
        "below the rolling mean (oversold) only if the lookback trend is flat "
        "or upward; sells on reversion, optional take-profit, or stop-loss."
    )

    def __init__(
        self,
        lookback_window: int = 50,
        entry_z_score: float = -2.0,
        exit_z_score: float = 0.0,
        max_downward_trend_pct: float = 1.0,
        profit_target_pct: float | None = None,
        stop_loss_pct: float | None = None,
    ):
        super().__init__(
            params={
                "lookback_window": lookback_window,
                "entry_z_score": entry_z_score,
                "exit_z_score": exit_z_score,
                "max_downward_trend_pct": max_downward_trend_pct,
                "profit_target_pct": profit_target_pct,
                "stop_loss_pct": stop_loss_pct,
            }
        )
        self.lookback_window = lookback_window
        self.entry_z_score = entry_z_score
        self.exit_z_score = exit_z_score
        self.max_downward_trend_pct = max_downward_trend_pct
        self.profit_target_pct = profit_target_pct
        self.stop_loss_pct = stop_loss_pct
        self._price_history: dict[str, list[float]] = {}
        self._in_position: set[str] = set()
        self._entry_price: dict[str, float] = {}

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
            if len(prices) < self.lookback_window:
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
                    self.stop_loss_pct,
                    self.profit_target_pct,
                    self._in_position,
                    self._entry_price,
                    signals,
                ):
                    continue

                if z >= self.exit_z_score:
                    self._in_position.discard(ticker)
                    self._entry_price.pop(ticker, None)
                    signals.append(Signal(ticker, "SELL", -1, "MARKET", None))
            elif z < self.entry_z_score:
                trend = _trend_pct(prices, self.lookback_window)
                if not _trend_allows_entry(trend, self.max_downward_trend_pct):
                    continue
                self._in_position.add(ticker)
                self._entry_price[ticker] = price
                signals.append(Signal(ticker, "BUY", -1, "MARKET", None))

        return signals


class MeanReversionPct(Strategy):
    """Buy when price is X% below rolling SMA; sell when price reverts to SMA."""

    description = (
        "Regression to the mean (percent deviation) – buys when price deviates "
        "entry_pct below a rolling SMA only if the lookback trend is flat or "
        "upward; sells on SMA reversion, optional take-profit, or stop-loss."
    )

    def __init__(
        self,
        lookback_window: int = 50,
        entry_pct: float = -2.0,
        max_downward_trend_pct: float = 1.0,
        profit_target_pct: float | None = None,
        stop_loss_pct: float | None = None,
    ):
        super().__init__(
            params={
                "lookback_window": lookback_window,
                "entry_pct": entry_pct,
                "max_downward_trend_pct": max_downward_trend_pct,
                "profit_target_pct": profit_target_pct,
                "stop_loss_pct": stop_loss_pct,
            }
        )
        self.lookback_window = lookback_window
        self.entry_pct = entry_pct
        self.max_downward_trend_pct = max_downward_trend_pct
        self.profit_target_pct = profit_target_pct
        self.stop_loss_pct = stop_loss_pct
        self._price_history: dict[str, list[float]] = {}
        self._in_position: set[str] = set()
        self._entry_price: dict[str, float] = {}

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
            if len(prices) < self.lookback_window:
                continue

            sma = _rolling_mean(prices, self.lookback_window)
            entry_threshold = sma * (1 + self.entry_pct / 100)

            if ticker in self._in_position:
                entry = self._entry_price.get(ticker, price)
                if _exit_if_risk_targets(
                    ticker,
                    price,
                    entry,
                    self.stop_loss_pct,
                    self.profit_target_pct,
                    self._in_position,
                    self._entry_price,
                    signals,
                ):
                    continue

                if price >= sma:
                    self._in_position.discard(ticker)
                    self._entry_price.pop(ticker, None)
                    signals.append(Signal(ticker, "SELL", -1, "MARKET", None))
            elif price <= entry_threshold:
                trend = _trend_pct(prices, self.lookback_window)
                if not _trend_allows_entry(trend, self.max_downward_trend_pct):
                    continue
                self._in_position.add(ticker)
                self._entry_price[ticker] = price
                signals.append(Signal(ticker, "BUY", -1, "MARKET", None))

        return signals


class MeanReversionRSI(Strategy):
    """Buy on oversold RSI; sell when RSI normalizes."""

    description = (
        "Regression to the mean (RSI) – buys when RSI is oversold only if the "
        "rsi_period trend is flat or upward; sells on RSI normalization, "
        "optional take-profit, or stop-loss."
    )

    def __init__(
        self,
        rsi_period: int = 14,
        entry_rsi: float = 30.0,
        exit_rsi: float = 50.0,
        max_downward_trend_pct: float = 1.0,
        profit_target_pct: float | None = None,
        stop_loss_pct: float | None = None,
    ):
        super().__init__(
            params={
                "rsi_period": rsi_period,
                "entry_rsi": entry_rsi,
                "exit_rsi": exit_rsi,
                "max_downward_trend_pct": max_downward_trend_pct,
                "profit_target_pct": profit_target_pct,
                "stop_loss_pct": stop_loss_pct,
            }
        )
        self.rsi_period = rsi_period
        self.entry_rsi = entry_rsi
        self.exit_rsi = exit_rsi
        self.max_downward_trend_pct = max_downward_trend_pct
        self.profit_target_pct = profit_target_pct
        self.stop_loss_pct = stop_loss_pct
        self._price_history: dict[str, list[float]] = {}
        self._in_position: set[str] = set()
        self._entry_price: dict[str, float] = {}

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
            if len(prices) < self.rsi_period + 1:
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
                    self.stop_loss_pct,
                    self.profit_target_pct,
                    self._in_position,
                    self._entry_price,
                    signals,
                ):
                    continue

                if rsi >= self.exit_rsi:
                    self._in_position.discard(ticker)
                    self._entry_price.pop(ticker, None)
                    signals.append(Signal(ticker, "SELL", -1, "MARKET", None))
            elif rsi <= self.entry_rsi:
                trend = _trend_pct(prices, self.rsi_period)
                if not _trend_allows_entry(trend, self.max_downward_trend_pct):
                    continue
                self._in_position.add(ticker)
                self._entry_price[ticker] = price
                signals.append(Signal(ticker, "BUY", -1, "MARKET", None))

        return signals
