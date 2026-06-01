"""The event-driven backtester and the strategy-facing Context."""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from btengine.core.broker import SimulatedBroker
from btengine.core.events import OrderEvent, SignalEvent
from btengine.core.portfolio import Portfolio, Position


class Context:
    """Passed to `Strategy.on_bar`. Exposes only data up to the current bar."""

    def __init__(self, engine: "Backtester"):
        self._engine = engine
        self._signals: List[SignalEvent] = []

    # --- time & data (causal: never includes future bars) ------------------
    @property
    def now(self) -> pd.Timestamp:
        return self._engine.current_time

    @property
    def instruments(self) -> List[str]:
        return self._engine.instruments

    def local(self, tz: Optional[str] = None) -> pd.Timestamp:
        """The current time converted to an IANA timezone (DST-correct per instant).

        `tz=None` returns the UTC timestamp unchanged. The host machine's local
        timezone is never consulted, so backtests stay reproducible across machines.
        Pass an explicit zone (e.g. "America/New_York") for session-relative logic.
        """
        return self.now if tz is None else self.now.tz_convert(tz)

    def history(self, instrument: str) -> pd.DataFrame:
        """OHLCV for `instrument` from the start up to and including the current bar."""
        return self._engine.history(instrument)

    def bar(self, instrument: str) -> Optional[pd.Series]:
        """The most recent bar for `instrument` at/at-or-before now, or None."""
        hist = self.history(instrument)
        return hist.iloc[-1] if len(hist) else None

    def price(self, instrument: str) -> Optional[float]:
        bar = self.bar(instrument)
        return None if bar is None else float(bar["close"])

    # --- account state -----------------------------------------------------
    @property
    def cash(self) -> float:
        return self._engine.portfolio.cash

    @property
    def equity(self) -> float:
        return self._engine.portfolio.equity(self._engine.last_close)

    def position(self, instrument: str) -> Position:
        return self._engine.portfolio.position(instrument)

    def units(self, instrument: str) -> float:
        return self._engine.portfolio.units(instrument)

    # --- order helpers (emit signals; filled next bar) ---------------------
    def signal(self, instrument: str, units: float) -> None:
        """Queue a signed unit delta (positive buys, negative sells)."""
        if units:
            self._signals.append(SignalEvent(self.now, instrument, float(units)))

    def default_size(self, instrument: str) -> float:
        """The engine's default order size (units) for `instrument`."""
        return self._engine.size_units(instrument)

    def buy(self, instrument: str, units: Optional[float] = None) -> None:
        self.signal(instrument, abs(units) if units is not None else self.default_size(instrument))

    def sell(self, instrument: str, units: Optional[float] = None) -> None:
        self.signal(instrument, -(abs(units) if units is not None else self.default_size(instrument)))

    def close(self, instrument: str) -> None:
        """Flatten the current position in `instrument`."""
        self.signal(instrument, -self.units(instrument))

    def order_target_units(self, instrument: str, target: float) -> None:
        """Trade the delta needed to reach an absolute signed position of `target`."""
        self.signal(instrument, target - self.units(instrument))

    def record(self, instrument: Optional[str] = None, **values: float) -> None:
        """Record named series for the current bar (e.g. indicator values).

        Captured into `BacktestResult.records` for plotting. If `instrument` is
        given, keys are namespaced as "<instrument>.<name>" so the dashboard can
        overlay them on that instrument's price panel.
        """
        if not values:
            return
        prefix = f"{instrument}." if instrument else ""
        self._engine.record_values(self.now, {f"{prefix}{k}": v for k, v in values.items()})

    def drain_signals(self) -> List[SignalEvent]:
        signals, self._signals = self._signals, []
        return signals


@dataclass
class BacktestResult:
    portfolio: Portfolio
    equity: pd.Series
    trades: pd.DataFrame
    bars: int
    records: pd.DataFrame = field(default_factory=pd.DataFrame)


class Backtester:
    """Drives the event loop over an aligned set of per-instrument OHLCV frames."""

    def __init__(
        self,
        data: Dict[str, pd.DataFrame],
        strategy,
        broker: Optional[SimulatedBroker] = None,
        initial_cash: float = 100_000.0,
        default_units: float = 10_000.0,
        size_fraction: Optional[float] = None,
    ):
        """
        data: {instrument: OHLCV DataFrame indexed by UTC timestamp}.
        size_fraction: if set, default order size = (equity * fraction) / price,
            rounded down; otherwise `default_units` is used.
        """
        if not data:
            raise ValueError("Backtester requires at least one instrument")
        self.instruments = list(data.keys())
        self.strategy = strategy
        self.broker = broker or SimulatedBroker()
        self.portfolio = Portfolio(initial_cash=initial_cash)
        self.default_units = default_units
        self.size_fraction = size_fraction

        # Per-instrument frames + int64 timestamp arrays for fast causal slicing.
        self._data: Dict[str, pd.DataFrame] = {}
        self._ts: Dict[str, np.ndarray] = {}
        all_ts: List[pd.DatetimeIndex] = []
        for inst, df in data.items():
            df = df.sort_index()
            self._data[inst] = df
            self._ts[inst] = df.index.values.astype("datetime64[ns]").astype("int64")
            all_ts.append(df.index)

        # Master timeline: the sorted union of every instrument's timestamps.
        master = all_ts[0]
        for idx in all_ts[1:]:
            master = master.union(idx)
        self.master_index = master

        self.current_time: Optional[pd.Timestamp] = None
        self._cursor = 0  # number of bars visible for each instrument at current_time
        self._counts: Dict[str, int] = {inst: 0 for inst in self.instruments}
        self.last_close: Dict[str, float] = {}
        self._records: Dict[pd.Timestamp, Dict[str, float]] = {}

    # --- data access used by Context --------------------------------------
    def history(self, instrument: str) -> pd.DataFrame:
        return self._data[instrument].iloc[: self._counts[instrument]]

    def record_values(self, timestamp: pd.Timestamp, values: Dict[str, float]) -> None:
        self._records.setdefault(timestamp, {}).update(values)

    def _records_frame(self) -> pd.DataFrame:
        if not self._records:
            return pd.DataFrame()
        df = pd.DataFrame.from_dict(self._records, orient="index").sort_index()
        df.index.name = "time"
        return df

    def size_units(self, instrument: str) -> float:
        if self.size_fraction is None:
            return self.default_units
        price = self.last_close.get(instrument)
        if not price:
            return 0.0
        return float(math.floor((self.portfolio.equity(self.last_close) * self.size_fraction) / price))

    # --- main loop ---------------------------------------------------------
    def run(self) -> BacktestResult:
        ctx = Context(self)
        pending: List[OrderEvent] = []

        self.strategy.bind(ctx)
        self.strategy.on_start(ctx)

        for ts in self.master_index:
            self.current_time = ts
            ts_int = ts.value

            # Which instruments print a new bar at this timestamp?
            bars_now: Dict[str, pd.Series] = {}
            for inst in self.instruments:
                count = int(np.searchsorted(self._ts[inst], ts_int, side="right"))
                self._counts[inst] = count
                if count > 0 and self._ts[inst][count - 1] == ts_int:
                    bar = self._data[inst].iloc[count - 1]
                    bars_now[inst] = bar
                    self.last_close[inst] = float(bar["close"])

            # 1. Execute orders queued on the previous bar, at this bar's open.
            still_pending: List[OrderEvent] = []
            for order_event in pending:
                inst = order_event.order.instrument
                if inst in bars_now:
                    fill = self.broker.execute(order_event, bars_now[inst], ts)
                    if fill is not None:
                        self.portfolio.on_fill(fill)
                    # MARKET fills always; LIMIT/STOP that miss are dropped (day order).
                else:
                    # No bar for this instrument yet; keep waiting.
                    still_pending.append(order_event)
            pending = still_pending

            # 2. Mark equity at the close (forward-filled for stale instruments).
            self.portfolio.mark(ts, self.last_close)

            # 3. Strategy reacts to data up to this bar's close.
            self.strategy.on_bar(ctx)

            # 4. Convert signals into orders, active on the next bar.
            for signal in ctx.drain_signals():
                order_event = self.portfolio.create_order(signal)
                if order_event is not None:
                    pending.append(order_event)

        self.strategy.on_finish(ctx)

        return BacktestResult(
            portfolio=self.portfolio,
            equity=self.portfolio.equity_series(),
            trades=self.portfolio.trades_frame(),
            bars=len(self.master_index),
            records=self._records_frame(),
        )
