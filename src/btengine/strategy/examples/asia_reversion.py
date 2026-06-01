"""Asia-range reversion (fade the London break back to the 50% level).

For each instrument, once the Asia session (20:00-03:00 NY) has closed:
  - During the London window (03:00-09:30 NY, before the NY open) watch for price
    to break beyond the Asia range.
  - When it reverts to the Asia midpoint (50%), fade it: enter toward the opposite
    extreme with a stop at the broken extreme and a take-profit at the far extreme.
      * broke ABOVE Asia high, back to mid  -> SHORT, stop = Asia high, TP = Asia low
      * broke BELOW Asia low, back to mid    -> LONG,  stop = Asia low,  TP = Asia high
  - Size so the stop risks ~1% of equity. One trade per instrument per day.
  - Flat by 16:00 NY (no overnight hold); resting brackets are cancelled on exit.

Use an intraday granularity finer than the Asia window (M15/M5/M1).
"""
from __future__ import annotations

from datetime import time

import numpy as np

from btengine.core.order import Side
from btengine.indicators import asia_range
from btengine.strategy.base import Strategy

_LONDON_OPEN = time(3, 0)    # Asia close / London-window start (NY)
_NY_OPEN = time(9, 30)       # entry window end (NY)
_FLAT_TIME = time(16, 0)     # force-flat at the NY close


class AsiaReversion(Strategy):
    def __init__(self, risk_pct: float = 0.01, tz: str = "America/New_York", **params):
        super().__init__(risk_pct=risk_pct, tz=tz, **params)
        self.risk_pct = risk_pct
        self.tz = tz
        self._day = {}      # instrument -> current NY date
        self._armed = {}    # instrument -> None | "short" | "long"
        self._traded = {}   # instrument -> bool (one trade per day)

    def on_bar(self, ctx) -> None:
        local = ctx.local(self.tz)
        today = local.date()
        t = local.time()

        for inst in ctx.instruments:
            # New NY day: reset the per-day state machine.
            if self._day.get(inst) != today:
                self._day[inst] = today
                self._armed[inst] = None
                self._traded[inst] = False

            asia = ctx.indicator(inst, "asia", asia_range)  # cached; O(1) per bar
            hi, lo, mid = asia["high"], asia["low"], asia["mid"]
            if not (np.isnan(hi) or np.isnan(lo)):
                ctx.record(inst, asia_high=hi, asia_low=lo, asia_mid=mid)

            # Force-flat at/after the NY close; never hold overnight.
            if t >= _FLAT_TIME:
                if ctx.units(inst) != 0:
                    ctx.close(inst)
                    ctx.cancel_all(inst)
                continue

            # Only set up trades in the London window, before the NY open.
            in_window = _LONDON_OPEN <= t < _NY_OPEN
            if not in_window or self._traded[inst] or np.isnan(hi) or np.isnan(lo):
                continue

            price = ctx.price(inst)
            if price is None:
                continue

            # Arm on a break beyond the Asia range.
            if self._armed[inst] is None:
                if price > hi:
                    self._armed[inst] = "short"
                elif price < lo:
                    self._armed[inst] = "long"
                continue

            # Trigger on the reversion back to the 50% level.
            if self._armed[inst] == "short" and price <= mid:
                units = ctx.units_for_risk(inst, stop_price=hi, risk_pct=self.risk_pct)
                ctx.enter(inst, Side.SELL, units, stop_loss=hi, take_profit=lo, tag="asia_short")
                self._traded[inst] = True
            elif self._armed[inst] == "long" and price >= mid:
                units = ctx.units_for_risk(inst, stop_price=lo, risk_pct=self.risk_pct)
                ctx.enter(inst, Side.BUY, units, stop_loss=lo, take_profit=hi, tag="asia_long")
                self._traded[inst] = True
