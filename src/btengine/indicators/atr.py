from __future__ import annotations

import pandas as pd


def true_range(high: pd.Series, low: pd.Series, close: pd.Series) -> pd.Series:
    """True Range: max of (H-L, |H-prev_close|, |L-prev_close|)."""
    prev_close = close.shift(1)
    ranges = pd.concat(
        [high - low, (high - prev_close).abs(), (low - prev_close).abs()],
        axis=1,
    )
    return ranges.max(axis=1)


def atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    """Average True Range using Wilder's smoothing."""
    tr = true_range(high, low, close)
    return tr.ewm(alpha=1.0 / period, adjust=False, min_periods=period).mean()
