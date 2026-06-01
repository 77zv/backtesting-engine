import pandas as pd

from btengine.core.engine import Backtester
from btengine.strategy.base import Strategy
from btengine.strategy.examples.sma_crossover import SmaCrossover
from btengine.analytics.visualize import dashboard, _instrument_records
from conftest import make_ohlcv


class RecordingProbe(Strategy):
    def on_bar(self, ctx):
        inst = ctx.instruments[0]
        ctx.record(inst, foo=1.5, bar=2.0)
        ctx.record(global_metric=len(ctx.history(inst)))


def test_ctx_record_collects_namespaced_and_global():
    data = {"EUR_USD": make_ohlcv(list(range(100, 105)))}
    result = Backtester(data, RecordingProbe()).run()
    recs = result.records
    assert not recs.empty
    assert "EUR_USD.foo" in recs.columns
    assert "EUR_USD.bar" in recs.columns
    assert "global_metric" in recs.columns
    assert (recs["EUR_USD.foo"] == 1.5).all()
    # Instrument-scoped view strips the prefix.
    sub = _instrument_records(recs, "EUR_USD")
    assert set(sub.columns) == {"foo", "bar"}


def test_dashboard_writes_self_contained_html(tmp_path):
    data = {
        "EUR_USD": make_ohlcv([100 + (i % 7) - 3 for i in range(120)]),
        "GBP_USD": make_ohlcv([200 + (i % 5) - 2 for i in range(120)]),
    }
    result = Backtester(data, SmaCrossover(fast=5, slow=15), default_units=10).run()
    out = dashboard(result, data, tmp_path / "dash.html", title="Test", granularity="H1")

    assert out.exists()
    html = out.read_text()
    # Self-contained: plotly.js embedded (not just a CDN link).
    assert "<html" in html.lower()
    assert "Plotly.newPlot" in html
    assert "Test" in html
    # Recorded indicators surfaced as overlay traces.
    assert "EUR_USD.sma_fast" in html


class _NoopStrategy(Strategy):
    def on_bar(self, ctx):
        pass


def test_dashboard_handles_no_trades(tmp_path):
    # A strategy that never trades -> empty trade log must not break rendering.
    data = {"EUR_USD": make_ohlcv(list(range(100, 130)))}
    result = Backtester(data, _NoopStrategy()).run()
    out = dashboard(result, data, tmp_path / "empty.html")
    assert out.exists() and "Plotly.newPlot" in out.read_text()
