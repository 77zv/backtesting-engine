"""Event records flowing through the engine.

Pipeline: MarketEvent -> SignalEvent -> OrderEvent -> FillEvent.
"""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from btengine.core.order import Order, Side


@dataclass
class MarketEvent:
    """A new bar (or set of bars) is available at `timestamp`."""

    timestamp: pd.Timestamp


@dataclass
class SignalEvent:
    """A strategy's intent to change exposure, expressed as a signed unit delta.

    Positive `units` buys, negative sells. The portfolio turns this into an Order.
    """

    timestamp: pd.Timestamp
    instrument: str
    units: float  # signed delta in units


@dataclass
class OrderEvent:
    timestamp: pd.Timestamp
    order: Order


@dataclass
class FillEvent:
    timestamp: pd.Timestamp
    instrument: str
    side: Side
    units: float        # positive
    price: float        # actual fill price incl. spread/slippage
    commission: float
