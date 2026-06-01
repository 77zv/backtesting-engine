# btengine

An event-driven, multi-instrument backtesting engine for FX/CFD strategies, using
[Oanda](https://developer.oanda.com/rest-live-v20/introduction/) v20 candlestick data.

- **Event-driven** loop — bar-by-bar, no look-ahead bias.
- **Multi-instrument portfolio** with shared account equity.
- **Class-based strategies** against a small built-in indicator library.
- **Backtest only** — Oanda is used purely as a historical data source.

## Setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env   # then add your Oanda practice token
```

Get a free practice-account token at
<https://www.oanda.com/demo-account/tpa/personal_token>.

## Usage

Download and cache candles:

```bash
bt-download --instruments EUR_USD,GBP_USD --granularity H1 --from 2023-01-01 --to 2024-01-01
```

Run a backtest on cached data:

```bash
bt-run --strategy sma_crossover --instruments EUR_USD,GBP_USD --granularity H1
```

## Writing a strategy

Subclass `Strategy` and implement `on_bar`:

```python
from btengine.strategy.base import Strategy
from btengine.indicators import sma

class SmaCrossover(Strategy):
    def on_bar(self, ctx):
        for inst in ctx.instruments:
            close = ctx.history(inst)["close"]
            if len(close) < 50:
                continue
            fast, slow = sma(close, 20), sma(close, 50)
            if fast.iloc[-1] > slow.iloc[-1] and not ctx.position(inst):
                ctx.buy(inst)
            elif fast.iloc[-1] < slow.iloc[-1] and ctx.position(inst):
                ctx.close(inst)
```

## Testing

```bash
pytest
```

The engine test suite runs fully offline against synthetic data.

## Architecture

```
MarketEvent -> Strategy -> SignalEvent -> Portfolio (sizing) -> OrderEvent
            -> SimulatedBroker (spread/slippage/commission) -> FillEvent -> Portfolio
```

See `PLAN.md` for the full design.
