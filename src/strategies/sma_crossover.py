from datetime import datetime

import pandas as pd

from src.strategies.base import Signal, Strategy


class SMACrossover(Strategy):
    """Buy when short SMA crosses above long SMA, sell when it crosses below."""
    
    description = (
        "SMA Crossover – uses two simple moving averages (short & long). "
        "A buy signal triggers when the short SMA crosses above the long SMA "
        "(golden cross), and a sell signal triggers when it crosses below "
        "(death cross)."
    )

    def __init__(self, short_window: int = 50, long_window: int = 200):
        super().__init__(params={"short_window": short_window, "long_window": long_window})
        self.short_window = short_window
        self.long_window = long_window
        self._price_history: dict[str, list[float]] = {}
        self._in_position: set[str] = set()

    def on_bar(
        self,
        date: datetime,
        data: dict[str, pd.Series],
        positions: dict,
        cash: float,
        equity: float,
    ) -> list[Signal]:
        signals = []

        for ticker, series in data.items():
            if pd.isna(series.get("adj_close")):
                continue

            price = float(series["adj_close"])

            if ticker not in self._price_history:
                self._price_history[ticker] = []
            self._price_history[ticker].append(price)

            prices = self._price_history[ticker]
            if len(prices) < self.long_window:
                continue

            short_sma = sum(prices[-self.short_window:]) / self.short_window
            long_sma = sum(prices[-self.long_window:]) / self.long_window

            prev_prices = prices[: -1]
            prev_short = sum(prev_prices[-self.short_window:]) / self.short_window
            prev_long = sum(prev_prices[-self.long_window:]) / self.long_window

            if ticker in self._in_position:
                if short_sma < long_sma and prev_short >= prev_long:
                    self._in_position.discard(ticker)
                    signals.append(Signal(ticker, "SELL", -1, "MARKET", None))
            else:
                if short_sma > long_sma and prev_short <= prev_long:
                    self._in_position.add(ticker)
                    signals.append(Signal(ticker, "BUY", -1, "MARKET", None))

        return signals