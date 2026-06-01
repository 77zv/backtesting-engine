"""Tests for resting (GTC), reduce-only, and OCO bracket order behavior."""
import pandas as pd

from btengine.core.broker import SimulatedBroker
from btengine.core.engine import Backtester
from btengine.core.order import Order, OrderType, Side
from btengine.strategy.base import Strategy
from conftest import make_ohlcv


class _Once(Strategy):
    """Submit a set of orders on the first bar only, then do nothing."""

    def __init__(self, orders_fn):
        super().__init__()
        self.orders_fn = orders_fn
        self._done = False

    def on_bar(self, ctx):
        if self._done:
            return
        self._done = True
        self.orders_fn(ctx)


def test_gtc_stop_rests_until_triggered():
    # Prices: 100,101,...; a buy-stop at 105 should fill only when the bar reaches it.
    data = {"X": make_ohlcv([100, 101, 102, 103, 104, 105, 106])}

    def submit(ctx):
        ctx.submit(Order("X", Side.BUY, 1, OrderType.STOP, stop_price=104.5, tif="GTC"))

    engine = Backtester(data, _Once(submit), SimulatedBroker())
    engine.run()
    pos = engine.portfolio.position("X")
    # Filled once price crossed 104.5 (the 105 bar), at the stop price.
    assert pos.units == 1
    assert pos.avg_price == 104.5


def test_day_stop_expires_after_one_bar():
    data = {"X": make_ohlcv([100, 101, 102, 103, 104, 105])}

    def submit(ctx):
        # Day stop at 104.5: active only on bar index 1 (price 101), never reached -> expires.
        ctx.submit(Order("X", Side.BUY, 1, OrderType.STOP, stop_price=104.5, tif="DAY"))

    engine = Backtester(data, _Once(submit), SimulatedBroker())
    engine.run()
    assert engine.portfolio.units("X") == 0  # expired, never filled later


def test_reduce_only_does_not_open_or_flip():
    data = {"X": make_ohlcv([100, 101, 102, 103])}

    def submit(ctx):
        # Reduce-only sell with no position -> must not open a short.
        ctx.submit(Order("X", Side.SELL, 5, OrderType.MARKET, tif="GTC", reduce_only=True))

    engine = Backtester(data, _Once(submit), SimulatedBroker())
    engine.run()
    assert engine.portfolio.units("X") == 0


def test_reduce_only_clamps_to_open_position():
    data = {"X": make_ohlcv([100, 101, 102, 103, 104])}

    def submit(ctx):
        ctx.submit(Order("X", Side.BUY, 3, OrderType.MARKET))          # open +3
        # Oversized reduce-only sell should close exactly 3, not flip to -7.
        ctx.submit(Order("X", Side.SELL, 10, OrderType.MARKET, tif="GTC", reduce_only=True))

    engine = Backtester(data, _Once(submit), SimulatedBroker())
    engine.run()
    assert engine.portfolio.units("X") == 0


def test_oco_bracket_one_cancels_other():
    # Rising prices: a long's take-profit should fill and cancel the stop-loss.
    data = {"X": make_ohlcv([100, 101, 102, 103, 104, 105, 106])}

    def submit(ctx):
        ctx.enter("X", Side.BUY, 1, stop_loss=98, take_profit=103.5)

    engine = Backtester(data, _Once(submit), SimulatedBroker())
    engine.run()
    # TP filled (price rose through 103.5); position flat; stop was cancelled.
    assert engine.portfolio.units("X") == 0
    assert len(engine.portfolio.trades) == 1
    assert engine.portfolio.trades[0].exit_price == 103.5
    # No resting orders left over.
    assert engine._active_orders == []


def test_cancel_all_removes_resting_orders():
    data = {"X": make_ohlcv([100, 101, 102, 103, 104])}

    class _SubmitThenCancel(Strategy):
        def __init__(self):
            super().__init__()
            self.bar = 0

        def on_bar(self, ctx):
            if self.bar == 0:
                ctx.submit(Order("X", Side.BUY, 1, OrderType.STOP, stop_price=200, tif="GTC"))
            elif self.bar == 1:
                ctx.cancel_all("X")
            self.bar += 1

    engine = Backtester(data, _SubmitThenCancel(), SimulatedBroker())
    engine.run()
    assert engine._active_orders == []
    assert engine.portfolio.units("X") == 0
