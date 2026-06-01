import numpy as np
import pandas as pd
import pytest

from btengine.indicators import asia_range, opening_range, session_range
from btengine.sessions import OPENING_RANGE


def _bars(local_times, highs, lows, tz="America/New_York"):
    idx = pd.DatetimeIndex(
        [pd.Timestamp(t, tz=tz).tz_convert("UTC") for t in local_times], name="time"
    )
    return pd.DataFrame(
        {"open": lows, "high": highs, "low": lows, "close": highs}, index=idx
    )


def test_opening_range_locks_after_window():
    df = _bars(
        ["2024-07-15 09:00", "2024-07-15 09:30", "2024-07-15 09:45",
         "2024-07-15 10:00", "2024-07-15 11:00"],
        highs=[99, 101, 103, 110, 120],
        lows=[98, 100, 99, 90, 80],
    )
    out = opening_range(df)
    # Before the open: undefined.
    assert np.isnan(out["high"].iloc[0]) and np.isnan(out["low"].iloc[0])
    # Running during the window.
    assert out["high"].iloc[1] == 101 and out["low"].iloc[1] == 100
    assert out["high"].iloc[2] == 103 and out["low"].iloc[2] == 99
    # Locked after 10:00 (the 110/90 and 120/80 bars are outside the window).
    assert (out["high"].iloc[3:] == 103).all()
    assert (out["low"].iloc[3:] == 99).all()
    assert out["mid"].iloc[-1] == pytest.approx((103 + 99) / 2)
    assert out["width"].iloc[-1] == pytest.approx(103 - 99)


def test_asia_range_spans_midnight():
    df = _bars(
        ["2024-07-15 19:00", "2024-07-15 20:00", "2024-07-15 23:00",
         "2024-07-16 02:00", "2024-07-16 09:00"],
        highs=[50, 60, 70, 65, 100],
        lows=[49, 55, 52, 48, 90],
    )
    out = asia_range(df)
    assert np.isnan(out["high"].iloc[0])           # 19:00 is before the 20:00 open
    assert out["high"].iloc[1] == 60               # session opens
    # The 02:00 next-morning bar belongs to the SAME session that opened at 20:00.
    assert out["high"].iloc[3] == 70 and out["low"].iloc[3] == 48
    # After 03:00 close, levels lock through the day.
    assert out["high"].iloc[4] == 70 and out["low"].iloc[4] == 48


def test_separate_days_get_separate_ranges():
    df = _bars(
        ["2024-07-15 09:30", "2024-07-15 09:45",   # day 1 OR: 105/100
         "2024-07-16 09:30", "2024-07-16 09:45"],  # day 2 OR: 205/200
        highs=[103, 105, 203, 205],
        lows=[100, 101, 200, 201],
    )
    out = opening_range(df)
    assert out["high"].iloc[1] == 105 and out["low"].iloc[1] == 100
    # New day resets to its own range, not carrying day 1's levels.
    assert out["high"].iloc[2] == 203 and out["low"].iloc[2] == 200


def test_no_lock_goes_nan_between_sessions():
    df = _bars(
        ["2024-07-15 09:45", "2024-07-15 12:00"],  # in-window, then out
        highs=[105, 130],
        lows=[100, 90],
    )
    out = opening_range(df, lock=False)
    assert out["high"].iloc[0] == 105
    assert np.isnan(out["high"].iloc[1])           # outside window, not locked


def test_dst_correct_window_membership():
    # 09:30 NY is 13:30 UTC in summer (EDT) and 14:30 UTC in winter (EST).
    summer = opening_range(_bars(["2024-07-15 09:30"], [101], [100]))
    winter = opening_range(_bars(["2024-01-15 09:30"], [101], [100]))
    assert summer["high"].iloc[0] == 101    # recognized as in-window despite
    assert winter["high"].iloc[0] == 101    # different UTC instants
    assert summer.index[0] == pd.Timestamp("2024-07-15 13:30", tz="UTC")
    assert winter.index[0] == pd.Timestamp("2024-01-15 14:30", tz="UTC")


def test_causal_when_called_on_growing_history():
    df = _bars(
        ["2024-07-15 09:30", "2024-07-15 09:45", "2024-07-15 11:00"],
        highs=[101, 103, 120],
        lows=[100, 99, 80],
    )
    # Value at each bar must match the full-series computation up to that bar.
    full = opening_range(df)
    for i in range(1, len(df) + 1):
        partial = opening_range(df.iloc[:i])
        assert partial["high"].iloc[-1] == full["high"].iloc[i - 1] or (
            np.isnan(partial["high"].iloc[-1]) and np.isnan(full["high"].iloc[i - 1])
        )


def test_empty_input():
    empty = pd.DataFrame(
        columns=["open", "high", "low", "close"],
        index=pd.DatetimeIndex([], tz="UTC", name="time"),
    )
    out = session_range(empty, OPENING_RANGE)
    assert out.empty and list(out.columns) == ["high", "low", "mid", "width"]
