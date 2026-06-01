from datetime import date, time

import pandas as pd
import pytest

from btengine.sessions import NYSE, TOKYO, Session


def _utc(s):
    return pd.Timestamp(s, tz="UTC")


def _from_local(s, tz="America/New_York"):
    """A UTC timestamp for a given New York local wall-clock time."""
    return pd.Timestamp(s, tz=tz).tz_convert("UTC")


# --- is_open: DST is assessed per-instant, for the candle's own date --------
def test_is_open_uses_each_instants_dst_offset():
    # 09:30 New York is 13:30 UTC in summer (EDT) and 14:30 UTC in winter (EST).
    assert NYSE.is_open(_utc("2024-07-15 13:30")) is True   # EDT open
    assert NYSE.is_open(_utc("2024-01-15 14:30")) is True   # EST open

    # The SAME UTC time gives different answers across the year:
    # 14:30 UTC is 09:30 (open) in winter but 10:30 (in-session) in summer.
    assert NYSE.is_open(_utc("2024-07-15 13:30")) is True
    # 13:30 UTC in winter is only 08:30 NY -> before the open.
    assert NYSE.is_open(_utc("2024-01-15 13:30")) is False


def test_is_open_excludes_weekends_and_close_boundary():
    # 2024-07-13 is a Saturday.
    assert NYSE.is_open(_from_local("2024-07-13 11:00")) is False
    # Close is exclusive: 16:00 local is not "in session".
    assert NYSE.is_open(_from_local("2024-07-15 16:00")) is False
    assert NYSE.is_open(_from_local("2024-07-15 15:59")) is True


def test_is_open_respects_holidays():
    july4 = Session("America/New_York", time(9, 30), time(16, 0),
                    holidays=frozenset({date(2024, 7, 4)}))
    assert july4.is_open(_from_local("2024-07-04 11:00")) is False
    assert july4.is_open(_from_local("2024-07-05 11:00")) is True


def test_minutes_since_open():
    assert NYSE.minutes_since_open(_from_local("2024-07-15 09:30")) == pytest.approx(0.0)
    assert NYSE.minutes_since_open(_from_local("2024-07-15 10:30")) == pytest.approx(60.0)
    assert NYSE.minutes_since_open(_from_local("2024-07-15 08:00")) is None


def test_tokyo_no_dst():
    # Japan does not observe DST: 09:00 JST is 00:00 UTC year-round.
    assert TOKYO.is_open(_utc("2024-07-15 00:00")) is True
    assert TOKYO.is_open(_utc("2024-01-15 00:00")) is True


# --- is_start: derived from history, fires once per session day -------------
def _session_index(day_local_times, tz="America/New_York"):
    return pd.DatetimeIndex([_from_local(t, tz) for t in day_local_times], name="time")


def _starts_over(index):
    """Replay growing history and collect which bars report is_start."""
    return [NYSE.is_start(index[: i + 1]) for i in range(len(index))]


def test_is_start_fires_once_at_first_in_session_bar():
    idx = _session_index([
        "2024-07-15 09:00",  # pre-market -> not in session
        "2024-07-15 09:30",  # open -> START
        "2024-07-15 10:00",  # in session
        "2024-07-15 11:00",  # in session
    ])
    assert _starts_over(idx) == [False, True, False, False]


def test_is_start_across_spring_forward():
    # US springs forward on 2024-03-10. Fri 03-08 is EST, Mon 03-11 is EDT.
    idx = _session_index([
        "2024-03-08 09:30", "2024-03-08 10:00",   # Friday, EST
        "2024-03-11 09:30", "2024-03-11 10:00",   # Monday, EDT (post-transition)
    ])
    assert _starts_over(idx) == [True, False, True, False]
    # The two opens are the SAME local time but DIFFERENT UTC instants.
    assert idx[0] == _utc("2024-03-08 14:30")   # 09:30 EST = 14:30 UTC
    assert idx[2] == _utc("2024-03-11 13:30")   # 09:30 EDT = 13:30 UTC


def test_is_start_across_fall_back():
    # US falls back on 2024-11-03. Fri 11-01 is EDT, Mon 11-04 is EST.
    idx = _session_index([
        "2024-11-01 09:30", "2024-11-01 10:00",   # Friday, EDT
        "2024-11-04 09:30", "2024-11-04 10:00",   # Monday, EST
    ])
    assert _starts_over(idx) == [True, False, True, False]
    assert idx[0] == _utc("2024-11-01 13:30")   # 09:30 EDT = 13:30 UTC
    assert idx[2] == _utc("2024-11-04 14:30")   # 09:30 EST = 14:30 UTC
