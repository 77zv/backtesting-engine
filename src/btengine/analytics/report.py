"""Text summary and equity-curve plotting."""
from __future__ import annotations

from pathlib import Path
from typing import Dict, Optional, Union

import pandas as pd

_PCT_KEYS = {"total_return", "cagr", "ann_volatility", "max_drawdown", "win_rate"}
_LABELS = {
    "start_equity": "Start equity",
    "end_equity": "End equity",
    "total_return": "Total return",
    "cagr": "CAGR",
    "ann_volatility": "Annual volatility",
    "sharpe": "Sharpe",
    "sortino": "Sortino",
    "max_drawdown": "Max drawdown",
    "calmar": "Calmar",
    "num_trades": "Trades",
    "win_rate": "Win rate",
    "avg_win": "Avg win",
    "avg_loss": "Avg loss",
    "profit_factor": "Profit factor",
    "total_pnl": "Total P&L",
    "bars": "Bars",
}


def _fmt(key: str, value: float) -> str:
    if key in _PCT_KEYS:
        return f"{value * 100:,.2f}%"
    if key in {"num_trades", "bars"}:
        return f"{int(value):,}"
    return f"{value:,.2f}"


def format_report(metrics: Dict[str, float], title: str = "Backtest Results") -> str:
    lines = [title, "=" * len(title)]
    for key, label in _LABELS.items():
        if key in metrics:
            lines.append(f"{label:<18} {_fmt(key, metrics[key]):>16}")
    return "\n".join(lines)


def plot_equity(
    equity: pd.Series,
    path: Union[str, Path],
    title: str = "Equity Curve",
) -> Path:
    """Save an equity + drawdown plot to `path`. Returns the path."""
    import matplotlib

    matplotlib.use("Agg")  # headless
    import matplotlib.pyplot as plt

    drawdown = equity / equity.cummax() - 1.0
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(11, 7), sharex=True,
                                   gridspec_kw={"height_ratios": [3, 1]})
    ax1.plot(equity.index, equity.values, color="#1f77b4")
    ax1.set_title(title)
    ax1.set_ylabel("Equity")
    ax1.grid(alpha=0.3)

    ax2.fill_between(drawdown.index, drawdown.values * 100, 0, color="#d62728", alpha=0.4)
    ax2.set_ylabel("Drawdown %")
    ax2.grid(alpha=0.3)

    fig.tight_layout()
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=120)
    plt.close(fig)
    return path
