from __future__ import annotations

import pandas as pd


def sma(series: pd.Series, period: int) -> pd.Series:
    """Simple moving average."""
    return series.rolling(window=period, min_periods=period).mean()


def ema(series: pd.Series, period: int) -> pd.Series:
    """Exponential moving average (adjust=False, conventional trading definition)."""
    return series.ewm(span=period, adjust=False, min_periods=period).mean()


def rolling_std(series: pd.Series, period: int) -> pd.Series:
    """Rolling sample standard deviation."""
    return series.rolling(window=period, min_periods=period).std()
