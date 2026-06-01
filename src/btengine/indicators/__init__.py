"""Vectorized technical indicators operating on pandas Series.

All functions return a Series aligned to the input index. They are causal:
the value at position i depends only on data up to and including i, so calling
them on a rolling history window inside a strategy never introduces look-ahead.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

__all__ = ["sma", "ema", "rsi", "atr", "rolling_std", "crossover", "crossunder", "true_range"]


def sma(series: pd.Series, period: int) -> pd.Series:
    """Simple moving average."""
    return series.rolling(window=period, min_periods=period).mean()


def ema(series: pd.Series, period: int) -> pd.Series:
    """Exponential moving average (adjust=False, conventional trading definition)."""
    return series.ewm(span=period, adjust=False, min_periods=period).mean()


def rolling_std(series: pd.Series, period: int) -> pd.Series:
    """Rolling sample standard deviation."""
    return series.rolling(window=period, min_periods=period).std()


def rsi(series: pd.Series, period: int = 14) -> pd.Series:
    """Relative Strength Index using Wilder's smoothing."""
    delta = series.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)
    # Wilder's smoothing is an EMA with alpha = 1/period.
    avg_gain = gain.ewm(alpha=1.0 / period, adjust=False, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1.0 / period, adjust=False, min_periods=period).mean()
    rs = avg_gain / avg_loss
    out = 100.0 - (100.0 / (1.0 + rs))
    # When avg_loss is 0 (only gains), RSI is 100.
    out = out.where(avg_loss != 0.0, 100.0)
    # Preserve NaN during the warm-up window.
    out[avg_gain.isna()] = np.nan
    return out


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


def crossover(fast: pd.Series, slow: pd.Series) -> pd.Series:
    """Boolean Series: True where `fast` crosses from <= to > `slow`."""
    diff = fast - slow
    prev = diff.shift(1)
    return (prev <= 0) & (diff > 0)


def crossunder(fast: pd.Series, slow: pd.Series) -> pd.Series:
    """Boolean Series: True where `fast` crosses from >= to < `slow`."""
    diff = fast - slow
    prev = diff.shift(1)
    return (prev >= 0) & (diff < 0)
