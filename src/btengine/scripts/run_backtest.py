"""CLI: run a strategy over cached candles and print a performance report."""
from __future__ import annotations

import argparse
from typing import Dict, List, Optional

import pandas as pd

from btengine.analytics import compute_metrics, format_report, plot_equity
from btengine.core.broker import SimulatedBroker
from btengine.core.engine import Backtester
from btengine.data.loader import load_candles
from btengine.strategy.examples import REGISTRY


def _parse_instruments(value: str) -> List[str]:
    return [s.strip() for s in value.split(",") if s.strip()]


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Run a backtest over cached Oanda candles.")
    p.add_argument("--strategy", required=True, choices=sorted(REGISTRY), help="Strategy name")
    p.add_argument("--instruments", required=True, help="Comma-separated, e.g. EUR_USD,GBP_USD")
    p.add_argument("--granularity", default="H1")
    p.add_argument("--from", dest="start", default=None, help="ISO date/time (optional)")
    p.add_argument("--to", dest="end", default=None, help="ISO date/time (optional)")
    p.add_argument("--cash", type=float, default=100_000.0)
    p.add_argument("--units", type=float, default=10_000.0, help="Default order size in units")
    p.add_argument("--spread", type=float, default=0.0001, help="Bid/ask spread in price terms")
    p.add_argument("--slippage", type=float, default=0.0)
    p.add_argument("--commission-per-unit", type=float, default=0.0)
    p.add_argument("--fast", type=int, default=20)
    p.add_argument("--slow", type=int, default=50)
    p.add_argument("--plot", default=None, help="Path to save an equity-curve PNG")
    return p


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)

    data: Dict[str, pd.DataFrame] = {}
    for inst in _parse_instruments(args.instruments):
        df = load_candles(inst, args.granularity, start=args.start, end=args.end)
        if df.empty:
            print(f"WARNING: no cached data for {inst} [{args.granularity}]. "
                  f"Run bt-download first.")
            continue
        data[inst] = df

    if not data:
        print("No data loaded. Nothing to backtest.")
        return 1

    strategy_cls = REGISTRY[args.strategy]
    # Pass through known params; strategies ignore extras via **params.
    strategy = strategy_cls(fast=args.fast, slow=args.slow)

    broker = SimulatedBroker(
        spread=args.spread,
        slippage=args.slippage,
        commission_per_unit=args.commission_per_unit,
    )
    engine = Backtester(
        data=data,
        strategy=strategy,
        broker=broker,
        initial_cash=args.cash,
        default_units=args.units,
    )
    result = engine.run()

    metrics = compute_metrics(result.equity, result.trades, granularity=args.granularity)
    title = f"{args.strategy} | {', '.join(data)} | {args.granularity}"
    print(format_report(metrics, title=title))

    if args.plot:
        out = plot_equity(result.equity, args.plot, title=title)
        print(f"\nEquity curve saved to {out}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
