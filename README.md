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

## Visualizing results

Add `--plot` for a static equity/drawdown PNG, or `--dashboard` for a
self-contained interactive HTML report (candlesticks + buy/sell markers +
indicator overlays + equity, drawdown, and trade-analytics histograms):

```bash
bt-run --strategy sma_crossover --instruments EUR_USD --granularity H1 \
       --plot equity.png --dashboard dashboard.html
```

Open `dashboard.html` in any browser — Plotly.js is embedded, so it works
offline. Strategies surface indicators on the price chart by calling
`ctx.record(instrument, name=value)` (see `sma_crossover`).

## Built-in strategies

| `--strategy` | Description |
|---|---|
| `sma_crossover` | Fast/slow SMA crossover (records the SMAs for the chart). |
| `opening_range` | Opening-range breakout via the `SessionStrategy` base. |
| `session_breakout` | Breakout of the 09:30–10:00 opening range; overlays OR + Asia levels. |
| `asia_reversion` | Fades the London break of the Asia range back to the 50% level, with a 1%-risk stop/target bracket; flat by 16:00 ET. |

## Bracket orders & risk sizing

Strategies can place resting **stop-loss / take-profit brackets** (GTC, OCO,
reduce-only) and size by risk:

```python
units = ctx.units_for_risk(inst, stop_price=stop, risk_pct=0.01)  # risk 1% of equity
ctx.enter(inst, Side.SELL, units, stop_loss=stop, take_profit=target)  # OCO bracket
```

The stop and target rest across bars until one fills (cancelling the other), and
only ever reduce the position. See `asia_reversion` for a full example.

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
