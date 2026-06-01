"""CLI: download and cache Oanda candles for one or more instruments."""
from __future__ import annotations

import argparse
from typing import List, Optional

from btengine.data.loader import CandleCache


def _parse_instruments(value: str) -> List[str]:
    return [s.strip() for s in value.split(",") if s.strip()]


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Download Oanda candles into the local cache.")
    p.add_argument("--instruments", required=True, help="Comma-separated, e.g. EUR_USD,GBP_USD")
    p.add_argument("--granularity", default="H1", help="e.g. M1, M5, M15, H1, H4, D (default H1)")
    p.add_argument("--from", dest="start", required=True, help="ISO date/time, e.g. 2023-01-01")
    p.add_argument("--to", dest="end", default=None, help="ISO date/time (default: now)")
    p.add_argument("--force", action="store_true", help="Overwrite cache instead of merging")
    return p


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    cache = CandleCache()
    for instrument in _parse_instruments(args.instruments):
        df = cache.download(
            instrument,
            args.granularity,
            start=args.start,
            end=args.end,
            force=args.force,
        )
        span = f"{df.index.min()} .. {df.index.max()}" if len(df) else "(empty)"
        print(f"{instrument} [{args.granularity}]: {len(df)} candles cached, {span}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
