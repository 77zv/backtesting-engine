"""Thin wrapper over the Oanda v20 REST candles endpoint with pagination."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Iterable, List, Optional, Union

import pandas as pd

from btengine.config import Config, load_config
from btengine.data.models import OHLCV_COLUMNS, GRANULARITY_SECONDS, validate_granularity

# Oanda returns at most this many candles per request.
MAX_CANDLES_PER_REQUEST = 5000

DateLike = Union[str, datetime, pd.Timestamp]


def _to_utc(value: DateLike) -> datetime:
    """Coerce a date-like value to a timezone-aware UTC datetime."""
    ts = pd.Timestamp(value)
    if ts.tzinfo is None:
        ts = ts.tz_localize("UTC")
    else:
        ts = ts.tz_convert("UTC")
    return ts.to_pydatetime()


def _rfc3339(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000000000Z")


class OandaClient:
    """Fetches historical candles, transparently paginating past the 5000 limit."""

    def __init__(self, config: Optional[Config] = None, price: str = "M"):
        """price: 'M' (mid), 'B' (bid), or 'A' (ask)."""
        self.config = config or load_config()
        self.config.require_credentials()
        self.price = price
        # Imported lazily so the package imports without the dependency installed
        # (e.g. for offline unit tests that never touch the network).
        from oandapyV20 import API

        self._api = API(
            access_token=self.config.api_token,
            environment=self.config.environment,
        )

    def fetch_candles(
        self,
        instrument: str,
        granularity: str,
        start: DateLike,
        end: Optional[DateLike] = None,
    ) -> pd.DataFrame:
        """Return a UTC-indexed OHLCV DataFrame of *complete* candles in [start, end)."""
        from oandapyV20.endpoints.instruments import InstrumentsCandles

        validate_granularity(granularity)
        start_dt = _to_utc(start)
        end_dt = _to_utc(end) if end is not None else datetime.now(timezone.utc)
        window = timedelta(
            seconds=GRANULARITY_SECONDS[granularity] * MAX_CANDLES_PER_REQUEST
        )

        frames: List[pd.DataFrame] = []
        cursor = start_dt
        while cursor < end_dt:
            chunk_end = min(cursor + window, end_dt)
            params = {
                "granularity": granularity,
                "price": self.price,
                "from": _rfc3339(cursor),
                "to": _rfc3339(chunk_end),
            }
            request = InstrumentsCandles(instrument=instrument, params=params)
            response = self._api.request(request)
            frames.append(self._parse(response.get("candles", [])))
            cursor = chunk_end

        if not frames:
            return _empty_frame()

        df = pd.concat(frames)
        df = df[~df.index.duplicated(keep="last")].sort_index()
        # Defensive clip to the requested half-open range.
        return df.loc[(df.index >= pd.Timestamp(start_dt)) & (df.index < pd.Timestamp(end_dt))]

    def _parse(self, candles: Iterable[dict]) -> pd.DataFrame:
        key = {"M": "mid", "B": "bid", "A": "ask"}[self.price]
        rows = []
        index = []
        for c in candles:
            if not c.get("complete", False):
                continue
            ohlc = c[key]
            index.append(pd.Timestamp(c["time"]).tz_convert("UTC"))
            rows.append(
                [
                    float(ohlc["o"]),
                    float(ohlc["h"]),
                    float(ohlc["l"]),
                    float(ohlc["c"]),
                    float(c.get("volume", 0)),
                ]
            )
        if not rows:
            return _empty_frame()
        df = pd.DataFrame(rows, index=pd.DatetimeIndex(index, name="time"), columns=OHLCV_COLUMNS)
        return df


def _empty_frame() -> pd.DataFrame:
    return pd.DataFrame(
        columns=OHLCV_COLUMNS,
        index=pd.DatetimeIndex([], name="time", tz="UTC"),
    )
