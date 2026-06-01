"""A multi-instrument SMA crossover strategy.

Go long when the fast SMA crosses above the slow SMA; flatten when it crosses
back below. Trades each instrument independently.
"""
from __future__ import annotations

from btengine.indicators import sma
from btengine.strategy.base import Strategy


class SmaCrossover(Strategy):
    def __init__(self, fast: int = 20, slow: int = 50, **params):
        super().__init__(fast=fast, slow=slow, **params)
        self.fast = fast
        self.slow = slow

    def on_bar(self, ctx) -> None:
        for inst in ctx.instruments:
            close = ctx.history(inst)["close"]
            if len(close) < self.slow:
                continue
            fast_ma = sma(close, self.fast)
            slow_ma = sma(close, self.slow)
            if fast_ma.iloc[-1] > slow_ma.iloc[-1]:
                if ctx.units(inst) <= 0:
                    ctx.order_target_units(inst, ctx.default_size(inst))
            else:
                if ctx.units(inst) > 0:
                    ctx.close(inst)
