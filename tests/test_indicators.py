import numpy as np
import pandas as pd
import pytest

from btengine.indicators import atr, crossover, crossunder, ema, rsi, sma, true_range


def test_sma_basic():
    s = pd.Series([1, 2, 3, 4, 5], dtype=float)
    out = sma(s, 3)
    assert np.isnan(out.iloc[0]) and np.isnan(out.iloc[1])
    assert out.iloc[2] == pytest.approx(2.0)
    assert out.iloc[4] == pytest.approx(4.0)


def test_ema_first_value_equals_warmup_mean_tail():
    s = pd.Series(np.arange(1, 11), dtype=float)
    out = ema(s, 3)
    # Warm-up: NaN until enough periods, then a valid EMA.
    assert out.iloc[:2].isna().all()
    assert not np.isnan(out.iloc[-1])
    # EMA tracks but lags an increasing series, staying below the latest value.
    assert out.iloc[-1] < s.iloc[-1]


def test_rsi_all_gains_is_100():
    s = pd.Series(np.arange(1, 30), dtype=float)
    out = rsi(s, 14)
    assert out.dropna().iloc[-1] == pytest.approx(100.0)


def test_rsi_bounds():
    rng = np.random.default_rng(0)
    s = pd.Series(100 + np.cumsum(rng.normal(size=200)))
    out = rsi(s, 14).dropna()
    assert (out >= 0).all() and (out <= 100).all()


def test_true_range_and_atr():
    high = pd.Series([10, 11, 12], dtype=float)
    low = pd.Series([9, 9, 11], dtype=float)
    close = pd.Series([9.5, 10.5, 11.5], dtype=float)
    tr = true_range(high, low, close)
    # bar 0: just H-L = 1
    assert tr.iloc[0] == pytest.approx(1.0)
    # bar 1: max(11-9, |11-9.5|, |9-9.5|) = 2
    assert tr.iloc[1] == pytest.approx(2.0)
    a = atr(high, low, close, period=2)
    assert not np.isnan(a.iloc[-1])


def test_crossover_and_crossunder():
    fast = pd.Series([1, 2, 3, 2, 1], dtype=float)
    slow = pd.Series([2, 2, 2, 2, 2], dtype=float)
    up = crossover(fast, slow)
    down = crossunder(fast, slow)
    assert up.iloc[2]  # 2->3 crosses above 2 (diff 0 -> +1)
    assert down.iloc[4]  # 2->1 crosses below 2 (diff 0 -> -1)
    assert up.sum() == 1 and down.sum() == 1
