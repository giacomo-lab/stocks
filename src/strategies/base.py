from abc import ABC, abstractmethod
from collections import namedtuple
from datetime import datetime

import pandas as pd

Signal = namedtuple("Signal", ["ticker", "action", "quantity", "order_type", "limit_price"])


class Strategy(ABC):
    """Base class for all trading strategies.

    Subclasses must implement on_bar() and should set a human-readable
    ``description`` class attribute (or override the property).
    """

    description: str = ""

    def __init__(self, params: dict | None = None):
        self.params = params or {}

    @abstractmethod
    def on_bar(
        self,
        date: datetime,
        data: dict[str, pd.Series],
        positions: dict,
        cash: float,
        equity: float,
    ) -> list[Signal]:
        ...