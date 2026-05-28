from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class OrderAction(Enum):
    BUY = "BUY"
    SELL = "SELL"


class OrderType(Enum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    STOP = "STOP"


@dataclass
class Order:
    ticker: str
    action: OrderAction
    quantity: int
    order_type: OrderType = OrderType.MARKET
    limit_price: float | None = None


@dataclass
class Fill:
    order_id: str
    ticker: str
    action: OrderAction
    quantity: int
    price: float
    timestamp: datetime


class Broker(ABC):
    @abstractmethod
    def connect(self) -> bool:
        ...

    @abstractmethod
    def place_order(self, order: Order) -> str:
        ...

    @abstractmethod
    def cancel_order(self, order_id: str) -> bool:
        ...

    @abstractmethod
    def get_positions(self) -> dict:
        ...

    @abstractmethod
    def get_cash(self) -> float:
        ...

    @abstractmethod
    def disconnect(self) -> bool:
        ...