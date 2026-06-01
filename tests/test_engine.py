import numpy as np
import pandas as pd
import pytest

from btengine.core.broker import SimulatedBroker
from btengine.core.engine import Backtester
from btengine.strategy.base import Strategy
from conftest import make_ohlcv


class BuyAndHold(Strategy):
    """Buy a fixed size on the first available bar, then hold."""

    def __init__(self, units=10):
        super().__init__()
        self.units = units
        self.bought = False

    def on_bar(self, ctx):
        inst = ctx.instruments[0]
        if not self.bought and len(ctx.history(inst)) >= 1:
            ctx.buy(inst, self.units)
            self.bought = True


class RecordingStrategy(Strategy):
    """Records the latest visible timestamp at every on_bar call."""

    def __init__(self):
        super().__init__()
        self.seen = []
        self.history_lengths = []

    def on_bar(self, ctx):
        inst = ctx.instruments[0]
        hist = ctx.history(inst)
        self.seen.append((ctx.now, hist.index[-1] if len(hist) else None))
        self.history_lengths.append(len(hist))


def test_buy_and_hold_pnl_no_costs():
    data = {"EUR_USD": make_ohlcv(list(range(100, 120)))}  # 20 bars, close 100..119
    engine = Backtester(data, BuyAndHold(units=10), broker=SimulatedBroker(),
                        initial_cash=100_000, default_units=10)
    result = engine.run()

    # Order placed on bar 0 close, filled at bar 1 open (== bar 0 close == 100).
    # Held to final close 119: PnL = 10 * (119 - 100) = 190.
    assert result.equity.iloc[-1] == pytest.approx(100_190.0)
    assert engine.portfolio.units("EUR_USD") == 10
    assert result.bars == 20


def test_no_lookahead():
    data = {"EUR_USD": make_ohlcv(list(range(100, 110)))}
    strat = RecordingStrategy()
    Backtester(data, strat).run()

    # The latest visible bar must always equal the current time — never the future.
    for now, last_seen in strat.seen:
        assert last_seen == now
    # History grows by exactly one bar per step for a single contiguous instrument.
    assert strat.history_lengths == list(range(1, 11))


def test_spread_costs_reduce_pnl():
    data = {"EUR_USD": make_ohlcv(list(range(100, 120)))}
    no_cost = Backtester(data, BuyAndHold(10), SimulatedBroker(),
                         initial_cash=100_000, default_units=10).run()
    with_cost = Backtester(data, BuyAndHold(10), SimulatedBroker(spread=0.02),
                           initial_cash=100_000, default_units=10).run()
    # Paying half-spread (0.01) on 10 units raises the entry by 0.10 of equity.
    assert with_cost.equity.iloc[-1] < no_cost.equity.iloc[-1]
    assert no_cost.equity.iloc[-1] - with_cost.equity.iloc[-1] == pytest.approx(10 * 0.01)


def test_multi_instrument_runs_and_aligns():
    data = {
        "EUR_USD": make_ohlcv(list(range(100, 120))),
        "GBP_USD": make_ohlcv(list(range(200, 220))),
    }
    engine = Backtester(data, BuyAndHold(10), initial_cash=100_000, default_units=10)
    result = engine.run()
    # Both instruments share the same timeline here.
    assert result.bars == 20
    assert len(result.equity) == 20


def test_misaligned_timestamps_union():
    a = make_ohlcv([1, 2, 3], start="2023-01-01", freq="2h")  # 00:00, 02:00, 04:00
    b = make_ohlcv([1, 2, 3], start="2023-01-01 01:00", freq="2h")  # 01:00, 03:00, 05:00
    engine = Backtester({"A": a, "B": b}, RecordingStrategy())
    result = engine.run()
    # Union of two 3-bar series with no shared timestamps -> 6 bars.
    assert result.bars == 6
