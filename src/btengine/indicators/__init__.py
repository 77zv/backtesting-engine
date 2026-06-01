"""Vectorized technical indicators operating on pandas Series.

All functions return a Series aligned to the input index. They are causal:
the value at position i depends only on data up to and including i, so calling
them on a rolling history window inside a strategy never introduces look-ahead.
"""
from btengine.indicators.atr import atr, true_range
from btengine.indicators.cross import crossover, crossunder
from btengine.indicators.moving_average import ema, rolling_std, sma
from btengine.indicators.rsi import rsi

__all__ = ["sma", "ema", "rsi", "atr", "rolling_std", "crossover", "crossunder", "true_range"]
