"""Core event-driven backtesting machinery."""
from btengine.core.engine import Backtester, BacktestResult
from btengine.core.broker import SimulatedBroker
from btengine.core.portfolio import Portfolio, Position
from btengine.core.order import Order, OrderType, Side
from btengine.core.events import FillEvent, MarketEvent, OrderEvent, SignalEvent

__all__ = [
    "Backtester",
    "BacktestResult",
    "SimulatedBroker",
    "Portfolio",
    "Position",
    "Order",
    "OrderType",
    "Side",
    "FillEvent",
    "MarketEvent",
    "OrderEvent",
    "SignalEvent",
]
