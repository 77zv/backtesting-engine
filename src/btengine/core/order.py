"""Order primitives."""
from __future__ import annotations

import enum
from dataclasses import dataclass
from typing import Optional


class Side(enum.Enum):
    BUY = "BUY"
    SELL = "SELL"

    @property
    def sign(self) -> int:
        return 1 if self is Side.BUY else -1


class OrderType(enum.Enum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    STOP = "STOP"


@dataclass
class Order:
    """An instruction to trade `units` of `instrument`.

    Orders are placed on bar t and become active on bar t+1 (no look-ahead).
    An unfilled LIMIT/STOP order is treated as a day order: cancelled if the
    next bar does not satisfy it.
    """

    instrument: str
    side: Side
    units: float  # always positive; direction comes from `side`
    order_type: OrderType = OrderType.MARKET
    limit_price: Optional[float] = None
    stop_price: Optional[float] = None

    def __post_init__(self) -> None:
        if self.units <= 0:
            raise ValueError("Order.units must be positive")
        if self.order_type is OrderType.LIMIT and self.limit_price is None:
            raise ValueError("LIMIT order requires limit_price")
        if self.order_type is OrderType.STOP and self.stop_price is None:
            raise ValueError("STOP order requires stop_price")

    @property
    def signed_units(self) -> float:
        return self.side.sign * self.units
