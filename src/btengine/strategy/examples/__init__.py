"""Example strategies."""
from btengine.strategy.examples.sma_crossover import SmaCrossover

# Registry used by the run-backtest CLI (--strategy <name>).
REGISTRY = {
    "sma_crossover": SmaCrossover,
}

__all__ = ["SmaCrossover", "REGISTRY"]
