"""Example strategies."""
from btengine.strategy.examples.asia_reversion import AsiaReversion
from btengine.strategy.examples.opening_range import OpeningRange
from btengine.strategy.examples.orb_retest import ORBRetest
from btengine.strategy.examples.session_breakout import SessionBreakout
from btengine.strategy.examples.sma_crossover import SmaCrossover

# Registry used by the run-backtest CLI (--strategy <name>).
REGISTRY = {
    "sma_crossover": SmaCrossover,
    "opening_range": OpeningRange,
    "session_breakout": SessionBreakout,
    "asia_reversion": AsiaReversion,
    "orb_retest": ORBRetest,
}

__all__ = ["SmaCrossover", "OpeningRange", "SessionBreakout", "AsiaReversion", "ORBRetest", "REGISTRY"]
