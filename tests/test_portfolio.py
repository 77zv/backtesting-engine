import pandas as pd
import pytest

from btengine.core.events import FillEvent
from btengine.core.order import Side
from btengine.core.portfolio import Portfolio

TS = pd.Timestamp("2023-01-01", tz="UTC")
TS2 = pd.Timestamp("2023-01-02", tz="UTC")


def _fill(instrument, side, units, price, commission=0.0, ts=TS):
    return FillEvent(ts, instrument, side, units, price, commission)


def test_buy_then_close_realizes_pnl():
    p = Portfolio(initial_cash=100_000)
    p.on_fill(_fill("EUR_USD", Side.BUY, 10_000, 1.10))
    assert p.units("EUR_USD") == 10_000
    assert p.cash == pytest.approx(100_000 - 10_000 * 1.10)
    # Mark at 1.12 -> unrealized profit of 200.
    assert p.equity({"EUR_USD": 1.12}) == pytest.approx(100_000 + 10_000 * (1.12 - 1.10))

    p.on_fill(_fill("EUR_USD", Side.SELL, 10_000, 1.12, ts=TS2))
    assert p.units("EUR_USD") == 0
    assert p.equity({"EUR_USD": 1.12}) == pytest.approx(100_200)
    assert len(p.trades) == 1
    assert p.trades[0].pnl == pytest.approx(200.0)


def test_commission_reduces_cash_and_equity():
    p = Portfolio(initial_cash=100_000)
    p.on_fill(_fill("EUR_USD", Side.BUY, 10_000, 1.10, commission=5.0))
    assert p.total_commission == 5.0
    assert p.equity({"EUR_USD": 1.10}) == pytest.approx(100_000 - 5.0)


def test_average_price_on_scale_in():
    p = Portfolio(initial_cash=100_000)
    p.on_fill(_fill("EUR_USD", Side.BUY, 10_000, 1.10))
    p.on_fill(_fill("EUR_USD", Side.BUY, 10_000, 1.20))
    pos = p.position("EUR_USD")
    assert pos.units == 20_000
    assert pos.avg_price == pytest.approx(1.15)


def test_short_position_pnl():
    p = Portfolio(initial_cash=100_000)
    p.on_fill(_fill("EUR_USD", Side.SELL, 10_000, 1.20))
    assert p.units("EUR_USD") == -10_000
    # Price falls to 1.18 -> short gains 200.
    assert p.equity({"EUR_USD": 1.18}) == pytest.approx(100_000 + 200)
    p.on_fill(_fill("EUR_USD", Side.BUY, 10_000, 1.18, ts=TS2))
    assert p.trades[0].pnl == pytest.approx(200.0)


def test_flip_long_to_short_records_one_trade():
    p = Portfolio(initial_cash=100_000)
    p.on_fill(_fill("EUR_USD", Side.BUY, 10_000, 1.10))
    # Sell 15k: closes 10k long (+ records trade) and opens 5k short.
    p.on_fill(_fill("EUR_USD", Side.SELL, 15_000, 1.15, ts=TS2))
    assert p.units("EUR_USD") == -5_000
    assert p.position("EUR_USD").avg_price == pytest.approx(1.15)
    assert len(p.trades) == 1
    assert p.trades[0].pnl == pytest.approx(10_000 * (1.15 - 1.10))


def test_equity_series_and_trades_frame():
    p = Portfolio(initial_cash=100_000)
    p.mark(TS, {})
    p.mark(TS2, {})
    es = p.equity_series()
    assert list(es.values) == [100_000, 100_000]
    assert isinstance(p.trades_frame(), pd.DataFrame)
