"""Unit tests for PopulationManager: species quotas, heuristic seeds, and population ranking."""

import numpy as np
import pandas as pd
import pytest

from core.events import EVENT_STRATEGY_CHAMPION_SELECTED, event_bus
from core.types import StrategySpecies
from engine.population_manager import PopulationManager


def generate_market_df(periods: int = 200) -> pd.DataFrame:
    np.random.seed(99)
    closes = [60000.0]
    for _ in range(periods - 1):
        closes.append(closes[-1] * (1.0 + np.random.normal(0.0005, 0.003)))

    closes = np.array(closes)
    return pd.DataFrame({
        "open": closes * 0.999,
        "high": closes * 1.003,
        "low": closes * 0.997,
        "close": closes,
        "volume": [1500.0] * periods,
    })


def test_population_initialization():
    mgr = PopulationManager(population_size=96, quota_per_species=24)
    population = mgr.initialize_population()

    assert len(population) == 96

    # Verify 24 strategies per species
    counts = {s: 0 for s in StrategySpecies}
    for g in population:
        counts[g.species] += 1

    for s, c in counts.items():
        assert c == 24, f"Species {s} count was {c}, expected 24"


def test_population_evaluation_and_champion():
    df = generate_market_df(periods=200)
    mgr = PopulationManager(population_size=40, quota_per_species=10)
    mgr.initialize_population()

    champion_events = []
    event_bus.subscribe(EVENT_STRATEGY_CHAMPION_SELECTED, lambda e: champion_events.append(e))

    results = mgr.evaluate_population(df)

    assert len(results) == 40
    # Results should be sorted by fitness descending
    for i in range(len(results) - 1):
        assert results[i].fitness_score >= results[i + 1].fitness_score

    assert mgr.champion is not None
    assert mgr.champion.strategy_id == results[0].strategy_id
    assert len(champion_events) >= 1

    # Check species champions
    species_champs = mgr.get_species_champions()
    assert len(species_champs) == 4
    for species in StrategySpecies:
        assert species in species_champs
