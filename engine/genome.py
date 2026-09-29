"""Strategy Genome definition, boundary validation, and genetic operators."""

import copy
import random
import uuid
from typing import Any, Dict, Optional, Tuple
import numpy as np

from core.types import StrategyGenome, StrategySpecies


GENOME_BOUNDS: Dict[str, Tuple[float, float]] = {
    "entry_signal_threshold": (0.15, 0.85),
    "trend_filter_lookback": (10.0, 200.0),
    "rsi_oversold_bound": (20.0, 45.0),
    "rsi_overbought_bound": (55.0, 80.0),
    "stop_loss_atr_mult": (1.0, 3.5),
    "take_profit_atr_mult": (1.5, 6.0),
}


class GenomeManager:
    """Handles genome validation, boundary clamping, mutation, and crossover."""

    @staticmethod
    def clamp_and_validate(genome: StrategyGenome) -> StrategyGenome:
        """Clamps all genes to their valid theoretical ranges and enforces mathematical invariants."""
        # 1. Clamp continuous bounds
        thresh = float(np.clip(
            genome.entry_signal_threshold,
            GENOME_BOUNDS["entry_signal_threshold"][0],
            GENOME_BOUNDS["entry_signal_threshold"][1],
        ))
        lookback = int(np.clip(
            genome.trend_filter_lookback,
            GENOME_BOUNDS["trend_filter_lookback"][0],
            GENOME_BOUNDS["trend_filter_lookback"][1],
        ))
        rsi_os = float(np.clip(
            genome.rsi_oversold_bound,
            GENOME_BOUNDS["rsi_oversold_bound"][0],
            GENOME_BOUNDS["rsi_oversold_bound"][1],
        ))
        rsi_ob = float(np.clip(
            genome.rsi_overbought_bound,
            GENOME_BOUNDS["rsi_overbought_bound"][0],
            GENOME_BOUNDS["rsi_overbought_bound"][1],
        ))
        sl_mult = float(np.clip(
            genome.stop_loss_atr_mult,
            GENOME_BOUNDS["stop_loss_atr_mult"][0],
            GENOME_BOUNDS["stop_loss_atr_mult"][1],
        ))
        tp_mult = float(np.clip(
            genome.take_profit_atr_mult,
            GENOME_BOUNDS["take_profit_atr_mult"][0],
            GENOME_BOUNDS["take_profit_atr_mult"][1],
        ))

        # 2. Enforce invariants: RSI oversold < overbought with minimum separation of 15 points
        if rsi_os >= rsi_ob - 15.0:
            rsi_os = max(20.0, rsi_ob - 20.0)

        # 3. Enforce positive Risk/Reward: TP multiple >= 1.2 * SL multiple
        if tp_mult < sl_mult * 1.2:
            tp_mult = min(6.0, sl_mult * 1.5)

        return StrategyGenome(
            strategy_id=genome.strategy_id,
            species=genome.species,
            entry_signal_threshold=thresh,
            trend_filter_lookback=lookback,
            rsi_oversold_bound=rsi_os,
            rsi_overbought_bound=rsi_ob,
            stop_loss_atr_mult=sl_mult,
            take_profit_atr_mult=tp_mult,
            sentiment_filter_enabled=genome.sentiment_filter_enabled,
            generation=genome.generation,
            fitness_score=genome.fitness_score,
        )

    @classmethod
    def random_genome(
        cls,
        species: StrategySpecies,
        strategy_id: Optional[str] = None,
        generation: int = 0,
    ) -> StrategyGenome:
        """Generates a random valid strategy genome for a given species."""
        if strategy_id is None:
            prefix = species.value[:3].upper()
            strategy_id = f"{prefix}-G{generation}-{uuid.uuid4().hex[:6]}"

        thresh = random.uniform(GENOME_BOUNDS["entry_signal_threshold"][0], GENOME_BOUNDS["entry_signal_threshold"][1])
        lookback = random.randint(int(GENOME_BOUNDS["trend_filter_lookback"][0]), int(GENOME_BOUNDS["trend_filter_lookback"][1]))
        rsi_os = random.uniform(GENOME_BOUNDS["rsi_oversold_bound"][0], GENOME_BOUNDS["rsi_oversold_bound"][1])
        rsi_ob = random.uniform(GENOME_BOUNDS["rsi_overbought_bound"][0], GENOME_BOUNDS["rsi_overbought_bound"][1])
        sl_mult = random.uniform(GENOME_BOUNDS["stop_loss_atr_mult"][0], GENOME_BOUNDS["stop_loss_atr_mult"][1])
        tp_mult = max(sl_mult * 1.5, random.uniform(GENOME_BOUNDS["take_profit_atr_mult"][0], GENOME_BOUNDS["take_profit_atr_mult"][1]))
        sentiment = random.choice([True, False])

        raw_genome = StrategyGenome(
            strategy_id=strategy_id,
            species=species,
            entry_signal_threshold=thresh,
            trend_filter_lookback=lookback,
            rsi_oversold_bound=rsi_os,
            rsi_overbought_bound=rsi_ob,
            stop_loss_atr_mult=sl_mult,
            take_profit_atr_mult=tp_mult,
            sentiment_filter_enabled=sentiment,
            generation=generation,
            fitness_score=0.0,
        )
        return cls.clamp_and_validate(raw_genome)

    @classmethod
    def mutate(
        cls,
        genome: StrategyGenome,
        mutation_rate: float = 0.25,
        mutation_power: float = 0.20,
        new_generation: Optional[int] = None,
    ) -> StrategyGenome:
        """
        Applies stochastic Gaussian perturbation to alleles with probability `mutation_rate`.
        Mutation power scales the standard deviation relative to each gene's range.
        """
        gen = new_generation if new_generation is not None else genome.generation + 1
        prefix = genome.species.value[:3].upper()
        new_id = f"{prefix}-G{gen}-{uuid.uuid4().hex[:6]}"

        thresh = genome.entry_signal_threshold
        if random.random() < mutation_rate:
            delta = np.random.normal(0, mutation_power * (GENOME_BOUNDS["entry_signal_threshold"][1] - GENOME_BOUNDS["entry_signal_threshold"][0]))
            thresh += delta

        lookback = genome.trend_filter_lookback
        if random.random() < mutation_rate:
            delta = int(np.random.normal(0, mutation_power * 40))
            lookback += delta

        rsi_os = genome.rsi_oversold_bound
        if random.random() < mutation_rate:
            rsi_os += float(np.random.normal(0, mutation_power * 10))

        rsi_ob = genome.rsi_overbought_bound
        if random.random() < mutation_rate:
            rsi_ob += float(np.random.normal(0, mutation_power * 10))

        sl_mult = genome.stop_loss_atr_mult
        if random.random() < mutation_rate:
            sl_mult += float(np.random.normal(0, mutation_power * 0.8))

        tp_mult = genome.take_profit_atr_mult
        if random.random() < mutation_rate:
            tp_mult += float(np.random.normal(0, mutation_power * 1.2))

        sentiment = genome.sentiment_filter_enabled
        if random.random() < (mutation_rate * 0.5):
            sentiment = not sentiment

        mutated = StrategyGenome(
            strategy_id=new_id,
            species=genome.species,
            entry_signal_threshold=thresh,
            trend_filter_lookback=lookback,
            rsi_oversold_bound=rsi_os,
            rsi_overbought_bound=rsi_ob,
            stop_loss_atr_mult=sl_mult,
            take_profit_atr_mult=tp_mult,
            sentiment_filter_enabled=sentiment,
            generation=gen,
            fitness_score=0.0,
        )
        return cls.clamp_and_validate(mutated)

    @classmethod
    def crossover(
        cls,
        parent_a: StrategyGenome,
        parent_b: StrategyGenome,
        generation: int,
    ) -> StrategyGenome:
        """
        Breeds an offspring by combining genes from two parent genomes.
        Uses arithmetic blend for numeric genes and uniform selection for boolean genes.
        Parent species is inherited from parent with higher fitness or parent_a.
        """
        chosen_species = parent_a.species if parent_a.fitness_score >= parent_b.fitness_score else parent_b.species
        prefix = chosen_species.value[:3].upper()
        offspring_id = f"{prefix}-G{generation}-{uuid.uuid4().hex[:6]}"

        # Arithmetic blending with random weight alpha in [0.2, 0.8]
        alpha = random.uniform(0.2, 0.8)

        thresh = alpha * parent_a.entry_signal_threshold + (1 - alpha) * parent_b.entry_signal_threshold
        lookback = int(round(alpha * parent_a.trend_filter_lookback + (1 - alpha) * parent_b.trend_filter_lookback))
        rsi_os = alpha * parent_a.rsi_oversold_bound + (1 - alpha) * parent_b.rsi_oversold_bound
        rsi_ob = alpha * parent_a.rsi_overbought_bound + (1 - alpha) * parent_b.rsi_overbought_bound
        sl_mult = alpha * parent_a.stop_loss_atr_mult + (1 - alpha) * parent_b.stop_loss_atr_mult
        tp_mult = alpha * parent_a.take_profit_atr_mult + (1 - alpha) * parent_b.take_profit_atr_mult
        sentiment = parent_a.sentiment_filter_enabled if random.random() < 0.5 else parent_b.sentiment_filter_enabled

        offspring = StrategyGenome(
            strategy_id=offspring_id,
            species=chosen_species,
            entry_signal_threshold=thresh,
            trend_filter_lookback=lookback,
            rsi_oversold_bound=rsi_os,
            rsi_overbought_bound=rsi_ob,
            stop_loss_atr_mult=sl_mult,
            take_profit_atr_mult=tp_mult,
            sentiment_filter_enabled=sentiment,
            generation=generation,
            fitness_score=0.0,
        )
        return cls.clamp_and_validate(offspring)
