"""Population management, heuristic seed strategies, and batch backtesting."""

from typing import Dict, List, Optional, Tuple
import pandas as pd
from loguru import logger

from core.events import (
    EVENT_STRATEGY_CHAMPION_SELECTED,
    EVENT_STRATEGY_POPULATION_EVOLVED,
    event_bus,
)
from core.types import BacktestResult, StrategyGenome, StrategySpecies
from engine.genome import GenomeManager
from engine.vectorized_backtester import VectorizedBacktester


class PopulationManager:
    """
    Manages the 96-strategy evolutionary pool (24 per species).
    Ensures species quotas, seeds proven quantitative archetypes, and ranks candidates.
    """

    def __init__(
        self,
        population_size: int = 96,
        quota_per_species: int = 24,
    ) -> None:
        self.population_size = population_size
        self.quota_per_species = quota_per_species
        self.backtester = VectorizedBacktester()
        self.population: List[StrategyGenome] = []
        self.latest_results: Dict[str, BacktestResult] = {}
        self.generation: int = 0
        self.champion: Optional[StrategyGenome] = None

    def initialize_population(self) -> List[StrategyGenome]:
        """Creates the initial Generation 0 population of 96 strategies with proven seeds and random variants."""
        self.generation = 0
        self.population = []

        all_species = [
            StrategySpecies.MOMENTUM_TREND,
            StrategySpecies.MEAN_REVERSION,
            StrategySpecies.BREAKOUT_VOLATILITY,
            StrategySpecies.REGIME_ADAPTIVE,
        ]

        for species in all_species:
            # 1. Add proven heuristic seeds for each species
            seeds = self._get_heuristic_seeds(species, self.generation)
            self.population.extend(seeds)

            # 2. Fill remainder of species quota with randomized genomes
            needed = self.quota_per_species - len(seeds)
            for _ in range(max(0, needed)):
                rand_genome = GenomeManager.random_genome(species, generation=self.generation)
                self.population.append(rand_genome)

        logger.info(f"Initialized Generation {self.generation} with {len(self.population)} strategies across 4 species.")
        return self.population

    def evaluate_population(self, df: pd.DataFrame) -> List[BacktestResult]:
        """
        Executes vectorized backtests across all 96 strategies in the population.
        Updates fitness scores and identifies the population champion.
        """
        results: List[BacktestResult] = []
        self.latest_results = {}

        for genome in self.population:
            res = self.backtester.backtest(df, genome)
            genome.fitness_score = res.fitness_score
            self.latest_results[genome.strategy_id] = res
            results.append(res)

        # Sort results by fitness score descending
        results.sort(key=lambda r: r.fitness_score, reverse=True)

        if results:
            best_res = results[0]
            for g in self.population:
                if g.strategy_id == best_res.strategy_id:
                    self.champion = g
                    break

            logger.info(
                f"Generation {self.generation} Evaluated | Champion: {best_res.strategy_id} ({best_res.species.value}) "
                f"| Sharpe: {best_res.sharpe_ratio:.2f} | PF: {best_res.profit_factor:.2f} | MDD: {best_res.max_drawdown:.1%} | Fitness: {best_res.fitness_score:.3f}"
            )

            event_bus.publish(EVENT_STRATEGY_CHAMPION_SELECTED, {
                "strategy_id": best_res.strategy_id,
                "species": best_res.species.value,
                "fitness_score": best_res.fitness_score,
                "sharpe_ratio": best_res.sharpe_ratio,
                "generation": self.generation,
            })

            event_bus.publish(EVENT_STRATEGY_POPULATION_EVOLVED, {
                "generation": self.generation,
                "population_count": len(self.population),
                "top_fitness": best_res.fitness_score,
                "top_strategy_id": best_res.strategy_id,
            })

        return results

    def get_species_champions(self) -> Dict[StrategySpecies, BacktestResult]:
        """Returns the highest fitness strategy result for each of the 4 species."""
        champs: Dict[StrategySpecies, BacktestResult] = {}
        for res in sorted(self.latest_results.values(), key=lambda r: r.fitness_score, reverse=True):
            if res.species not in champs:
                champs[res.species] = res
            if len(champs) == 4:
                break
        return champs

    @staticmethod
    def _get_heuristic_seeds(species: StrategySpecies, generation: int) -> List[StrategyGenome]:
        """Provides classic, battle-tested baseline strategies for seeding the genetic pool."""
        prefix = species.value[:3].upper()

        if species == StrategySpecies.MOMENTUM_TREND:
            return [
                StrategyGenome(
                    strategy_id=f"{prefix}-SEED-CLASSIC",
                    species=species,
                    entry_signal_threshold=0.30,
                    trend_filter_lookback=50,
                    rsi_oversold_bound=30.0,
                    rsi_overbought_bound=70.0,
                    stop_loss_atr_mult=1.8,
                    take_profit_atr_mult=3.6,
                    sentiment_filter_enabled=True,
                    generation=generation,
                ),
                StrategyGenome(
                    strategy_id=f"{prefix}-SEED-FAST",
                    species=species,
                    entry_signal_threshold=0.20,
                    trend_filter_lookback=21,
                    rsi_oversold_bound=35.0,
                    rsi_overbought_bound=65.0,
                    stop_loss_atr_mult=1.5,
                    take_profit_atr_mult=3.0,
                    sentiment_filter_enabled=False,
                    generation=generation,
                ),
            ]

        elif species == StrategySpecies.MEAN_REVERSION:
            return [
                StrategyGenome(
                    strategy_id=f"{prefix}-SEED-CONSERVATIVE",
                    species=species,
                    entry_signal_threshold=0.40,
                    trend_filter_lookback=50,
                    rsi_oversold_bound=25.0,
                    rsi_overbought_bound=75.0,
                    stop_loss_atr_mult=2.0,
                    take_profit_atr_mult=2.5,
                    sentiment_filter_enabled=True,
                    generation=generation,
                ),
                StrategyGenome(
                    strategy_id=f"{prefix}-SEED-AGGRESSIVE",
                    species=species,
                    entry_signal_threshold=0.25,
                    trend_filter_lookback=30,
                    rsi_oversold_bound=32.0,
                    rsi_overbought_bound=68.0,
                    stop_loss_atr_mult=1.5,
                    take_profit_atr_mult=2.0,
                    sentiment_filter_enabled=False,
                    generation=generation,
                ),
            ]

        elif species == StrategySpecies.BREAKOUT_VOLATILITY:
            return [
                StrategyGenome(
                    strategy_id=f"{prefix}-SEED-SQUEEZE",
                    species=species,
                    entry_signal_threshold=0.35,
                    trend_filter_lookback=20,
                    rsi_oversold_bound=30.0,
                    rsi_overbought_bound=70.0,
                    stop_loss_atr_mult=1.5,
                    take_profit_atr_mult=4.5,
                    sentiment_filter_enabled=True,
                    generation=generation,
                ),
                StrategyGenome(
                    strategy_id=f"{prefix}-SEED-RUNNER",
                    species=species,
                    entry_signal_threshold=0.25,
                    trend_filter_lookback=40,
                    rsi_oversold_bound=30.0,
                    rsi_overbought_bound=70.0,
                    stop_loss_atr_mult=2.0,
                    take_profit_atr_mult=5.5,
                    sentiment_filter_enabled=False,
                    generation=generation,
                ),
            ]

        elif species == StrategySpecies.REGIME_ADAPTIVE:
            return [
                StrategyGenome(
                    strategy_id=f"{prefix}-SEED-MACRO",
                    species=species,
                    entry_signal_threshold=0.30,
                    trend_filter_lookback=50,
                    rsi_oversold_bound=28.0,
                    rsi_overbought_bound=72.0,
                    stop_loss_atr_mult=1.8,
                    take_profit_atr_mult=3.5,
                    sentiment_filter_enabled=True,
                    generation=generation,
                ),
                StrategyGenome(
                    strategy_id=f"{prefix}-SEED-BALANCED",
                    species=species,
                    entry_signal_threshold=0.25,
                    trend_filter_lookback=34,
                    rsi_oversold_bound=30.0,
                    rsi_overbought_bound=70.0,
                    stop_loss_atr_mult=1.6,
                    take_profit_atr_mult=3.2,
                    sentiment_filter_enabled=True,
                    generation=generation,
                ),
            ]

        return []
