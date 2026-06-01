"""The event-driven backtester and the strategy-facing Context."""
from __future__ import annotations

import math
from dataclasses import dataclass, field, replace
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from btengine.core.broker import SimulatedBroker
from btengine.core.events import OrderEvent, SignalEvent
from btengine.core.order import Order, OrderType, Side
from btengine.core.portfolio import Portfolio, Position


class Context:
    """Passed to `Strategy.on_bar`. Exposes only data up to the current bar."""

    def __init__(self, engine: "Backtester"):
        self._engine = engine
        self._signals: List[SignalEvent] = []
        self._orders: List[OrderEvent] = []

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

    def indicator(self, instrument: str, key: str, fn):
        """Value at the current bar of a *causal* indicator, computed once and cached.

        `fn(full_ohlcv_df)` is evaluated a single time per (instrument, key) over the
        instrument's whole series, then this returns only the row at the current bar
        — so the per-bar cost is O(1) instead of recomputing over history each bar
        (turning an O(n^2) backtest into O(n)). The indicator MUST be causal (value
        at row i depends only on rows <= i); all of `btengine.indicators` qualify.
        `key` distinguishes parameterizations, e.g. f"sma{period}".

        Returns a scalar if `fn` yields a Series, or the row (a Series) if it yields
        a DataFrame; NaN/NaN-row before any bar is available.
        """
        cache = self._engine._indicator_cache
        ck = (instrument, key)
        series = cache.get(ck)
        if series is None:
            series = fn(self._engine._data[instrument])
            cache[ck] = series
        count = self._engine._counts[instrument]
        if count <= 0:
            return float("nan") if series.ndim == 1 else pd.Series(np.nan, index=series.columns)
        return series.iloc[count - 1]

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

    # --- advanced orders: resting brackets, OCO, risk sizing ---------------
    def submit(self, order: Order) -> None:
        """Queue an arbitrary Order (e.g. GTC/OCO/reduce-only stop or limit)."""
        self._orders.append(OrderEvent(self.now, order))

    def enter(
        self,
        instrument: str,
        side: Side,
        units: float,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None,
        tag: Optional[str] = None,
    ) -> None:
        """Market entry plus optional GTC reduce-only stop/target bracket (OCO).

        The stop and target are placed on the opposite side and linked so that
        whichever fills first cancels the other.
        """
        if units <= 0:
            return
        self.submit(Order(instrument, side, units, OrderType.MARKET, tag=tag or "entry"))
        exit_side = Side.SELL if side is Side.BUY else Side.BUY
        group = f"{instrument}@{self.now.value}"
        if stop_loss is not None:
            self.submit(Order(instrument, exit_side, units, OrderType.STOP,
                              stop_price=stop_loss, tif="GTC", reduce_only=True,
                              oco_group=group, tag="stop"))
        if take_profit is not None:
            self.submit(Order(instrument, exit_side, units, OrderType.LIMIT,
                              limit_price=take_profit, tif="GTC", reduce_only=True,
                              oco_group=group, tag="tp"))

    def cancel_all(self, instrument: str) -> None:
        """Cancel all resting and not-yet-active orders for `instrument`."""
        self._engine.cancel_orders(instrument)
        self._orders = [oe for oe in self._orders if oe.order.instrument != instrument]

    def units_for_risk(
        self,
        instrument: str,
        stop_price: float,
        entry_price: Optional[float] = None,
        risk_pct: float = 0.01,
    ) -> float:
        """Position size (units) so that hitting `stop_price` loses ~`risk_pct` of equity.

        Uses the current price as the assumed entry if `entry_price` is omitted.
        """
        entry = entry_price if entry_price is not None else self.price(instrument)
        if entry is None:
            return 0.0
        per_unit = abs(entry - stop_price)
        if per_unit <= 0:
            return 0.0
        return risk_pct * self.equity / per_unit

    def drain_orders(self) -> List[OrderEvent]:
        orders, self._orders = self._orders, []
        return orders

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
        self._active_orders: List[OrderEvent] = []
        self._indicator_cache: Dict[tuple, object] = {}

    # --- data access used by Context --------------------------------------
    def history(self, instrument: str) -> pd.DataFrame:
        return self._data[instrument].iloc[: self._counts[instrument]]

    def record_values(self, timestamp: pd.Timestamp, values: Dict[str, float]) -> None:
        self._records.setdefault(timestamp, {}).update(values)

    def cancel_orders(self, instrument: str) -> None:
        """Remove all resting/active orders for `instrument`."""
        self._active_orders = [oe for oe in self._active_orders
                               if oe.order.instrument != instrument]

    def _try_fill(self, order_event: OrderEvent, bar: pd.Series, ts: pd.Timestamp) -> bool:
        """Attempt to fill one order against `bar`. Returns True if it filled.

        Honors reduce-only: such orders only close an existing opposite position
        and never flip it; their size is clamped to the open position.
        """
        order = order_event.order
        exec_units = order.units
        if order.reduce_only:
            pos = self.portfolio.units(order.instrument)
            increases = pos == 0 or (pos > 0) == (order.side is Side.BUY)
            if increases:
                return False  # nothing to reduce (flat or same direction)
            exec_units = min(order.units, abs(pos))

        exec_order = order if exec_units == order.units else replace(order, units=exec_units)
        fill = self.broker.execute(OrderEvent(order_event.timestamp, exec_order), bar, ts)
        if fill is None:
            return False
        self.portfolio.on_fill(fill)
        return True

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
        self._active_orders = []
        self._indicator_cache = {}

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

            # 1. Process active orders against this bar. Orders for instruments
            #    without a bar this timestamp keep waiting. Entries fill before
            #    reduce-only exits so a same-bar bracket sees the open position.
            waiting = [oe for oe in self._active_orders if oe.order.instrument not in bars_now]
            to_process = [oe for oe in self._active_orders if oe.order.instrument in bars_now]
            to_process.sort(key=lambda oe: oe.order.reduce_only)  # entries (False) first

            cancelled_groups = set()
            survivors: List[OrderEvent] = list(waiting)
            for order_event in to_process:
                order = order_event.order
                if order.oco_group and order.oco_group in cancelled_groups:
                    continue  # sibling already filled -> cancel this leg
                if self._try_fill(order_event, bars_now[order.instrument], ts):
                    if order.oco_group:
                        cancelled_groups.add(order.oco_group)
                    # filled -> not kept
                elif order.tif == "GTC":
                    survivors.append(order_event)  # rests until filled/cancelled
                # DAY orders that didn't fill are dropped (expired)

            # Drop any survivors whose OCO group was triggered this bar.
            self._active_orders = [
                oe for oe in survivors
                if not (oe.order.oco_group and oe.order.oco_group in cancelled_groups)
            ]

            # 2. Mark equity at the close (forward-filled for stale instruments).
            self.portfolio.mark(ts, self.last_close)

            # 3. Strategy reacts to data up to this bar's close.
            self.strategy.on_bar(ctx)

            # 4. Queue new orders (from signals and direct submissions), active next bar.
            for signal in ctx.drain_signals():
                order_event = self.portfolio.create_order(signal)
                if order_event is not None:
                    self._active_orders.append(order_event)
            self._active_orders.extend(ctx.drain_orders())

        self.strategy.on_finish(ctx)

        return BacktestResult(
            portfolio=self.portfolio,
            equity=self.portfolio.equity_series(),
            trades=self.portfolio.trades_frame(),
            bars=len(self.master_index),
            records=self._records_frame(),
        )
