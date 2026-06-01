"""Portfolio: position accounting, cash, equity curve, and trade log.

Accounting is equity-style (cash -= signed_units * price). For a single-currency
FX pair quoted in the account currency this reproduces correct mark-to-market
P&L: equity == initial_cash + sum(units * (current_price - entry_price)) - costs.
Margin and leverage are not modelled (no margin calls).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

import pandas as pd

from btengine.core.events import FillEvent, OrderEvent, SignalEvent
from btengine.core.order import Order, OrderType, Side


@dataclass
class Position:
    units: float = 0.0       # signed
    avg_price: float = 0.0   # average entry price of the open position

    @property
    def is_flat(self) -> bool:
        return self.units == 0.0

    @property
    def is_long(self) -> bool:
        return self.units > 0.0

    @property
    def is_short(self) -> bool:
        return self.units < 0.0


@dataclass
class Trade:
    """A realized (closed or reduced) portion of a position."""

    instrument: str
    entry_time: Optional[pd.Timestamp]
    exit_time: pd.Timestamp
    units: float          # signed units that were closed
    entry_price: float
    exit_price: float
    pnl: float


class Portfolio:
    def __init__(self, initial_cash: float = 100_000.0):
        self.initial_cash = float(initial_cash)
        self.cash = float(initial_cash)
        self.positions: Dict[str, Position] = {}
        self._entry_time: Dict[str, pd.Timestamp] = {}
        self.trades: List[Trade] = []
        self.equity_curve: List[tuple] = []  # (timestamp, equity)
        self.total_commission = 0.0

    # ----- position access -------------------------------------------------
    def position(self, instrument: str) -> Position:
        return self.positions.setdefault(instrument, Position())

    def units(self, instrument: str) -> float:
        return self.position(instrument).units

    # ----- signal -> order -------------------------------------------------
    def create_order(self, signal: SignalEvent) -> Optional[OrderEvent]:
        """Turn a signed-unit signal into a market OrderEvent (None if zero)."""
        if signal.units == 0:
            return None
        side = Side.BUY if signal.units > 0 else Side.SELL
        order = Order(
            instrument=signal.instrument,
            side=side,
            units=abs(signal.units),
            order_type=OrderType.MARKET,
        )
        return OrderEvent(timestamp=signal.timestamp, order=order)

    # ----- fill handling ---------------------------------------------------
    def on_fill(self, fill: FillEvent) -> None:
        pos = self.position(fill.instrument)
        signed = fill.side.sign * fill.units

        self.cash -= signed * fill.price
        self.cash -= fill.commission
        self.total_commission += fill.commission

        old_units = pos.units
        new_units = old_units + signed

        if old_units == 0 or (old_units > 0) == (signed > 0):
            # Opening or increasing in the same direction: blend the entry price.
            if new_units != 0:
                pos.avg_price = (old_units * pos.avg_price + signed * fill.price) / new_units
            if old_units == 0:
                self._entry_time[fill.instrument] = fill.timestamp
        else:
            # Reducing, closing, or flipping: realize P&L on the closed portion.
            closed = min(abs(signed), abs(old_units))
            direction = 1.0 if old_units > 0 else -1.0
            pnl = direction * closed * (fill.price - pos.avg_price)
            self.trades.append(
                Trade(
                    instrument=fill.instrument,
                    entry_time=self._entry_time.get(fill.instrument),
                    exit_time=fill.timestamp,
                    units=direction * closed,
                    entry_price=pos.avg_price,
                    exit_price=fill.price,
                    pnl=pnl,
                )
            )
            if new_units == 0:
                pos.avg_price = 0.0
                self._entry_time.pop(fill.instrument, None)
            elif (new_units > 0) != (old_units > 0):
                # Flipped to the opposite side: new entry at the fill price.
                pos.avg_price = fill.price
                self._entry_time[fill.instrument] = fill.timestamp
            # else: partial reduction, avg_price unchanged.

        pos.units = new_units

    # ----- mark to market --------------------------------------------------
    def market_value(self, prices: Dict[str, float]) -> float:
        total = 0.0
        for instrument, pos in self.positions.items():
            if pos.units != 0 and instrument in prices:
                total += pos.units * prices[instrument]
        return total

    def equity(self, prices: Dict[str, float]) -> float:
        return self.cash + self.market_value(prices)

    def mark(self, timestamp: pd.Timestamp, prices: Dict[str, float]) -> float:
        eq = self.equity(prices)
        self.equity_curve.append((timestamp, eq))
        return eq

    def equity_series(self) -> pd.Series:
        if not self.equity_curve:
            return pd.Series(dtype=float, name="equity")
        idx, vals = zip(*self.equity_curve)
        return pd.Series(vals, index=pd.DatetimeIndex(idx, name="time"), name="equity")

    def trades_frame(self) -> pd.DataFrame:
        if not self.trades:
            return pd.DataFrame(
                columns=["instrument", "entry_time", "exit_time", "units",
                         "entry_price", "exit_price", "pnl"]
            )
        return pd.DataFrame([t.__dict__ for t in self.trades])
