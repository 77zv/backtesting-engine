# Plan: Event-Driven Backtesting Engine (Oanda candles)

## Context

Greenfield project in an empty directory (`/Users/ali1/WebstormProjects/backtesting-engine`, Python 3.9.6 available, not a git repo). The goal is a Python backtesting engine that:

- Pulls **historical candlestick data** from the **Oanda v20 REST API** (backtest-only; Oanda is used purely as a data source).
- Runs strategies through an **event-driven loop** (bar-by-bar, no look-ahead bias).
- Supports a **multi-instrument portfolio** with shared account equity.
- Lets users write **class-based strategies** against a small built-in indicator library.

Event-driven + class-based was chosen so the same `Strategy` interface could later be wired to a live Oanda execution adapter without rewriting strategy code.

## Architecture overview

A central **event queue** drives the simulation. For each timestamp the engine emits a `MarketEvent`; the strategy reacts with `SignalEvent`s; the portfolio sizes them into `OrderEvent`s; the simulated broker fills them into `FillEvent`s; the portfolio updates positions/equity. This keeps data, logic, sizing, and execution decoupled.

```
backtesting-engine/
  pyproject.toml          # deps + package metadata
  .env.example            # OANDA_API_TOKEN, OANDA_ACCOUNT_ID, OANDA_ENV=practice
  README.md
  src/btengine/
    config.py             # load .env, environment (practice/live host), data dir
    data/
      models.py           # Candle dataclass / typed columns
      oanda_client.py     # wraps oandapyV20; fetch candles w/ pagination
      loader.py           # disk cache (parquet), align multi-instrument bars
    indicators/__init__.py # SMA, EMA, RSI, ATR, rolling std, etc. (vectorized helpers)
    core/
      events.py           # MarketEvent, SignalEvent, OrderEvent, FillEvent
      order.py            # Order, OrderType (MARKET/LIMIT/STOP), Side enums
      broker.py           # SimulatedBroker: spread, slippage, commission, fills
      portfolio.py        # positions, cash, equity curve, sizing, P&L
      engine.py           # Backtester: the event loop + bar synchronization
    strategy/
      base.py             # Strategy ABC: on_bar(ctx), helpers to emit signals
      examples/sma_crossover.py
  scripts/
    download_data.py      # CLI: cache candles for instrument(s)/granularity/range
    run_backtest.py       # CLI: wire data + strategy + portfolio, print report
  analytics/  (src/btengine/analytics/)
    metrics.py            # Sharpe, Sortino, max drawdown, CAGR, win rate, exposure
    report.py             # text summary + matplotlib equity curve
  tests/
    test_indicators.py  test_portfolio.py  test_broker.py  test_engine.py
```

## Implementation phases

### Phase 1 — Project scaffolding & data layer
- `pyproject.toml` with deps: `oandapyV20`, `pandas`, `numpy`, `python-dotenv`, `pyarrow` (parquet cache), `matplotlib`, and dev `pytest`. Target Python 3.9 (avoid 3.10+ typing syntax like `X | Y`; use `Optional`, `List`).
- `config.py`: read `OANDA_API_TOKEN`, `OANDA_ACCOUNT_ID`, `OANDA_ENV` (`practice`/`live`) from `.env`; resolve API host; define a local `data/` cache dir.
- `data/oanda_client.py`: wrap `oandapyV20.endpoints.instruments.InstrumentsCandles` (`/v3/instruments/{instrument}/candles`). Handle the **5000-candle/request limit** by paginating with `from`/`to` time windows; support granularities (`M1, M5, M15, H1, H4, D`, etc.); request `mid` (and optionally `bid`/`ask`) prices; return a clean OHLCV `DataFrame` indexed by UTC time, keeping only `complete` candles.
- `data/loader.py`: cache each (instrument, granularity) to parquet keyed by date range; on load, **align multiple instruments onto a common sorted timestamp index** (outer-join, forward-filled per-instrument view) so the engine can iterate timestamps across the portfolio.
- `scripts/download_data.py`: CLI to pre-fetch and cache data.

### Phase 2 — Indicators
- `indicators/__init__.py`: pure pandas/numpy functions (`sma`, `ema`, `rsi`, `atr`, `rolling_std`, `crossover`). Strategies call these on the rolling history window the engine exposes — computed incrementally to avoid look-ahead.

### Phase 3 — Core event engine
- `core/events.py` + `core/order.py`: event dataclasses and order/side/type enums.
- `core/portfolio.py`: track cash, per-instrument positions, mark-to-market equity each bar, realized/unrealized P&L, and a position-sizing policy (start with fixed-fractional / fixed-units). Records the **equity curve** and trade log.
- `core/broker.py` `SimulatedBroker`: convert `OrderEvent`→`FillEvent` using next-bar open (configurable), apply **spread, slippage, and commission**; support market/limit/stop fills checked against bar high/low.
- `core/engine.py` `Backtester`: own the event queue; iterate the aligned timestamp index; for each timestamp push `MarketEvent`s, call `strategy.on_bar(ctx)`, drain signal→order→fill, then have the portfolio mark equity. Guard against look-ahead (strategy only sees data up to current bar).

### Phase 4 — Strategy API
- `strategy/base.py` `Strategy` ABC: lifecycle `on_start`, `on_bar(ctx)`, `on_finish`. `ctx` exposes current/historical bars per instrument, current positions/equity, and helpers `buy/sell/close(instrument, ...)` that emit `SignalEvent`s. Indicators are called against `ctx` history.
- `strategy/examples/sma_crossover.py`: reference multi-instrument SMA-crossover strategy.

### Phase 5 — Analytics & reporting
- `analytics/metrics.py`: Sharpe, Sortino, max drawdown, CAGR, total return, win rate, avg win/loss, exposure, trade count.
- `analytics/report.py`: text summary + equity-curve / drawdown plot (matplotlib, save to file).
- `scripts/run_backtest.py`: CLI tying data + strategy + portfolio + broker together and printing the report.

### Phase 6 — Tests
- `test_indicators.py`: indicator values vs hand-computed expectations.
- `test_portfolio.py`: position accounting, equity, P&L on scripted fills.
- `test_broker.py`: fill logic for market/limit/stop incl. commission/slippage.
- `test_engine.py`: end-to-end run on a tiny synthetic dataset (no network) producing a deterministic equity curve; verify no look-ahead.

## Key design decisions
- **Oanda specifics**: v20 REST; `oandapyV20` client; practice host by default; paginate the 5000-candle limit; use only `complete` candles; store mid OHLCV. Secrets via `.env` (gitignored), `.env.example` committed.
- **No look-ahead**: orders fill on the *next* bar; strategies only ever see history up to the current bar.
- **Portfolio sync**: a single merged UTC timestamp index across all instruments drives the loop.
- **Extensibility hook**: the `Backtester` consumes an abstract broker/data feed, so a live Oanda adapter could be dropped in later without touching strategy code (out of scope now).

## Verification
1. `pip install -e .` (or `pip install -e ".[dev]"`).
2. Unit + integration tests offline: `pytest` (engine test uses synthetic data, no network).
3. Data fetch (requires a free Oanda practice token in `.env`):
   `python scripts/download_data.py --instruments EUR_USD,GBP_USD --granularity H1 --from 2023-01-01 --to 2024-01-01`
   → confirm parquet cache files written with expected row counts.
4. End-to-end backtest on cached data:
   `python scripts/run_backtest.py --strategy sma_crossover --instruments EUR_USD,GBP_USD --granularity H1`
   → prints metrics summary and saves an equity-curve plot; sanity-check final equity, drawdown, and trade count.

## Open follow-ups (not in this build)
- Live/paper Oanda execution adapter, parameter-sweep/optimization harness, walk-forward analysis, bid/ask spread sourced from real candles, more order types.
