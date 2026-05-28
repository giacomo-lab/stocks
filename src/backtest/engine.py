from collections import defaultdict
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime

import numpy as np
import pandas as pd

from src.strategies.base import Signal, Strategy


@dataclass
class TradeRecord:
    ticker: str
    entry_date: datetime
    exit_date: datetime | None = None
    entry_price: float = 0.0
    exit_price: float = 0.0
    shares: int = 0
    pnl: float = 0.0
    pnl_pct: float = 0.0
    side: str = ""


@dataclass
class BacktestResult:
    equity_curve: pd.Series
    trades: list[TradeRecord]
    config: dict = field(default_factory=dict)


class BacktestEngine:
    def __init__(
        self,
        initial_capital: float = 100_000.0,
        commission_per_share: float = 0.005,
        commission_min: float = 1.0,
        slippage_pct: float = 0.001,
    ):
        self.initial_capital = initial_capital
        self.cash = initial_capital
        self.commission_per_share = commission_per_share
        self.commission_min = commission_min
        self.slippage_pct = slippage_pct

        self.positions: dict[str, int] = defaultdict(int)
        self.equity_log: list[float] = []
        self.dates: list[datetime] = []
        self.trades: list[TradeRecord] = []
        self._open_trades: dict[str, TradeRecord] = {}

    def run(
        self, strategy: Strategy, prices: pd.DataFrame, data: dict[str, pd.DataFrame]
    ) -> BacktestResult:
        self._reset()

        dates = prices.index
        tickers = list(prices.columns)

        pending_signals: list[Signal] = []

        for i in range(len(dates)):
            date = dates[i]

            bar_data: dict[str, pd.Series] = {}
            for ticker in tickers:
                if ticker in data and date in data[ticker].index:
                    bar_data[ticker] = data[ticker].loc[date]

            if pending_signals:
                signals_to_process = pending_signals
                pending_signals = []
            else:
                signals_to_process = []

            new_signals = strategy.on_bar(
                date=date, data=bar_data, positions=dict(self.positions),
                cash=self.cash, equity=self._equity(prices, i),
            )

            signals_to_process.extend(new_signals)

            for signal in signals_to_process:
                self._process_signal(signal, date, prices, i, tickers)

            self.dates.append(date)
            self.equity_log.append(self._equity(prices, i))

        for trade in list(self._open_trades.values()):
            trade.exit_date = self.dates[-1]
            trade.exit_price = prices[trade.ticker].iloc[-1]
            trade.pnl = (trade.exit_price - trade.entry_price) * trade.shares
            trade.pnl_pct = (trade.exit_price / trade.entry_price - 1) * 100

            self.cash += trade.shares * trade.exit_price
            comm = self._commission(trade.shares)
            self.cash -= comm * 2
            trade.pnl -= comm * 2

            self.trades.append(trade)

        equity_curve = pd.Series(self.equity_log, index=self.dates, name="equity")

        return BacktestResult(
            equity_curve=equity_curve,
            trades=self.trades,
            config={
                "initial_capital": self.initial_capital,
                "final_capital": self.cash,
            },
        )

    def _reset(self):
        self.cash = self.initial_capital
        self.positions = defaultdict(int)
        self.equity_log = []
        self.dates = []
        self.trades = []
        self._open_trades = {}

    def _equity(self, prices: pd.DataFrame, idx: int) -> float:
        position_value = 0.0
        for ticker, shares in self.positions.items():
            if ticker in prices.columns:
                bar_price = prices[ticker].iloc[idx]
                if not pd.isna(bar_price):
                    position_value += shares * bar_price
        return self.cash + position_value

    def _process_signal(
        self, signal: Signal, date: datetime, prices: pd.DataFrame,
        idx: int, tickers: list[str],
    ):
        ticker = signal.ticker
        if ticker not in prices.columns or pd.isna(prices[ticker].iloc[idx]):
            return

        price = prices[ticker].iloc[idx]

        if signal.action == "BUY":
            self._execute_buy(signal, ticker, price, date)
        elif signal.action == "SELL":
            self._execute_sell(signal, ticker, price, date)

    def _execute_buy(
        self, signal: Signal, ticker: str, price: float, date: datetime
    ):
        if signal.quantity == -1:
            total = self.cash / (price * (1 + self.slippage_pct))
            shares = int(total)
        else:
            shares = signal.quantity

        if shares == 0:
            return

        fill_price = price * (1 + self.slippage_pct)
        cost = shares * fill_price + self._commission(shares)

        if cost > self.cash:
            shares = int(self.cash / (fill_price + self.commission_per_share))
            if shares == 0:
                return
            cost = shares * fill_price + self._commission(shares)

        self.cash -= cost
        self.positions[ticker] += shares

        trade = TradeRecord(
            ticker=ticker, entry_date=date, entry_price=fill_price,
            shares=shares, side="BUY",
        )
        self._open_trades[ticker] = trade

    def _execute_sell(
        self, signal: Signal, ticker: str, price: float, date: datetime
    ):
        held = self.positions.get(ticker, 0)
        if held <= 0:
            return

        shares = signal.quantity if signal.quantity != -1 else held
        shares = min(shares, held)

        fill_price = price * (1 - self.slippage_pct)
        proceeds = shares * fill_price - self._commission(shares)

        self.cash += proceeds
        self.positions[ticker] -= shares
        if self.positions[ticker] == 0:
            del self.positions[ticker]

        trade = self._open_trades.get(ticker)
        if trade:
            trade.exit_date = date
            trade.exit_price = fill_price
            trade.pnl = (fill_price - trade.entry_price) * shares
            trade.pnl_pct = (fill_price / trade.entry_price - 1) * 100
            self.trades.append(trade)
            del self._open_trades[ticker]

    def _commission(self, shares: int) -> float:
        return max(self.commission_min, shares * self.commission_per_share)