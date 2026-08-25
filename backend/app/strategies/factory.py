"""Constructs a strategy instance by name + params — used by the
backtesting/comparison API layer only.

The live autonomous trader never goes through this factory: it always
instantiates SmaCrossoverStrategy() directly with its own configured
settings (see app/services/trading_orchestrator.py), so nothing here can
change what the autonomous trader runs.
"""
from app.strategies.base import BaseStrategy
from app.strategies.rsi import RsiStrategy
from app.strategies.sma_crossover import SmaCrossoverStrategy

STRATEGY_REGISTRY: dict[str, type[BaseStrategy]] = {
    "SMA": SmaCrossoverStrategy,
    "SMA_CROSSOVER": SmaCrossoverStrategy,
    "RSI": RsiStrategy,
}


def build_strategy(name: str, params: dict | None = None) -> BaseStrategy:
    params = params or {}
    strategy_cls = STRATEGY_REGISTRY.get(name.upper())
    if strategy_cls is None:
        raise ValueError(f"Unknown strategy '{name}'. Available: SMA, RSI")
    try:
        return strategy_cls(**params)
    except TypeError as exc:
        raise ValueError(f"Invalid parameters for {name}: {exc}") from exc
