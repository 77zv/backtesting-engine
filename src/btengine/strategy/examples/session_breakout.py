"""Session breakout — demonstrates the session-range indicators on the chart.

Each bar it computes the opening-range (09:30-10:00 NY) and Asia-session
(20:00-03:00 NY) high/low and records all four levels via `ctx.record`, so they
overlay on the dashboard's price panel. Trading logic: once the opening range is
locked, go long on a break above the OR high and flatten on a break below the OR
low (one position per instrument).

Use an intraday granularity finer than the 30-min opening range (e.g. M15/M5);
on H1 there is no bar inside 09:30-10:00 so the OR would be empty.
"""
from __future__ import annotations

import numpy as np

from btengine.indicators import asia_range, opening_range
from btengine.strategy.base import Strategy


class SessionBreakout(Strategy):
    def on_bar(self, ctx) -> None:
        for inst in ctx.instruments:
            hist = ctx.history(inst)
            if len(hist) < 2:
                continue

            orr = opening_range(hist).iloc[-1]
            asia = asia_range(hist).iloc[-1]

            # Record levels for the dashboard overlay (NaN renders as a gap).
            ctx.record(
                inst,
                or_high=orr["high"], or_low=orr["low"],
                asia_high=asia["high"], asia_low=asia["low"],
            )

            or_high, or_low = orr["high"], orr["low"]
            if np.isnan(or_high) or np.isnan(or_low):
                continue

            price = ctx.price(inst)
            if price > or_high and ctx.units(inst) <= 0:
                ctx.buy(inst)
            elif price < or_low and ctx.units(inst) > 0:
                ctx.close(inst)
