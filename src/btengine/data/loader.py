"""Parquet candle cache and multi-instrument timestamp alignment."""
from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd

from btengine.config import Config, load_config
from btengine.data.models import OHLCV_COLUMNS, validate_granularity
from btengine.data.oanda_client import DateLike, OandaClient, _to_utc


class CandleCache:
    """Reads/writes per-(instrument, granularity) OHLCV parquet files.

    Fetches missing data from Oanda on demand and caches the union locally.
    """

    def __init__(self, config: Optional[Config] = None, client: Optional[OandaClient] = None):
        self.config = config or load_config()
        self._client = client  # created lazily to avoid requiring credentials offline

    def _path(self, instrument: str, granularity: str) -> Path:
        d = self.config.data_dir / granularity
        return d / f"{instrument}.parquet"

    def _ensure_client(self) -> OandaClient:
        if self._client is None:
            self._client = OandaClient(self.config)
        return self._client

    def read(self, instrument: str, granularity: str) -> pd.DataFrame:
        path = self._path(instrument, granularity)
        if not path.exists():
            return pd.DataFrame(
                columns=OHLCV_COLUMNS,
                index=pd.DatetimeIndex([], name="time", tz="UTC"),
            )
        df = pd.read_parquet(path)
        if df.index.tz is None:
            df.index = df.index.tz_localize("UTC")
        return df.sort_index()

    def write(self, instrument: str, granularity: str, df: pd.DataFrame) -> None:
        path = self._path(instrument, granularity)
        path.parent.mkdir(parents=True, exist_ok=True)
        df.sort_index().to_parquet(path)

    def download(
        self,
        instrument: str,
        granularity: str,
        start: DateLike,
        end: Optional[DateLike] = None,
        force: bool = False,
    ) -> pd.DataFrame:
        """Fetch [start, end) from Oanda, merge into the cache, and return the merged frame."""
        validate_granularity(granularity)
        client = self._ensure_client()
        fetched = client.fetch_candles(instrument, granularity, start, end)

        if force:
            merged = fetched
        else:
            existing = self.read(instrument, granularity)
            # Skip empty frames so concat doesn't warn about all-NA dtype inference.
            frames = [f for f in (existing, fetched) if not f.empty]
            merged = pd.concat(frames) if frames else fetched
            merged = merged[~merged.index.duplicated(keep="last")].sort_index()

        self.write(instrument, granularity, merged)
        return merged


def load_candles(
    instrument: str,
    granularity: str,
    start: Optional[DateLike] = None,
    end: Optional[DateLike] = None,
    cache: Optional[CandleCache] = None,
) -> pd.DataFrame:
    """Load cached candles for one instrument, optionally sliced to [start, end)."""
    cache = cache or CandleCache()
    df = cache.read(instrument, granularity)
    if start is not None:
        df = df.loc[df.index >= pd.Timestamp(_to_utc(start))]
    if end is not None:
        df = df.loc[df.index < pd.Timestamp(_to_utc(end))]
    return df


def align_instruments(frames: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Merge per-instrument OHLCV frames onto a single sorted UTC timestamp index.

    Returns a DataFrame with a column MultiIndex (instrument, field). Timestamps
    present for any instrument appear once; missing fields are NaN. The engine
    iterates this index and skips instruments whose bar is NaN at a timestamp.
    """
    if not frames:
        raise ValueError("align_instruments requires at least one instrument frame")

    pieces: List[pd.DataFrame] = []
    for instrument, df in frames.items():
        piece = df.copy()
        piece.columns = pd.MultiIndex.from_product([[instrument], piece.columns])
        pieces.append(piece)

    combined = pd.concat(pieces, axis=1).sort_index()
    combined.columns.names = ["instrument", "field"]
    return combined
