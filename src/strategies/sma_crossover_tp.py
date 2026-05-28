from datetime import datetime

import pandas as pd

from src.strategies.base import Signal, Strategy


class SMACrossoverTakeProfit(Strategy):
    """SMA crossover with a take-profit threshold.

    Entry is the same golden-cross logic as SMACrossover, but the position
    is closed early when the unrealised profit reaches *profit_target_pct*
    (e.g. 1.0 for 1 %).  The death cross still acts as a stop-loss exit.
    """

    description = (
        "SMA Crossover + Take Profit – enters on a golden cross (short SMA "
        "crosses above long SMA) and exits either when the position reaches "
        "the profit target or when a death cross occurs."
    )

    def __init__(
        self,
        short_window: int = 50,
        long_window: int = 200,
        profit_target_pct: float = 1.0,
    ):
        super().__init__(
            params={
                "short_window": short_window,
                "long_window": long_window,
                "profit_target_pct": profit_target_pct,
            }
        )
        self.short_window = short_window
        self.long_window = long_window
        self.profit_target_pct = profit_target_pct
        self._price_history: dict[str, list[float]] = {}
        self._entry_price: dict[str, float] = {}
        self._in_position: set[str] = set()

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

            # --- maintain price history ---
            if ticker not in self._price_history:
                self._price_history[ticker] = []
            self._price_history[ticker].append(price)

            prices = self._price_history[ticker]
            if len(prices) < self.long_window:
                continue

            # --- compute SMAs ---
            short_sma = sum(prices[-self.short_window:]) / self.short_window
            long_sma = sum(prices[-self.long_window:]) / self.long_window

            prev_prices = prices[:-1]
            prev_short = sum(prev_prices[-self.short_window:]) / self.short_window
            prev_long = sum(prev_prices[-self.long_window:]) / self.long_window

            # --- exit logic ---
            if ticker in self._in_position:
                entry = self._entry_price.get(ticker, price)
                profit_pct = (price / entry - 1) * 100

                # Take-profit exit
                if profit_pct >= self.profit_target_pct:
                    self._in_position.discard(ticker)
                    self._entry_price.pop(ticker, None)
                    signals.append(Signal(ticker, "SELL", -1, "MARKET", None))
                    continue

                # Death-cross exit (stop-loss)
                if short_sma < long_sma and prev_short >= prev_long:
                    self._in_position.discard(ticker)
                    self._entry_price.pop(ticker, None)
                    signals.append(Signal(ticker, "SELL", -1, "MARKET", None))

            # --- entry logic ---
            else:
                if short_sma > long_sma and prev_short <= prev_long:
                    self._in_position.add(ticker)
                    self._entry_price[ticker] = price
                    signals.append(Signal(ticker, "BUY", -1, "MARKET", None))

        return signals
