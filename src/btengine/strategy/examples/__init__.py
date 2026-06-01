"""Example strategies."""
from btengine.strategy.examples.opening_range import OpeningRange
from btengine.strategy.examples.sma_crossover import SmaCrossover

# Registry used by the run-backtest CLI (--strategy <name>).
REGISTRY = {
    "sma_crossover": SmaCrossover,
    "opening_range": OpeningRange,
}

__all__ = ["SmaCrossover", "OpeningRange", "REGISTRY"]
