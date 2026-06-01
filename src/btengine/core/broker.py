"""Simulated execution: converts OrderEvents into FillEvents.

Fill model (no look-ahead): an order placed on bar t is executed against bar
t+1. MARKET orders fill at that bar's open; LIMIT/STOP orders fill only if the
bar's range satisfies the trigger, otherwise the order is cancelled (day order).
Spread, slippage, and commission are applied on top.
"""
from __future__ import annotations

from typing import Optional

import pandas as pd

from btengine.core.events import FillEvent, OrderEvent
from btengine.core.order import OrderType, Side


class SimulatedBroker:
    def __init__(
        self,
        spread: float = 0.0,
        slippage: float = 0.0,
        commission_per_unit: float = 0.0,
        commission_min: float = 0.0,
    ):
        """
        spread: full bid/ask spread in price terms; buyers pay +spread/2,
            sellers receive -spread/2.
        slippage: additional adverse price movement per fill (price terms).
        commission_per_unit: commission charged per traded unit.
        commission_min: minimum commission per fill.
        """
        self.spread = spread
        self.slippage = slippage
        self.commission_per_unit = commission_per_unit
        self.commission_min = commission_min

    def execute(self, event: OrderEvent, bar: pd.Series, timestamp: pd.Timestamp) -> Optional[FillEvent]:
        """Try to fill `event` against `bar` (the OHLCV of the execution bar).

        Returns a FillEvent, or None if the order did not trigger.
        """
        order = event.order
        open_, high, low = float(bar["open"]), float(bar["high"]), float(bar["low"])

        fill_price = self._trigger_price(order.order_type, order.side, open_, high, low,
                                         order.limit_price, order.stop_price)
        if fill_price is None:
            return None

        fill_price = self._apply_costs(fill_price, order.side)
        commission = max(self.commission_min, self.commission_per_unit * order.units)
        return FillEvent(
            timestamp=timestamp,
            instrument=order.instrument,
            side=order.side,
            units=order.units,
            price=fill_price,
            commission=commission,
        )

    def _trigger_price(self, order_type, side, open_, high, low, limit_price, stop_price):
        if order_type is OrderType.MARKET:
            return open_
        if order_type is OrderType.LIMIT:
            # Buy limit fills if price trades at/below limit; sell limit at/above.
            if side is Side.BUY and low <= limit_price:
                return min(open_, limit_price)
            if side is Side.SELL and high >= limit_price:
                return max(open_, limit_price)
            return None
        if order_type is OrderType.STOP:
            # Buy stop triggers if price trades at/above stop; sell stop at/below.
            if side is Side.BUY and high >= stop_price:
                return max(open_, stop_price)
            if side is Side.SELL and low <= stop_price:
                return min(open_, stop_price)
            return None
        raise ValueError(f"Unknown order type {order_type!r}")

    def _apply_costs(self, price: float, side: Side) -> float:
        """Apply half-spread and slippage adversely to the trade direction."""
        adverse = (self.spread / 2.0) + self.slippage
        return price + adverse if side is Side.BUY else price - adverse
