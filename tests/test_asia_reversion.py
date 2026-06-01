"""Tests for the AsiaReversion strategy (fade the London break to the 50% level)."""
import pandas as pd
import pytest

from btengine.core.broker import SimulatedBroker
from btengine.core.engine import Backtester
from btengine.strategy.examples.asia_reversion import AsiaReversion

EPS = 0.05
INIT = 100_000.0


def _bars(rows, tz="America/New_York"):
    """rows: list of (NY-local time string, close). Builds proper OHLC bars."""
    idx = pd.DatetimeIndex(
        [pd.Timestamp(t, tz=tz).tz_convert("UTC") for t, _ in rows], name="time"
    )
    closes = [c for _, c in rows]
    opens = [closes[0]] + closes[:-1]
    highs = [max(o, c) + EPS for o, c in zip(opens, closes)]
    lows = [min(o, c) - EPS for o, c in zip(opens, closes)]
    return pd.DataFrame(
        {"open": opens, "high": highs, "low": lows, "close": closes,
         "volume": [1000] * len(closes)},
        index=idx,
    )


# Asia bars define a 100-102 range (high≈102.05, low≈99.95, mid≈101).
_ASIA = [
    ("2024-05-13 20:00", 100),
    ("2024-05-13 23:00", 102),
    ("2024-05-14 02:00", 101),
]


def _run(rows):
    engine = Backtester({"X": _bars(rows)}, AsiaReversion(), SimulatedBroker(), initial_cash=INIT)
    return engine, engine.run()


def test_short_setup_takes_profit_at_asia_low():
    rows = _ASIA + [
        ("2024-05-14 04:00", 103),   # break above Asia high -> arm short
        ("2024-05-14 05:00", 101),   # revert to mid -> trigger short
        ("2024-05-14 06:00", 100),   # entry fills at open(101); price falls -> TP at Asia low
        ("2024-05-14 09:00", 100),
    ]
    engine, result = _run(rows)
    trades = engine.portfolio.trades
    assert len(trades) == 1
    assert trades[0].units < 0                         # it was a SHORT
    assert trades[0].exit_price == pytest.approx(99.95)  # TP at Asia low
    assert trades[0].pnl == pytest.approx(1000.0)        # +1% (won at 1R)
    assert engine.portfolio.units("X") == 0              # flat after
    # Asia levels were recorded for the dashboard.
    assert "X.asia_high" in result.records.columns


def test_short_stop_loss_risks_one_percent():
    rows = _ASIA + [
        ("2024-05-14 04:00", 103),   # arm short
        ("2024-05-14 05:00", 101),   # trigger short
        ("2024-05-14 06:00", 101),   # entry fills at open(101)
        ("2024-05-14 07:00", 103),   # rises through Asia high -> stop out
        ("2024-05-14 09:00", 103),
    ]
    engine, _ = _run(rows)
    trades = engine.portfolio.trades
    assert len(trades) == 1
    assert trades[0].exit_price == pytest.approx(102.05)   # stopped at Asia high
    # Loss is ~1% of starting equity (the position was sized for exactly that).
    assert trades[0].pnl == pytest.approx(-1000.0)
    assert abs(trades[0].pnl) / INIT == pytest.approx(0.01)
    assert engine.portfolio.units("X") == 0


def test_long_mirror_takes_profit_at_asia_high():
    rows = _ASIA + [
        ("2024-05-14 04:00", 99),    # break below Asia low -> arm long
        ("2024-05-14 05:00", 101),   # revert to mid -> trigger long
        ("2024-05-14 06:00", 102),   # rises -> TP at Asia high
        ("2024-05-14 09:00", 102),
    ]
    engine, _ = _run(rows)
    trades = engine.portfolio.trades
    assert len(trades) == 1
    assert trades[0].units > 0                          # it was a LONG
    assert trades[0].exit_price == pytest.approx(102.05)  # TP at Asia high
    assert trades[0].pnl == pytest.approx(1000.0)
    assert engine.portfolio.units("X") == 0


def test_forced_flat_at_ny_close_no_overnight():
    rows = _ASIA + [
        ("2024-05-14 04:00", 103),   # arm short
        ("2024-05-14 05:00", 101),   # trigger short
        ("2024-05-14 06:00", 101),   # entry fills at open(101)
        ("2024-05-14 10:00", 101),   # held; neither stop nor TP hit
        ("2024-05-14 16:00", 101),   # 16:00 ET -> force close + cancel brackets
        ("2024-05-14 16:15", 101),   # close fills here
    ]
    engine, _ = _run(rows)
    assert engine.portfolio.units("X") == 0              # flat, nothing held overnight
    assert engine._active_orders == []                   # brackets cancelled
    trades = engine.portfolio.trades
    assert len(trades) == 1
    # Exit happened at/after the 16:00 cutoff.
    assert trades[0].exit_time >= pd.Timestamp("2024-05-14 16:00", tz="America/New_York")


def test_one_trade_per_day():
    rows = _ASIA + [
        ("2024-05-14 04:00", 103),   # arm + ...
        ("2024-05-14 05:00", 101),   # trigger short
        ("2024-05-14 06:00", 100),   # entry + TP
        ("2024-05-14 07:00", 103),   # back above Asia high -> would re-arm, but traded_today
        ("2024-05-14 08:00", 101),   # revert again -> must NOT trade again
    ]
    engine, _ = _run(rows)
    assert len(engine.portfolio.trades) == 1
