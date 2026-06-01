"""Shared test fixtures and helpers."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest


def make_ohlcv(closes, start="2023-01-01", freq="h", spread=0.0):
    """Build a simple OHLCV frame from a list of close prices.

    open == previous close (or first close on bar 0); high/low bracket the bar.
    """
    closes = np.asarray(closes, dtype=float)
    index = pd.date_range(start=start, periods=len(closes), freq=freq, tz="UTC", name="time")
    opens = np.empty_like(closes)
    opens[0] = closes[0]
    opens[1:] = closes[:-1]
    highs = np.maximum(opens, closes) + spread
    lows = np.minimum(opens, closes) - spread
    volume = np.full_like(closes, 1000.0)
    return pd.DataFrame(
        {"open": opens, "high": highs, "low": lows, "close": closes, "volume": volume},
        index=index,
    )


@pytest.fixture
def ramp_ohlcv():
    """20 bars rising from 100 to 119 by 1 each bar."""
    return make_ohlcv(list(range(100, 120)))
