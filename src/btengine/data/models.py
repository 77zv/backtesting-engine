"""Shared data definitions for candle data."""
from __future__ import annotations

# Canonical column order for OHLCV DataFrames (indexed separately by UTC timestamp).
OHLCV_COLUMNS = ["open", "high", "low", "close", "volume"]

# Approximate number of seconds in each supported Oanda granularity.
# Used to size pagination windows for the 5000-candle/request limit.
GRANULARITY_SECONDS = {
    "S5": 5,
    "S10": 10,
    "S15": 15,
    "S30": 30,
    "M1": 60,
    "M2": 120,
    "M4": 240,
    "M5": 300,
    "M10": 600,
    "M15": 900,
    "M30": 1800,
    "H1": 3600,
    "H2": 7200,
    "H3": 10800,
    "H4": 14400,
    "H6": 21600,
    "H8": 28800,
    "H12": 43200,
    "D": 86400,
    "W": 604800,
    # Monthly is irregular; approximate with 30 days for window sizing only.
    "M": 2592000,
}


def validate_granularity(granularity: str) -> str:
    if granularity not in GRANULARITY_SECONDS:
        raise ValueError(
            f"Unsupported granularity {granularity!r}. "
            f"Supported: {sorted(GRANULARITY_SECONDS)}"
        )
    return granularity
