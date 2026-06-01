"""Session-range indicators (high/low of a market session).

Unlike the price-only indicators in this package, these need the bar timestamps
and a timezone, so they operate on an OHLC DataFrame (UTC DatetimeIndex) together
with a `Session`. They are causal: the value at bar i uses only bars up to i.

For each bar they return the high/low of the *current or most recently completed*
instance of that session. With `lock=True` (default) the levels persist after the
session closes — e.g. the 9:30-10:00 opening range stays fixed for the rest of the
day, and the overnight Asia high/low carry into the day session — which is exactly
what breakout / support-resistance strategies key off.
"""
from __future__ import annotations

from datetime import time
from typing import Optional

import numpy as np
import pandas as pd

from btengine.sessions import ASIA, OPENING_RANGE, Session

_COLUMNS = ["high", "low", "mid", "width"]


def session_range(ohlc: pd.DataFrame, session: Session, lock: bool = True) -> pd.DataFrame:
    """High/low of `session` for each bar in `ohlc`.

    Returns a DataFrame aligned to `ohlc.index` with columns
    [high, low, mid, width]. While a session is in progress the high/low are the
    running extremes so far; once it closes they hold (if `lock`) until the next
    instance begins, otherwise they go NaN between sessions.
    """
    if ohlc.empty:
        return pd.DataFrame(columns=_COLUMNS, index=ohlc.index)

    idx = ohlc.index
    idx_utc = idx.tz_localize("UTC") if idx.tz is None else idx
    local = idx_utc.tz_convert(session.tz)

    mins = local.hour * 60 + local.minute
    open_min = session.open.hour * 60 + session.open.minute
    close_min = session.close.hour * 60 + session.close.minute
    overnight = open_min > close_min

    if overnight:
        in_window = (mins >= open_min) | (mins < close_min)
    else:
        in_window = (mins >= open_min) & (mins < close_min)

    in_sess = in_window & np.isin(local.weekday, list(session.weekdays))
    if session.holidays:
        in_sess &= ~np.array([d.date() in session.holidays for d in local])

    # Instance id = the local date the session opened. For overnight sessions the
    # early-morning bars (before close) belong to the prior evening's instance.
    instance = pd.Series(local.normalize(), index=idx)
    if overnight:
        instance = instance - pd.to_timedelta((mins < close_min).astype(int), unit="D")

    mask = pd.Series(in_sess, index=idx)
    instance = instance.where(mask)  # NaT outside the session -> excluded from groups

    high = ohlc["high"].where(mask).groupby(instance).cummax()
    low = ohlc["low"].where(mask).groupby(instance).cummin()

    if lock:
        high = high.ffill()
        low = low.ffill()

    out = pd.DataFrame({"high": high, "low": low}, index=idx)
    out["mid"] = (out["high"] + out["low"]) / 2.0
    out["width"] = out["high"] - out["low"]
    return out


def opening_range(
    ohlc: pd.DataFrame,
    tz: str = "America/New_York",
    start: time = time(9, 30),
    end: time = time(10, 0),
    lock: bool = True,
) -> pd.DataFrame:
    """Opening-range high/low (default 09:30-10:00 New York)."""
    session = OPENING_RANGE if (tz, start, end) == (OPENING_RANGE.tz, OPENING_RANGE.open, OPENING_RANGE.close) \
        else Session(tz, start, end)
    return session_range(ohlc, session, lock=lock)


def asia_range(
    ohlc: pd.DataFrame,
    tz: str = "America/New_York",
    start: time = time(20, 0),
    end: time = time(3, 0),
    lock: bool = True,
) -> pd.DataFrame:
    """Asia-session high/low (default 20:00-03:00 New York, wraps midnight)."""
    session = ASIA if (tz, start, end) == (ASIA.tz, ASIA.open, ASIA.close) \
        else Session(tz, start, end, weekdays=frozenset(range(7)))
    return session_range(ohlc, session, lock=lock)
