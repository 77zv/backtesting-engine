from __future__ import annotations

import pandas as pd


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
