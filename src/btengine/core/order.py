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

    Time-in-force:
      - "DAY" (default): active for one bar; cancelled if that bar doesn't fill it.
      - "GTC": rests across bars until filled or cancelled (e.g. stop-loss / take-profit).

    `reduce_only` orders may only shrink/close an existing opposite position (never
    open or increase one). `oco_group` links orders so that when one fills, its
    siblings are cancelled (one-cancels-other) — used for stop+target brackets.
    """

    instrument: str
    side: Side
    units: float  # always positive; direction comes from `side`
    order_type: OrderType = OrderType.MARKET
    limit_price: Optional[float] = None
    stop_price: Optional[float] = None
    tif: str = "DAY"
    reduce_only: bool = False
    oco_group: Optional[str] = None
    tag: Optional[str] = None

    def __post_init__(self) -> None:
        if self.units <= 0:
            raise ValueError("Order.units must be positive")
        if self.order_type is OrderType.LIMIT and self.limit_price is None:
            raise ValueError("LIMIT order requires limit_price")
        if self.order_type is OrderType.STOP and self.stop_price is None:
            raise ValueError("STOP order requires stop_price")
        if self.tif not in ("DAY", "GTC"):
            raise ValueError("tif must be 'DAY' or 'GTC'")

    @property
    def signed_units(self) -> float:
        return self.side.sign * self.units
