import pandas as pd

from btengine.core.engine import Backtester
from btengine.strategy.examples import REGISTRY, SessionBreakout


def _intraday(local_days, tz="America/New_York", freq_min=15):
    stamps = []
    for d in local_days:
        day = pd.date_range(f"{d} 00:00", f"{d} 23:45", freq=f"{freq_min}min", tz=tz)
        stamps.extend(day)
    idx = pd.DatetimeIndex(sorted(stamps)).tz_convert("UTC")
    idx.name = "time"
    n = len(idx)
    base = 5000 + pd.Series(range(n)).mul(0.1).values
    return pd.DataFrame(
        {"open": base, "high": base + 2, "low": base - 2, "close": base + 1, "volume": 1000.0},
        index=idx,
    )


def test_session_breakout_registered():
    assert REGISTRY["session_breakout"] is SessionBreakout


def test_session_breakout_runs_and_records_levels():
    data = {"SPX500_USD": _intraday(["2024-05-13", "2024-05-14", "2024-05-15"])}
    result = Backtester(data, SessionBreakout(), default_units=1).run()
    recs = result.records
    # All four session levels are surfaced for the dashboard overlay.
    for col in ("SPX500_USD.or_high", "SPX500_USD.or_low",
                "SPX500_USD.asia_high", "SPX500_USD.asia_low"):
        assert col in recs.columns
    # Opening-range levels become defined once the 09:30-10:00 window is seen.
    assert recs["SPX500_USD.or_high"].notna().any()
    assert result.bars == len(data["SPX500_USD"])
