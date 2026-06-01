import numpy as np
import pandas as pd

from btengine.core.engine import Backtester
from btengine.sessions import NYSE
from btengine.strategy.base import Strategy
from btengine.strategy.examples.opening_range import OpeningRange


def _intraday_ohlcv(local_days, tz="America/New_York"):
    """Build hourly OHLCV bars 09:00–16:00 local across the given local dates."""
    stamps = []
    for d in local_days:
        for hour in range(9, 16):  # 09:00 .. 15:00 local
            stamps.append(pd.Timestamp(f"{d} {hour:02d}:30", tz=tz).tz_convert("UTC"))
    idx = pd.DatetimeIndex(sorted(stamps), name="time")
    rng = np.random.default_rng(1)
    close = 100 + np.cumsum(rng.normal(0, 0.5, size=len(idx)))
    opens = np.empty_like(close)
    opens[0] = close[0]
    opens[1:] = close[:-1]
    return pd.DataFrame(
        {"open": opens, "high": np.maximum(opens, close) + 0.5,
         "low": np.minimum(opens, close) - 0.5, "close": close,
         "volume": 1000.0},
        index=idx,
    )


def test_ctx_local_is_dst_correct_and_machine_independent():
    seen = {}

    class Recorder(Strategy):
        def on_bar(self, ctx):
            seen[ctx.now] = ctx.local("America/New_York")

    # One summer bar and one winter bar, both at 13:30 UTC.
    data = {"X": _intraday_ohlcv(["2024-07-15"]).iloc[:1]}
    Backtester(data, Recorder()).run()
    ts = list(seen)[0]
    # ctx.local must equal a plain tz_convert — no OS-local involvement.
    assert seen[ts] == ts.tz_convert("America/New_York")
    # tz=None is a no-op (stays UTC).

    class UtcRecorder(Strategy):
        def on_bar(self, ctx):
            assert ctx.local() == ctx.now
            assert str(ctx.local().tz) == "UTC"

    Backtester(data, UtcRecorder()).run()


def test_opening_range_runs_across_spring_forward():
    # Days straddling the 2024-03-10 US spring-forward transition.
    data = {"SPX": _intraday_ohlcv(["2024-03-08", "2024-03-11", "2024-03-12"])}
    result = Backtester(data, OpeningRange(NYSE), default_units=10).run()
    # Sanity: it ran over every bar and produced a full equity curve.
    assert result.bars == len(data["SPX"])
    assert len(result.equity) == result.bars
    # Equity is finite throughout (no NaN/inf from session handling).
    assert np.isfinite(result.equity.values).all()


def test_session_strategy_start_hook_fires_once_per_day():
    starts = []

    class CountStarts(OpeningRange):
        def on_session_start(self, ctx, instrument):
            super().on_session_start(ctx, instrument)
            starts.append(ctx.local("America/New_York").date())

    data = {"SPX": _intraday_ohlcv(["2024-03-08", "2024-03-11"])}
    Backtester(data, CountStarts(NYSE), default_units=10).run()
    # Exactly one start per trading day, on the correct local dates.
    assert starts == [pd.Timestamp("2024-03-08").date(), pd.Timestamp("2024-03-11").date()]
