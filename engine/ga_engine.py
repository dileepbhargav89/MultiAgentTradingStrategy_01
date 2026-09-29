"""Multi-generation Genetic Algorithm engine with dynamic regime quotas and anti-stagnation mechanisms."""

import copy
import random
from typing import Any, Dict, List, Optional, Tuple
import numpy as np
import pandas as pd
from loguru import logger

from core.events import (
    EVENT_STRATEGY_CHAMPION_SELECTED,
    EVENT_STRATEGY_POPULATION_EVOLVED,
    event_bus,
)
from core.types import BacktestResult, StrategyGenome, StrategySpecies, VolatilityRegime
from engine.genome import GenomeManager
from engine.population_manager import PopulationManager
from engine.vectorized_backtester import VectorizedBacktester


class GAEngine:
    """
    Orchestrates generational breeding, tournament selection, elitism,
    random immigrant injection, and dynamic regime-conditioned species quotas.
    """

    def __init__(
        self,
        population_manager: Optional[PopulationManager] = None,
        population_size: int = 96,
        tournament_k: int = 3,
        elitism_per_species: int = 2,
        immigrants_count: int = 8,
        mutation_rate: float = 0.25,
        mutation_power: float = 0.20,
    ) -> None:
        self.pop_mgr = population_manager or PopulationManager(population_size=population_size)
        self.population_size = population_size
        self.tournament_k = tournament_k
        self.elitism_per_species = elitism_per_species
        self.immigrants_count = immigrants_count
        self.mutation_rate = mutation_rate
        self.mutation_power = mutation_power
        self.backtester = VectorizedBacktester()
        self.generation_history: List[Dict[str, Any]] = []

    def get_regime_quotas(self, regime: Optional[VolatilityRegime]) -> Dict[StrategySpecies, int]:
        """Dynamically adjusts target quotas based on active volatility regime."""
        if regime == VolatilityRegime.LOW_VOL_COMPRESSION or regime == "LOW_VOL_COMPRESSION":
            return {
                StrategySpecies.BREAKOUT_VOLATILITY: 34,
                StrategySpecies.MEAN_REVERSION: 32,
                StrategySpecies.MOMENTUM_TREND: 15,
                StrategySpecies.REGIME_ADAPTIVE: 15,
            }
        elif regime == VolatilityRegime.TRENDING_EXPANSION or regime == "TRENDING_EXPANSION":
            return {
                StrategySpecies.MOMENTUM_TREND: 42,
                StrategySpecies.BREAKOUT_VOLATILITY: 24,
                StrategySpecies.MEAN_REVERSION: 15,
                StrategySpecies.REGIME_ADAPTIVE: 15,
            }
        elif regime == VolatilityRegime.HIGH_VOL_CHAOS or regime == "HIGH_VOL_CHAOS":
            return {
                StrategySpecies.REGIME_ADAPTIVE: 51,
                StrategySpecies.BREAKOUT_VOLATILITY: 15,
                StrategySpecies.MOMENTUM_TREND: 15,
                StrategySpecies.MEAN_REVERSION: 15,
            }
        else:
            return {
                StrategySpecies.MOMENTUM_TREND: 24,
                StrategySpecies.MEAN_REVERSION: 24,
                StrategySpecies.BREAKOUT_VOLATILITY: 24,
                StrategySpecies.REGIME_ADAPTIVE: 24,
            }

    def tournament_select(self, population: List[StrategyGenome], k: int = 3) -> StrategyGenome:
        """Selects parent using tournament selection of size k."""
        candidates = random.sample(population, min(k, len(population)))
        best = max(candidates, key=lambda g: g.fitness_score)
        return best

    def evolve_generation(
        self,
        df: pd.DataFrame,
        current_regime: Optional[VolatilityRegime] = None,
    ) -> List[BacktestResult]:
        """
        Executes a single generational evolution cycle:
        1. Evaluate current generation
        2. Preserve species elites
        3. Inject random immigrants
        4. Breed offspring to meet target regime quotas
        """
        # Ensure population is initialized
        if not self.pop_mgr.population:
            self.pop_mgr.initialize_population()

        current_gen = self.pop_mgr.generation
        results = self.pop_mgr.evaluate_population(df)

        quotas = self.get_regime_quotas(current_regime)
        next_gen_number = current_gen + 1
        new_population: List[StrategyGenome] = []

        # 1. Elitism: Preserve top 2 performers per species
        species_pools: Dict[StrategySpecies, List[StrategyGenome]] = {s: [] for s in StrategySpecies}
        for g in self.pop_mgr.population:
            species_pools[g.species].append(g)

        elites_kept = 0
        for species, pool in species_pools.items():
            pool.sort(key=lambda g: g.fitness_score, reverse=True)
            for elite in pool[:self.elitism_per_species]:
                # Deep copy elite into next generation
                clone = copy.deepcopy(elite)
                clone.generation = next_gen_number
                new_population.append(clone)
                elites_kept += 1

        # 2. Random Immigrants: Inject fresh genomes to prevent local optima traps
        for species in StrategySpecies:
            for _ in range(self.immigrants_count // 4):
                immigrant = GenomeManager.random_genome(species, generation=next_gen_number)
                new_population.append(immigrant)

        # 3. Breeding to satisfy target species quotas
        current_counts = {s: 0 for s in StrategySpecies}
        for g in new_population:
            current_counts[g.species] += 1

        for species, target in quotas.items():
            needed = target - current_counts[species]
            pool = species_pools[species] if len(species_pools[species]) >= 2 else self.pop_mgr.population

            for _ in range(max(0, needed)):
                parent_a = self.tournament_select(pool, k=self.tournament_k)
                parent_b = self.tournament_select(pool, k=self.tournament_k)

                offspring = GenomeManager.crossover(parent_a, parent_b, generation=next_gen_number)
                mutated_offspring = GenomeManager.mutate(
                    offspring,
                    mutation_rate=self.mutation_rate,
                    mutation_power=self.mutation_power,
                    new_generation=next_gen_number,
                )
                # Ensure species aligns with target quota
                mutated_offspring.species = species
                new_population.append(mutated_offspring)

        # Truncate or pad to exact population size
        if len(new_population) > self.population_size:
            new_population = new_population[:self.population_size]
        elif len(new_population) < self.population_size:
            diff = self.population_size - len(new_population)
            for _ in range(diff):
                rand_sp = random.choice(list(StrategySpecies))
                new_population.append(GenomeManager.random_genome(rand_sp, generation=next_gen_number))

        # Update PopulationManager
        self.pop_mgr.population = new_population
        self.pop_mgr.generation = next_gen_number

        # Log & record generation history
        best_res = results[0] if results else None
        avg_fitness = float(np.mean([r.fitness_score for r in results])) if results else 0.0

        gen_stat = {
            "generation": current_gen,
            "best_fitness": best_res.fitness_score if best_res else 0.0,
            "avg_fitness": round(avg_fitness, 4),
            "champion_id": best_res.strategy_id if best_res else None,
            "champion_species": best_res.species.value if best_res else None,
            "champion_sharpe": best_res.sharpe_ratio if best_res else 0.0,
        }
        self.generation_history.append(gen_stat)

        logger.info(
            f"GA Generation {current_gen} -> {next_gen_number} | Best Fitness: {gen_stat['best_fitness']:.3f} | "
            f"Avg Fitness: {gen_stat['avg_fitness']:.3f} | Champion: {gen_stat['champion_id']}"
        )

        return results

    def run_evolution(
        self,
        df: pd.DataFrame,
        generations: int = 5,
        current_regime: Optional[VolatilityRegime] = None,
    ) -> Dict[str, Any]:
        """Runs multiple generations of evolution sequentially."""
        logger.info(f"Starting Evolutionary Run for {generations} generations...")
        for g in range(generations):
            self.evolve_generation(df, current_regime=current_regime)

        # Final evaluation of the last generation
        final_results = self.pop_mgr.evaluate_population(df)

        return {
            "completed_generations": generations,
            "final_generation": self.pop_mgr.generation,
            "champion": self.pop_mgr.champion,
            "champion_result": final_results[0] if final_results else None,
            "history": self.generation_history,
        }
