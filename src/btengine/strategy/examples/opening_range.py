"""Opening-range breakout — a session-aware example.

On the first bar of each session, records that bar's high/low as the opening
range. For the rest of the session, goes long on a break above the range high
and flattens on a break below the range low. Positions are closed at session end
(the next session start resets the range and any leftover position is squared by
the new day's logic, but we also flatten explicitly when the session closes).
"""
from __future__ import annotations

from btengine.sessions import NYSE, Session
from btengine.strategy.session_strategy import SessionStrategy


class OpeningRange(SessionStrategy):
    session: Session = NYSE

    def __init__(self, session: Session = NYSE, **params):
        super().__init__(session=session, **params)
        self._high = {}
        self._low = {}

    def on_session_start(self, ctx, instrument: str) -> None:
        bar = ctx.bar(instrument)
        self._high[instrument] = float(bar["high"])
        self._low[instrument] = float(bar["low"])
        # Flat at the open; the range is being established this bar.
        if ctx.units(instrument) != 0:
            ctx.close(instrument)

    def on_session_bar(self, ctx, instrument: str) -> None:
        hi = self._high.get(instrument)
        lo = self._low.get(instrument)
        if hi is None or lo is None:
            return
        price = ctx.price(instrument)
        if price > hi and ctx.units(instrument) <= 0:
            ctx.buy(instrument)
        elif price < lo and ctx.units(instrument) > 0:
            ctx.close(instrument)
