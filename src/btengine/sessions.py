"""Opt-in market-session helpers.

This module is *policy*, layered on top of the engine's UTC core. A `Session`
describes a market's trading hours in local civil time plus its IANA timezone;
every query converts the bar's UTC instant to local time first, so DST is handled
in exactly one place and is correct for the candle's *own* date (not "today").

Strategies import this only if they care about sessions. Nothing here touches
engine internals or the host machine's clock.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time
from typing import FrozenSet, Optional

import pandas as pd

# Weekday integers as returned by datetime.weekday(): Mon=0 .. Sun=6.
_WEEKDAYS_MON_FRI = frozenset({0, 1, 2, 3, 4})


@dataclass(frozen=True)
class Session:
    """A market's trading session in local civil time.

    open/close are local wall-clock times in `tz`. Intraday sessions
    (open < close) are the common case; overnight sessions (open > close,
    wrapping past midnight) are also supported by `is_open`.
    """

    tz: str
    open: time
    close: time
    weekdays: FrozenSet[int] = _WEEKDAYS_MON_FRI
    holidays: FrozenSet[date] = field(default_factory=frozenset)

    # --- conversion --------------------------------------------------------
    def to_local(self, ts: pd.Timestamp) -> pd.Timestamp:
        """Convert a tz-aware UTC timestamp to this session's local time."""
        if ts.tzinfo is None:
            ts = ts.tz_localize("UTC")
        return ts.tz_convert(self.tz)

    # --- queries (all stateless, DST-correct) ------------------------------
    def is_open(self, ts: pd.Timestamp) -> bool:
        """True if the instant `ts` falls within the trading session."""
        local = self.to_local(ts)
        if local.weekday() not in self.weekdays:
            return False
        if local.date() in self.holidays:
            return False
        t = local.time()
        if self.open <= self.close:
            return self.open <= t < self.close
        # Overnight session wrapping past midnight.
        return t >= self.open or t < self.close

    def minutes_since_open(self, ts: pd.Timestamp) -> Optional[float]:
        """Minutes elapsed since today's session open, or None if not in session."""
        if not self.is_open(ts):
            return None
        local = self.to_local(ts)
        open_dt = datetime.combine(local.date(), self.open, tzinfo=local.tzinfo)
        return (local - pd.Timestamp(open_dt)).total_seconds() / 60.0

    def is_start(self, history) -> bool:
        """True if the most recent bar in `history` is the session's first bar.

        Derived purely from data: the latest bar is a start iff it is in-session
        and the immediately preceding bar was either out of session or on a
        different local date. `history` is a DataFrame or DatetimeIndex; only its
        index/timestamps are used. No external state required.
        """
        index = getattr(history, "index", history)
        n = len(index)
        if n == 0:
            return False
        last = index[-1]
        if not self.is_open(last):
            return False
        if n == 1:
            return True
        prev = index[-2]
        if not self.is_open(prev):
            return True
        return self.to_local(prev).date() != self.to_local(last).date()


# --- presets ---------------------------------------------------------------
NYSE = Session("America/New_York", time(9, 30), time(16, 0))
LONDON = Session("Europe/London", time(8, 0), time(16, 30))
TOKYO = Session("Asia/Tokyo", time(9, 0), time(15, 0))  # no DST, mechanics identical
