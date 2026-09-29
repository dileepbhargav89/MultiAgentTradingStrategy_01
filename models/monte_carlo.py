"""Monte Carlo permutation test: 1,000-shuffle bootstrap trade order analysis and Risk of Ruin."""

from typing import List, Optional
import numpy as np
import pandas as pd

from core.types import MonteCarloReport, StrategyGenome
from engine.species_strategies import SpeciesStrategyBuilder


class MonteCarloTester:
    """
    Performs 1,000-run bootstrap permutations on trade returns to evaluate
    tail-risk under adverse sequence clustering (streaks of losses).
    Calculates 95th-percentile drawdown and risk of ruin.
    """

    def __init__(
        self,
        permutations: int = 1000,
        max_allowed_95th_dd: float = 0.18,  # 18% max acceptable worst-case drawdown
        ruin_threshold: float = 0.20,       # 20% drawdown constitutes ruin
        max_allowed_ruin_prob: float = 1.0, # 1.0% max acceptable risk of ruin
    ) -> None:
        self.permutations = permutations
        self.max_allowed_95th_dd = max_allowed_95th_dd
        self.ruin_threshold = ruin_threshold
        self.max_allowed_ruin_prob = max_allowed_ruin_prob

    def run_permutation_test(
        self,
        df: pd.DataFrame,
        genome: StrategyGenome,
    ) -> MonteCarloReport:
        """
        Extracts active trade returns for the genome on df, reshuffles them
        1,000 times, and assesses catastrophic tail risk.
        """
        # 1. Compute discrete trade/bar returns
        signals = SpeciesStrategyBuilder.generate_signals(df, genome)
        positions = np.roll(signals, 1)
        positions[0] = 0.0

        c = df["close"].values
        prev_c = np.roll(c, 1)
        prev_c[0] = c[0]
        valid_mask = (c > 0) & (prev_c > 0)
        log_ret = np.zeros(len(c), dtype=float)
        log_ret[valid_mask] = np.log(c[valid_mask] / prev_c[valid_mask])

        pos_changes = np.abs(positions - np.roll(positions, 1))
        # Base friction with chaos regime multiplier
        base_friction = 0.0005
        ret_vol = float(np.std(log_ret)) if len(log_ret) > 10 else 0.01
        if ret_vol > 0.03:  # High vol → 3x slippage
            friction_rate = base_friction * 3.0
        elif ret_vol > 0.015:
            friction_rate = base_friction * 1.5
        else:
            friction_rate = base_friction
        friction = pos_changes * friction_rate
        strat_returns = (positions * log_ret) - friction

        active_returns = strat_returns[positions != 0]

        # If too few active trades, return default safe report
        if len(active_returns) < 5:
            return MonteCarloReport(
                strategy_id=genome.strategy_id,
                permutations_tested=0,
                drawdown_95th_percentile=0.0,
                max_drawdown_observed=0.0,
                risk_of_ruin_pct=0.0,
                probability_of_profit=0.5,
                is_disqualified=True,
                rejection_reason="INSUFFICIENT_ACTIVE_TRADES_FOR_MC (<5)",
            )

        # 2. Vectorized 1,000 True Permutations (shuffle without replacement)
        rng = np.random.default_rng()
        n_samples = len(active_returns)
        simulated_returns = np.zeros((self.permutations, n_samples))
        for i in range(self.permutations):
            simulated_returns[i] = rng.permutation(active_returns)

        # Cumulative equity curves: shape (permutations, n_samples)
        cum_ret = np.cumsum(simulated_returns, axis=1)
        equities = np.exp(cum_ret)

        # Running max for each permutation
        running_max = np.maximum.accumulate(equities, axis=1)
        drawdowns = (running_max - equities) / running_max

        # Max drawdown per permutation: shape (permutations,)
        max_dds = np.max(drawdowns, axis=1)

        # Final returns per permutation
        final_returns = cum_ret[:, -1]

        # 3. Compute Risk Metrics
        dd_95th = float(np.percentile(max_dds, 95))
        worst_dd = float(np.max(max_dds))
        ruin_count = np.sum(max_dds >= self.ruin_threshold)
        risk_of_ruin_pct = float((ruin_count / self.permutations) * 100.0)
        prob_profit = float(np.mean(final_returns > 0))

        # 4. Disqualification Gate
        is_disqualified = False
        rejection_reason: Optional[str] = None

        if dd_95th > self.max_allowed_95th_dd:
            is_disqualified = True
            rejection_reason = f"EXCESSIVE_95TH_PERCENTILE_DRAWDOWN ({dd_95th:.1%} > {self.max_allowed_95th_dd:.1%})"
        elif risk_of_ruin_pct > self.max_allowed_ruin_prob:
            is_disqualified = True
            rejection_reason = f"UNACCEPTABLE_RISK_OF_RUIN ({risk_of_ruin_pct:.2f}% > {self.max_allowed_ruin_prob:.1f}%)"

        return MonteCarloReport(
            strategy_id=genome.strategy_id,
            permutations_tested=self.permutations,
            drawdown_95th_percentile=round(dd_95th, 4),
            max_drawdown_observed=round(worst_dd, 4),
            risk_of_ruin_pct=round(risk_of_ruin_pct, 2),
            probability_of_profit=round(prob_profit, 4),
            is_disqualified=is_disqualified,
            rejection_reason=rejection_reason,
        )
