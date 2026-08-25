import pytest

from app.strategies.factory import build_strategy
from app.strategies.rsi import RsiStrategy
from app.strategies.sma_crossover import SmaCrossoverStrategy


def test_build_sma_strategy_with_params():
    strategy = build_strategy("SMA", {"short_window": 5, "long_window": 20})

    assert isinstance(strategy, SmaCrossoverStrategy)
    assert strategy.short_window == 5
    assert strategy.long_window == 20


def test_build_sma_crossover_alias():
    strategy = build_strategy("SMA_CROSSOVER", {"short_window": 5, "long_window": 20})
    assert isinstance(strategy, SmaCrossoverStrategy)


def test_build_strategy_name_is_case_insensitive():
    strategy = build_strategy("sma", {"short_window": 5, "long_window": 20})
    assert isinstance(strategy, SmaCrossoverStrategy)


def test_build_rsi_strategy_with_params():
    strategy = build_strategy("RSI", {"period": 21, "oversold": 25, "overbought": 75})

    assert isinstance(strategy, RsiStrategy)
    assert strategy.period == 21
    assert strategy.oversold == 25
    assert strategy.overbought == 75


def test_build_strategy_with_no_params_uses_defaults():
    strategy = build_strategy("SMA", None)
    assert isinstance(strategy, SmaCrossoverStrategy)


def test_build_strategy_rejects_unknown_name():
    with pytest.raises(ValueError, match="Unknown strategy"):
        build_strategy("MACD", {})


def test_build_strategy_propagates_invalid_sma_params():
    with pytest.raises(ValueError, match="must be less than"):
        build_strategy("SMA", {"short_window": 30, "long_window": 10})


def test_build_strategy_rejects_unexpected_params():
    with pytest.raises(ValueError, match="Invalid parameters"):
        build_strategy("SMA", {"not_a_real_param": 123})
