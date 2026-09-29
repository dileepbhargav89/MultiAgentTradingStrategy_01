"""Unit tests for GAEngine: tournament selection, dynamic quotas, and multi-generation evolution."""

import numpy as np
import pandas as pd
import pytest

from core.types import StrategySpecies, VolatilityRegime
from engine.ga_engine import GAEngine
from engine.population_manager import PopulationManager


def generate_market(periods: int = 150) -> pd.DataFrame:
    np.random.seed(77)
    closes = [60000.0]
    for _ in range(periods - 1):
        closes.append(closes[-1] * (1.0 + np.random.normal(0.0005, 0.004)))

    closes = np.array(closes)
    return pd.DataFrame({
        "open": closes * 0.999,
        "high": closes * 1.003,
        "low": closes * 0.997,
        "close": closes,
        "volume": [1200.0] * periods,
    })


def test_ga_engine_dynamic_regime_quotas():
    engine = GAEngine()

    quotas_comp = engine.get_regime_quotas(VolatilityRegime.LOW_VOL_COMPRESSION)
    assert quotas_comp[StrategySpecies.BREAKOUT_VOLATILITY] == 34
    assert quotas_comp[StrategySpecies.MEAN_REVERSION] == 32
    assert sum(quotas_comp.values()) == 96

    quotas_trend = engine.get_regime_quotas(VolatilityRegime.TRENDING_EXPANSION)
    assert quotas_trend[StrategySpecies.MOMENTUM_TREND] == 42
    assert sum(quotas_trend.values()) == 96

    quotas_chaos = engine.get_regime_quotas(VolatilityRegime.HIGH_VOL_CHAOS)
    assert quotas_chaos[StrategySpecies.REGIME_ADAPTIVE] == 51
    assert sum(quotas_chaos.values()) == 96


def test_ga_engine_evolution_cycle():
    df = generate_market(periods=150)
    pop_mgr = PopulationManager(population_size=32, quota_per_species=8)
    engine = GAEngine(population_manager=pop_mgr, population_size=32, elitism_per_species=1, immigrants_count=4)

    # Initial generation 0
    pop_mgr.initialize_population()
    assert pop_mgr.generation == 0

    # Evolve 1 generation
    results = engine.evolve_generation(df, current_regime=VolatilityRegime.TRENDING_EXPANSION)
    assert pop_mgr.generation == 1
    assert len(pop_mgr.population) == 32
    assert len(engine.generation_history) == 1


def test_ga_engine_multi_generation_run():
    df = generate_market(periods=120)
    pop_mgr = PopulationManager(population_size=20, quota_per_species=5)
    engine = GAEngine(population_manager=pop_mgr, population_size=20, elitism_per_species=1, immigrants_count=4)

    summary = engine.run_evolution(df, generations=3)
    assert summary["completed_generations"] == 3
    assert summary["final_generation"] == 3
    assert summary["champion"] is not None
    assert len(summary["history"]) == 3
