"""Opening-range breakout retest.

After the 09:30-10:00 NY opening range locks:
  1. During 10:00-11:00, arm if any bar closes outside the OR:
       close > OR high  →  arm "long"   (breakout above)
       close < OR low   →  arm "short"  (breakout below)
  2. Once armed, wait for price to return to the violated boundary:
       armed long  + price ≤ OR high  →  BUY  at market
       armed short + price ≥ OR low   →  SELL at market
  3. Bracket: stop and take-profit each equal one OR width from the entry level,
     giving a 1:1 risk/reward measured in OR widths.
       long:  stop = OR high − OR width (= OR low),  TP = OR high + OR width
       short: stop = OR low  + OR width (= OR high), TP = OR low  − OR width
  4. Size so the stop risks risk_pct (default 1%) of equity.
  5. One trade per instrument per day; force-flat at 16:00 NY.

Use an intraday granularity finer than 30 minutes (M5 or M15 recommended).
"""
from __future__ import annotations

from datetime import time

import numpy as np

from btengine.core.order import Side
from btengine.indicators import opening_range
from btengine.strategy.base import Strategy

_BREAKOUT_START = time(10, 0)   # OR locks; begin monitoring for a close outside it
_BREAKOUT_END   = time(11, 0)   # last bar that can arm the setup
_FLAT_TIME      = time(16, 0)   # force-flat; never hold overnight


class ORBRetest(Strategy):
    """Opening-range breakout retest with 1:1 OR-width stop/target bracket."""

    def __init__(self, risk_pct: float = 0.01, tz: str = "America/New_York", **params):
        super().__init__(risk_pct=risk_pct, tz=tz, **params)
        self.risk_pct = risk_pct
        self.tz = tz
        self._day = {}      # instrument -> current NY date
        self._armed = {}    # instrument -> None | "long" | "short"
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

            orr = ctx.indicator(inst, "opening_range", opening_range)
            or_high, or_low = orr["high"], orr["low"]

            if not (np.isnan(or_high) or np.isnan(or_low)):
                ctx.record(inst, or_high=or_high, or_low=or_low)

            # Force-flat at/after the NY close; never hold overnight.
            if t >= _FLAT_TIME:
                if ctx.units(inst) != 0:
                    ctx.close(inst)
                    ctx.cancel_all(inst)
                continue

            if np.isnan(or_high) or np.isnan(or_low):
                continue

            price = ctx.price(inst)
            if price is None:
                continue

            or_width = or_high - or_low

            # Phase 1: arm on a close outside the OR (10:00–11:00 window only).
            if self._armed[inst] is None and _BREAKOUT_START <= t < _BREAKOUT_END:
                if price > or_high:
                    self._armed[inst] = "long"
                elif price < or_low:
                    self._armed[inst] = "short"

            # Phase 2: trigger on retest of the violated OR boundary.
            # On the arming bar price is outside the OR, so these conditions
            # are mutually exclusive with Phase 1 — no same-bar entry.
            if self._armed[inst] is not None and not self._traded[inst]:
                if self._armed[inst] == "long" and price <= or_high:
                    stop   = or_high - or_width   # = OR low
                    target = or_high + or_width
                    units  = ctx.units_for_risk(inst, stop_price=stop,
                                                entry_price=or_high,
                                                risk_pct=self.risk_pct)
                    ctx.enter(inst, Side.BUY, units,
                              stop_loss=stop, take_profit=target, tag="orb_long")
                    self._traded[inst] = True
                elif self._armed[inst] == "short" and price >= or_low:
                    stop   = or_low + or_width    # = OR high
                    target = or_low - or_width
                    units  = ctx.units_for_risk(inst, stop_price=stop,
                                                entry_price=or_low,
                                                risk_pct=self.risk_pct)
                    ctx.enter(inst, Side.SELL, units,
                              stop_loss=stop, take_profit=target, tag="orb_short")
                    self._traded[inst] = True
