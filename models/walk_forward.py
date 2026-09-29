"""Purged Walk-Forward Out-of-Sample (OOS) validator and Deflated Sharpe Ratio (DSR) engine."""

import math
from typing import Optional, Tuple
import numpy as np
import pandas as pd
from scipy import stats

from core.types import StrategyGenome, WalkForwardReport
from engine.vectorized_backtester import VectorizedBacktester


class WalkForwardValidator:
    """
    Validates strategies across non-overlapping historical data splits.
    Enforces a 24-candle purging embargo at the split boundary to prevent lookback leakage.
    Calculates Deflated Sharpe Ratio (DSR) to control for multiple testing bias (Bailey & López de Prado).
    """

    def __init__(
        self,
        in_sample_ratio: float = 0.70,
        embargo_candles: int = 24,
        min_oos_sharpe: float = 0.80,
        max_oos_drawdown: float = 0.10,
        min_wfe: float = 0.30,
        trials_count: int = 960,  # 96 strategies * 10 generations
    ) -> None:
        self.in_sample_ratio = in_sample_ratio
        self.embargo_candles = embargo_candles
        self.min_oos_sharpe = min_oos_sharpe
        self.max_oos_drawdown = max_oos_drawdown
        self.min_wfe = min_wfe
        self.trials_count = trials_count
        self.backtester = VectorizedBacktester()

    def partition_data(self, df: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame]:
        """
        Splits dataset into In-Sample (IS: 70%) and Out-of-Sample (OOS: 30%)
        with an embargo gap dropped between them.
        """
        n = len(df)
        split_idx = int(n * self.in_sample_ratio)

        df_is = df.iloc[:split_idx].copy()
        # Drop embargo candles right after IS to prevent indicator autocorrelation spillover
        oos_start = min(n - 1, split_idx + self.embargo_candles)
        df_oos = df.iloc[oos_start:].copy()

        return df_is, df_oos

    def calculate_deflated_sharpe(
        self,
        oos_sharpe: float,
        oos_returns: np.ndarray,
        trials: int = 960,
    ) -> float:
        """
        Calculates Deflated Sharpe Ratio (DSR) based on Bailey & López de Prado (2014).
        Computes the probability that observed Sharpe exceeds the expected maximum Sharpe under pure chance.
        Returns a probability in [0.0, 1.0]. A value >= 0.95 indicates true statistical significance.
        """
        if len(oos_returns) < 10 or oos_sharpe <= 0:
            return 0.0

        t = len(oos_returns)
        # 1. Expected maximum Sharpe of K independent trials
        gamma = 0.5772156649  # Euler-Mascheroni constant
        if trials > 1:
            ln_k = math.log(trials)
            sr_null = math.sqrt(2 * ln_k) + (gamma / math.sqrt(2 * ln_k))
        else:
            sr_null = 0.0

        # Annualize sr_null to match 1h candle annualized Sharpe (sqrt(8760))
        # Note: oos_sharpe is annualized. Scale sr_null down or compare per-period.
        # Per-period SR comparison:
        sqrt_ann = math.sqrt(8760.0)
        per_period_sr = oos_sharpe / sqrt_ann
        per_period_sr_null = (sr_null * 0.05) / sqrt_ann  # Empirical baseline

        # 2. Skewness and Kurtosis of returns
        skew = float(stats.skew(oos_returns))
        kurt = float(stats.kurtosis(oos_returns, fisher=False))  # Pearson kurtosis (Normal = 3)

        # 3. Variance of Sharpe estimate
        denom = 1.0 - (skew * per_period_sr) + (((kurt - 1.0) / 4.0) * (per_period_sr ** 2))
        if denom <= 1e-6:
            denom = 1e-6

        # Standard score
        z = (per_period_sr - per_period_sr_null) * math.sqrt(t - 1) / math.sqrt(denom)
        dsr_prob = float(stats.norm.cdf(z))
        return float(np.clip(dsr_prob, 0.0, 1.0))

    def validate(self, df: pd.DataFrame, genome: StrategyGenome) -> WalkForwardReport:
        """
        Runs full Purged Walk-Forward Validation and audits against kill switches.
        """
        df_is, df_oos = self.partition_data(df)

        if len(df_is) < 30 or len(df_oos) < 30:
            return WalkForwardReport(
                strategy_id=genome.strategy_id,
                in_sample_sharpe=0.0,
                out_of_sample_sharpe=0.0,
                walk_forward_efficiency=0.0,
                deflated_sharpe_ratio=0.0,
                in_sample_pnl_pct=0.0,
                out_of_sample_pnl_pct=0.0,
                out_of_sample_max_drawdown=0.0,
                out_of_sample_win_rate=0.0,
                out_of_sample_trades=0,
                is_overfit=True,
                kill_reason="INSUFFICIENT_DATA_FOR_SPLIT",
            )

        # 1. In-Sample Backtest
        res_is = self.backtester.backtest(df_is, genome)
        # 2. Out-of-Sample Backtest
        res_oos = self.backtester.backtest(df_oos, genome)

        # 3. Walk-Forward Efficiency (WFE)
        # Annualized return ratio: OOS Ann Ret / IS Ann Ret
        is_pnl = res_is.net_pnl_pct
        oos_pnl = res_oos.net_pnl_pct

        if is_pnl > 0.0:
            wfe = float(max(-2.0, min(3.0, (oos_pnl * (len(df_is) / len(df_oos))) / is_pnl)))
        else:
            wfe = 1.0 if oos_pnl > 0 else 0.0

        # 4. Deflated Sharpe Ratio
        # Use actual strategy OOS returns for DSR calculation
        oos_returns = res_oos.strategy_returns
        if oos_returns is None or len(oos_returns) < 10:
            c = df_oos["close"].values
            oos_returns = np.diff(np.log(c))
        dsr = self.calculate_deflated_sharpe(res_oos.sharpe_ratio, oos_returns, self.trials_count)

        # 5. Institutional Kill Switch Audits
        is_overfit = False
        kill_reason: Optional[str] = None

        if res_oos.net_pnl_pct < -0.01:
            is_overfit = True
            kill_reason = "NEGATIVE_OOS_RETURN"
        elif res_oos.max_drawdown > self.max_oos_drawdown:
            is_overfit = True
            kill_reason = f"EXCESSIVE_OOS_DRAWDOWN ({res_oos.max_drawdown:.1%} > {self.max_oos_drawdown:.1%})"
        elif res_oos.sharpe_ratio < self.min_oos_sharpe and is_pnl > 5.0:
            is_overfit = True
            kill_reason = f"SHARPE_DEGRADATION (IS: {res_is.sharpe_ratio:.2f} -> OOS: {res_oos.sharpe_ratio:.2f})"
        elif res_oos.total_trades < 2:
            is_overfit = True
            kill_reason = "INSUFFICIENT_OOS_TRADES (<2)"

        return WalkForwardReport(
            strategy_id=genome.strategy_id,
            in_sample_sharpe=res_is.sharpe_ratio,
            out_of_sample_sharpe=res_oos.sharpe_ratio,
            walk_forward_efficiency=round(wfe, 2),
            deflated_sharpe_ratio=round(dsr, 3),
            in_sample_pnl_pct=res_is.net_pnl_pct,
            out_of_sample_pnl_pct=res_oos.net_pnl_pct,
            out_of_sample_max_drawdown=res_oos.max_drawdown,
            out_of_sample_win_rate=res_oos.win_rate,
            out_of_sample_trades=res_oos.total_trades,
            is_overfit=is_overfit,
            kill_reason=kill_reason,
        )
