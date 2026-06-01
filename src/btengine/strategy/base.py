"""Strategy base class.

Subclass and implement `on_bar`. Use the `Context` (`ctx`) passed to each hook
to read causal history and submit orders (`ctx.buy/sell/close/order_target_units`).
Orders are filled on the next bar, so strategies cannot peek at future prices.
"""
from __future__ import annotations

from typing import Any


class Strategy:
    def __init__(self, **params: Any):
        self.params = params
        self.ctx = None  # bound by the engine before on_start

    def bind(self, ctx) -> None:
        self.ctx = ctx

    # --- lifecycle hooks (override as needed) ------------------------------
    def on_start(self, ctx) -> None:
        """Called once before the first bar."""

    def on_bar(self, ctx) -> None:
        """Called once per timestamp, after equity is marked at the bar close."""
        raise NotImplementedError

    def on_finish(self, ctx) -> None:
        """Called once after the last bar."""

    # --- convenience -------------------------------------------------------
    def param(self, name: str, default: Any = None) -> Any:
        return self.params.get(name, default)
