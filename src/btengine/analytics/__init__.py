"""Performance metrics and reporting."""
from btengine.analytics.metrics import compute_metrics
from btengine.analytics.report import format_report, plot_equity
from btengine.analytics.visualize import dashboard

__all__ = ["compute_metrics", "format_report", "plot_equity", "dashboard"]
