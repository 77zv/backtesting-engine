"""Interactive Plotly dashboard for a backtest result.

Produces a single self-contained HTML file with:
  - one price panel per instrument (candlesticks) + recorded indicator overlays
    + buy/sell entry and exit markers,
  - an equity-curve panel,
  - a drawdown panel,
  - trade-analytics histograms (per-trade P&L and bar-return distribution).

Plotly is imported lazily so the rest of the package works without it.
"""
from __future__ import annotations

from pathlib import Path
from typing import Dict, Optional, Union

import pandas as pd

from btengine.analytics.metrics import compute_metrics


def _instrument_records(records: pd.DataFrame, instrument: str) -> pd.DataFrame:
    """Columns recorded for `instrument` (prefixed "<instrument>."), prefix stripped."""
    if records is None or records.empty:
        return pd.DataFrame()
    prefix = f"{instrument}."
    cols = [c for c in records.columns if c.startswith(prefix)]
    sub = records[cols].copy()
    sub.columns = [c[len(prefix):] for c in cols]
    return sub


def build_figure(result, data: Dict[str, pd.DataFrame], title: str = "Backtest"):
    """Build (price+equity+drawdown figure, analytics figure) as a Plotly tuple."""
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots

    instruments = list(data)
    trades = result.trades
    equity = result.equity
    records = getattr(result, "records", pd.DataFrame())

    n_price = len(instruments)
    rows = n_price + 2
    price_h, other_h = 0.6 / max(n_price, 1), 0.2
    row_heights = [price_h] * n_price + [other_h, other_h]
    titles = [f"{inst} — price & trades" for inst in instruments] + ["Equity", "Drawdown"]

    fig = make_subplots(
        rows=rows, cols=1, shared_xaxes=True, vertical_spacing=0.03,
        row_heights=row_heights, subplot_titles=titles,
    )

    for i, inst in enumerate(instruments):
        r = i + 1
        df = data[inst]
        fig.add_trace(
            go.Candlestick(
                x=df.index, open=df["open"], high=df["high"], low=df["low"], close=df["close"],
                name=inst, showlegend=False,
            ),
            row=r, col=1,
        )
        # Indicator overlays (recorded via ctx.record).
        for col in (recs := _instrument_records(records, inst)).columns:
            fig.add_trace(
                go.Scatter(x=recs.index, y=recs[col], mode="lines", name=f"{inst}.{col}",
                           line=dict(width=1)),
                row=r, col=1,
            )
        _add_trade_markers(fig, go, trades, inst, r)
        fig.update_yaxes(title_text="price", row=r, col=1)

    # Equity.
    fig.add_trace(
        go.Scatter(x=equity.index, y=equity.values, mode="lines", name="equity",
                   line=dict(color="#1f77b4"), showlegend=False),
        row=n_price + 1, col=1,
    )
    # Drawdown.
    if len(equity):
        dd = (equity / equity.cummax() - 1.0) * 100
        fig.add_trace(
            go.Scatter(x=dd.index, y=dd.values, mode="lines", name="drawdown",
                       fill="tozeroy", line=dict(color="#d62728"), showlegend=False),
            row=n_price + 2, col=1,
        )
    fig.update_yaxes(title_text="equity", row=n_price + 1, col=1)
    fig.update_yaxes(title_text="drawdown %", row=n_price + 2, col=1)

    # Candlestick range sliders clutter a stacked layout.
    fig.update_layout(
        title=title, height=260 * rows, xaxis_rangeslider_visible=False,
        hovermode="x unified", legend=dict(orientation="h", y=1.02, yanchor="bottom"),
        margin=dict(t=80, l=60, r=30, b=40),
    )
    for ax in range(2, rows + 1):
        fig.update_layout(**{f"xaxis{ax}_rangeslider_visible": False})

    return fig, _analytics_figure(go, make_subplots, result)


def _add_trade_markers(fig, go, trades: pd.DataFrame, instrument: str, row: int) -> None:
    if trades is None or trades.empty:
        return
    t = trades[trades["instrument"] == instrument]
    if t.empty:
        return
    longs = t[t["units"] > 0]
    shorts = t[t["units"] < 0]
    # Entries: long = green up-triangle, short = red down-triangle.
    if not longs.empty:
        fig.add_trace(
            go.Scatter(x=longs["entry_time"], y=longs["entry_price"], mode="markers",
                       name="long entry", marker=dict(symbol="triangle-up", size=10, color="green")),
            row=row, col=1,
        )
    if not shorts.empty:
        fig.add_trace(
            go.Scatter(x=shorts["entry_time"], y=shorts["entry_price"], mode="markers",
                       name="short entry", marker=dict(symbol="triangle-down", size=10, color="red")),
            row=row, col=1,
        )
    # Exits coloured by P&L (win = green, loss = red).
    colors = ["green" if p >= 0 else "red" for p in t["pnl"]]
    fig.add_trace(
        go.Scatter(x=t["exit_time"], y=t["exit_price"], mode="markers", name="exit",
                   marker=dict(symbol="x", size=8, color=colors),
                   text=[f"P&L {p:,.2f}" for p in t["pnl"]], hoverinfo="text+x+y"),
        row=row, col=1,
    )


def _analytics_figure(go, make_subplots, result):
    fig = make_subplots(rows=1, cols=2, subplot_titles=["Trade P&L", "Bar-return distribution"])
    trades = result.trades
    if trades is not None and not trades.empty:
        fig.add_trace(go.Histogram(x=trades["pnl"], name="trade P&L", nbinsx=40), row=1, col=1)
    if result.equity is not None and len(result.equity) > 2:
        rets = result.equity.pct_change().dropna() * 100
        fig.add_trace(go.Histogram(x=rets, name="bar returns %", nbinsx=60), row=1, col=2)
    fig.update_layout(height=320, showlegend=False, title="Trade analytics",
                      margin=dict(t=60, l=40, r=30, b=40))
    fig.update_xaxes(title_text="P&L", row=1, col=1)
    fig.update_xaxes(title_text="return %", row=1, col=2)
    return fig


def dashboard(
    result,
    data: Dict[str, pd.DataFrame],
    path: Union[str, Path],
    title: str = "Backtest",
    granularity: Optional[str] = None,
) -> Path:
    """Render the full interactive dashboard to a self-contained HTML file."""
    main_fig, analytics_fig = build_figure(result, data, title=title)
    metrics = compute_metrics(result.equity, result.trades, granularity=granularity)

    summary = "".join(
        f"<span style='margin-right:18px'><b>{k}</b>: {v:,.4g}</span>"
        for k, v in metrics.items()
        if k in ("total_return", "cagr", "sharpe", "max_drawdown", "num_trades", "win_rate")
    )

    # Embed plotly.js once (first figure), reuse for the second -> offline-capable.
    main_html = main_fig.to_html(full_html=False, include_plotlyjs=True)
    analytics_html = analytics_fig.to_html(full_html=False, include_plotlyjs=False)

    html = (
        f"<!DOCTYPE html><html><head><meta charset='utf-8'><title>{title}</title></head>"
        f"<body style='font-family:sans-serif;margin:16px'>"
        f"<h2>{title}</h2><div style='margin:8px 0 16px'>{summary}</div>"
        f"{main_html}{analytics_html}</body></html>"
    )

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(html, encoding="utf-8")
    return path
