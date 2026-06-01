"""A multi-instrument SMA crossover strategy.

Go long when the fast SMA crosses above the slow SMA; flatten when it crosses
back below. Trades each instrument independently.
"""
from __future__ import annotations

import numpy as np

from btengine.indicators import sma
from btengine.strategy.base import Strategy


class SmaCrossover(Strategy):
    def __init__(self, fast: int = 20, slow: int = 50, **params):
        super().__init__(fast=fast, slow=slow, **params)
        self.fast = fast
        self.slow = slow

    def on_bar(self, ctx) -> None:
        for inst in ctx.instruments:
            # Cached, causal indicator lookups (O(1) per bar).
            fast_ma = ctx.indicator(inst, f"sma{self.fast}", lambda df: sma(df["close"], self.fast))
            slow_ma = ctx.indicator(inst, f"sma{self.slow}", lambda df: sma(df["close"], self.slow))
            if np.isnan(fast_ma) or np.isnan(slow_ma):
                continue
            # Capture indicators for the dashboard's price overlay.
            ctx.record(inst, sma_fast=float(fast_ma), sma_slow=float(slow_ma))
            if fast_ma > slow_ma:
                if ctx.units(inst) <= 0:
                    ctx.order_target_units(inst, ctx.default_size(inst))
            else:
                if ctx.units(inst) > 0:
                    ctx.close(inst)
