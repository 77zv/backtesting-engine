"""Optional base class for session-aware strategies.

Sugar over `btengine.sessions.Session`: filters out-of-session bars and splits
the in-session callback into a once-per-day `on_session_start` and a per-bar
`on_session_bar`. Subclass and override whichever hooks you need. This is purely
a convenience — strategies can also call `Session` helpers directly.
"""
from __future__ import annotations

from typing import Optional

from btengine.sessions import Session
from btengine.strategy.base import Strategy


class SessionStrategy(Strategy):
    #: Subclasses may set a class-level default session.
    session: Optional[Session] = None

    def __init__(self, session: Optional[Session] = None, **params):
        super().__init__(**params)
        if session is not None:
            self.session = session
        if self.session is None:
            raise ValueError("SessionStrategy requires a `session` (preset or custom).")

    def on_bar(self, ctx) -> None:
        for inst in ctx.instruments:
            hist = ctx.history(inst)
            if len(hist) == 0 or not self.session.is_open(hist.index[-1]):
                continue
            if self.session.is_start(hist):
                self.on_session_start(ctx, inst)
            else:
                self.on_session_bar(ctx, inst)

    # --- hooks (override as needed) ----------------------------------------
    def on_session_start(self, ctx, instrument: str) -> None:
        """Called once on the first in-session bar of each trading day."""

    def on_session_bar(self, ctx, instrument: str) -> None:
        """Called on every subsequent in-session bar that day."""
