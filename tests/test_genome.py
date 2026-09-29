"""Unit tests for StrategyGenome and GenomeManager."""

import pytest
from core.types import StrategyGenome, StrategySpecies
from engine.genome import GENOME_BOUNDS, GenomeManager


def test_genome_bounds_and_clamping():
    # Intentionally malformed genome with negative values and invalid bounds
    raw = StrategyGenome(
        strategy_id="TEST-01",
        species=StrategySpecies.MOMENTUM_TREND,
        entry_signal_threshold=0.01,   # Below min 0.15
        trend_filter_lookback=5,       # Below min 10
        rsi_oversold_bound=50.0,       # Conflicted with overbought
        rsi_overbought_bound=40.0,     # Below oversold!
        stop_loss_atr_mult=0.5,        # Below min 1.0
        take_profit_atr_mult=0.8,      # Violates RR ratio
    )

    clamped = GenomeManager.clamp_and_validate(raw)

    assert clamped.entry_signal_threshold >= GENOME_BOUNDS["entry_signal_threshold"][0]
    assert clamped.trend_filter_lookback >= GENOME_BOUNDS["trend_filter_lookback"][0]
    assert clamped.rsi_oversold_bound < clamped.rsi_overbought_bound
    assert clamped.stop_loss_atr_mult >= 1.0
    assert clamped.take_profit_atr_mult >= clamped.stop_loss_atr_mult * 1.2


def test_random_genome_generation():
    for species in StrategySpecies:
        genome = GenomeManager.random_genome(species, generation=0)
        assert genome.species == species
        assert GENOME_BOUNDS["entry_signal_threshold"][0] <= genome.entry_signal_threshold <= GENOME_BOUNDS["entry_signal_threshold"][1]
        assert GENOME_BOUNDS["trend_filter_lookback"][0] <= genome.trend_filter_lookback <= GENOME_BOUNDS["trend_filter_lookback"][1]
        assert genome.rsi_oversold_bound < genome.rsi_overbought_bound
        assert genome.take_profit_atr_mult >= genome.stop_loss_atr_mult * 1.2


def test_genome_mutation():
    parent = GenomeManager.random_genome(StrategySpecies.MOMENTUM_TREND, generation=1)
    mutated = GenomeManager.mutate(parent, mutation_rate=1.0, mutation_power=0.30, new_generation=2)

    assert mutated.strategy_id != parent.strategy_id
    assert mutated.generation == 2
    assert mutated.species == parent.species
    # At least one gene must have changed
    has_diff = (
        mutated.entry_signal_threshold != parent.entry_signal_threshold
        or mutated.trend_filter_lookback != parent.trend_filter_lookback
        or mutated.rsi_oversold_bound != parent.rsi_oversold_bound
        or mutated.stop_loss_atr_mult != parent.stop_loss_atr_mult
    )
    assert has_diff


def test_genome_crossover():
    parent_a = GenomeManager.random_genome(StrategySpecies.MOMENTUM_TREND, generation=1)
    parent_b = GenomeManager.random_genome(StrategySpecies.MEAN_REVERSION, generation=1)

    parent_a.fitness_score = 1.85
    parent_b.fitness_score = 1.20

    child = GenomeManager.crossover(parent_a, parent_b, generation=2)

    assert child.generation == 2
    assert child.species == StrategySpecies.MOMENTUM_TREND  # Inherited from higher fitness parent_a
    assert child.strategy_id != parent_a.strategy_id
    assert child.strategy_id != parent_b.strategy_id


def test_genome_serialization():
    original = GenomeManager.random_genome(StrategySpecies.BREAKOUT_VOLATILITY, generation=3)
    data = original.to_dict()

    rebuilt = StrategyGenome.from_dict(data)
    assert rebuilt.strategy_id == original.strategy_id
    assert rebuilt.species == original.species
    assert rebuilt.trend_filter_lookback == original.trend_filter_lookback
    assert abs(rebuilt.entry_signal_threshold - original.entry_signal_threshold) < 1e-4
