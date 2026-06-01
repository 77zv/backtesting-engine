"""Performance metrics computed from an equity curve and trade log."""
from __future__ import annotations

from typing import Dict, Optional

import numpy as np
import pandas as pd

# Periods per year for annualization, keyed by Oanda granularity.
_PERIODS_PER_YEAR = {
    "S5": 252 * 24 * 720, "M1": 252 * 24 * 60, "M5": 252 * 24 * 12,
    "M15": 252 * 24 * 4, "M30": 252 * 24 * 2, "H1": 252 * 24,
    "H4": 252 * 6, "D": 252, "W": 52, "M": 12,
}


def _infer_periods_per_year(index: pd.DatetimeIndex) -> float:
    """Estimate annualization factor from the median spacing of timestamps."""
    if len(index) < 3:
        return 252.0
    median_sec = np.median(np.diff(index.values).astype("timedelta64[s]").astype(float))
    if median_sec <= 0:
        return 252.0
    # ~252 trading days/year of active market seconds.
    return (252.0 * 24 * 3600) / median_sec


def compute_metrics(
    equity: pd.Series,
    trades: Optional[pd.DataFrame] = None,
    granularity: Optional[str] = None,
    risk_free_rate: float = 0.0,
) -> Dict[str, float]:
    """Return a dict of headline performance metrics.

    `risk_free_rate` is an annual rate used for Sharpe/Sortino.
    """
    out: Dict[str, float] = {}
    if equity is None or len(equity) < 2:
        return {"bars": float(0 if equity is None else len(equity))}

    equity = equity.astype(float)
    ppy = _PERIODS_PER_YEAR.get(granularity) if granularity else None
    if ppy is None:
        ppy = _infer_periods_per_year(equity.index)

    returns = equity.pct_change().dropna()
    total_return = equity.iloc[-1] / equity.iloc[0] - 1.0

    years = len(returns) / ppy if ppy else np.nan
    cagr = (equity.iloc[-1] / equity.iloc[0]) ** (1.0 / years) - 1.0 if years and years > 0 else np.nan

    rf_per_period = risk_free_rate / ppy
    excess = returns - rf_per_period
    vol = returns.std(ddof=1)
    sharpe = (excess.mean() / vol * np.sqrt(ppy)) if vol > 0 else np.nan

    downside = returns[returns < 0]
    dvol = downside.std(ddof=1)
    sortino = (excess.mean() / dvol * np.sqrt(ppy)) if dvol and dvol > 0 else np.nan

    # Max drawdown.
    running_max = equity.cummax()
    drawdown = equity / running_max - 1.0
    max_dd = drawdown.min()
    calmar = (cagr / abs(max_dd)) if max_dd < 0 and not np.isnan(cagr) else np.nan

    out.update(
        {
            "start_equity": float(equity.iloc[0]),
            "end_equity": float(equity.iloc[-1]),
            "total_return": float(total_return),
            "cagr": float(cagr) if cagr == cagr else float("nan"),
            "ann_volatility": float(vol * np.sqrt(ppy)) if vol > 0 else 0.0,
            "sharpe": float(sharpe) if sharpe == sharpe else float("nan"),
            "sortino": float(sortino) if sortino == sortino else float("nan"),
            "max_drawdown": float(max_dd),
            "calmar": float(calmar) if calmar == calmar else float("nan"),
            "bars": float(len(equity)),
            "periods_per_year": float(ppy),
        }
    )

    if trades is not None and len(trades):
        pnl = trades["pnl"].astype(float)
        wins = pnl[pnl > 0]
        losses = pnl[pnl < 0]
        out.update(
            {
                "num_trades": float(len(pnl)),
                "win_rate": float(len(wins) / len(pnl)),
                "avg_win": float(wins.mean()) if len(wins) else 0.0,
                "avg_loss": float(losses.mean()) if len(losses) else 0.0,
                "profit_factor": float(wins.sum() / abs(losses.sum())) if losses.sum() != 0 else float("inf"),
                "total_pnl": float(pnl.sum()),
            }
        )
    else:
        out["num_trades"] = 0.0

    return out
