import pandas as pd
import pytest

from btengine.core.broker import SimulatedBroker
from btengine.core.events import OrderEvent
from btengine.core.order import Order, OrderType, Side

TS = pd.Timestamp("2023-01-01", tz="UTC")


def _bar(open_, high, low, close):
    return pd.Series({"open": open_, "high": high, "low": low, "close": close, "volume": 1000})


def _order(side, units=10_000, order_type=OrderType.MARKET, limit=None, stop=None):
    return OrderEvent(TS, Order("EUR_USD", side, units, order_type, limit, stop))


def test_market_fill_at_open():
    b = SimulatedBroker()
    fill = b.execute(_order(Side.BUY), _bar(1.10, 1.12, 1.09, 1.11), TS)
    assert fill is not None
    assert fill.price == pytest.approx(1.10)


def test_spread_and_slippage_adverse():
    b = SimulatedBroker(spread=0.0002, slippage=0.0001)
    buy = b.execute(_order(Side.BUY), _bar(1.10, 1.12, 1.09, 1.11), TS)
    sell = b.execute(_order(Side.SELL), _bar(1.10, 1.12, 1.09, 1.11), TS)
    # Buyer pays half-spread + slippage above open; seller receives below.
    assert buy.price == pytest.approx(1.10 + 0.0001 + 0.0001)
    assert sell.price == pytest.approx(1.10 - 0.0001 - 0.0001)


def test_commission_per_unit_with_min():
    b = SimulatedBroker(commission_per_unit=0.0001, commission_min=2.0)
    fill = b.execute(_order(Side.BUY, units=10_000), _bar(1.10, 1.12, 1.09, 1.11), TS)
    assert fill.commission == pytest.approx(max(2.0, 0.0001 * 10_000))


def test_buy_limit_triggers_only_when_price_reaches():
    b = SimulatedBroker()
    o = _order(Side.BUY, order_type=OrderType.LIMIT, limit=1.095)
    # Low (1.09) reaches the limit -> fills at the limit price.
    fill = b.execute(o, _bar(1.10, 1.12, 1.09, 1.11), TS)
    assert fill is not None and fill.price == pytest.approx(1.095)
    # Low (1.10) never reaches -> no fill.
    assert b.execute(o, _bar(1.11, 1.13, 1.10, 1.12), TS) is None


def test_buy_stop_triggers_above():
    b = SimulatedBroker()
    o = _order(Side.BUY, order_type=OrderType.STOP, stop=1.115)
    # High (1.12) exceeds the stop -> fills at the stop price.
    fill = b.execute(o, _bar(1.10, 1.12, 1.09, 1.11), TS)
    assert fill is not None and fill.price == pytest.approx(1.115)
    # High (1.11) below stop -> no fill.
    assert b.execute(o, _bar(1.08, 1.11, 1.07, 1.10), TS) is None
