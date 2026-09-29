"""Quantitative derivatives positioning analyzer: Funding Z-score, OI velocity, and 4-quadrant mapping."""

from typing import Optional, Tuple
import numpy as np
import pandas as pd
from core.types import CrowdingBias, PositioningQuadrant


class PositioningAnalyzer:
    """
    Analyzes derivatives positioning metrics to identify institutional accumulation vs retail crowding,
    liquidation cascade vulnerabilities, and squeeze conditions.
    """

    @staticmethod
    def calculate_funding_zscore(
        current_rate: float,
        history_df: pd.DataFrame,
    ) -> float:
        """
        Calculates rolling Z-score of the 8-hour funding rate:
        Z = (Current_Rate - Mean_30d) / Std_30d
        """
        if history_df is None or history_df.empty or "funding_rate" not in history_df.columns:
            # Baseline baseline rate is 0.0001 (0.01%)
            return 0.0

        rates = history_df["funding_rate"].dropna()
        if len(rates) < 5:
            return 0.0

        mean = float(rates.mean())
        std = float(rates.std())

        if std == 0.0 or np.isnan(std):
            return 0.0

        zscore = (current_rate - mean) / std
        return float(np.clip(zscore, -5.0, 5.0))

    @staticmethod
    def calculate_oi_velocity(oi_df: pd.DataFrame) -> Tuple[float, float]:
        """
        Computes 4-hour and 24-hour Open Interest percentage change.
        Returns: (oi_change_4h_pct, oi_change_24h_pct)
        """
        if oi_df is None or oi_df.empty or "sum_open_interest" not in oi_df.columns:
            return 0.0, 0.0

        oi_series = oi_df["sum_open_interest"].dropna()
        n = len(oi_series)
        if n < 2:
            return 0.0, 0.0

        current_oi = float(oi_series.iloc[-1])
        if current_oi <= 0.0:
            return 0.0, 0.0

        # 4-hour change (4 rows back for 1h candles)
        idx_4h = max(0, n - 5)
        oi_4h_ago = float(oi_series.iloc[idx_4h])
        chg_4h = (current_oi - oi_4h_ago) / oi_4h_ago if oi_4h_ago > 0 else 0.0

        # 24-hour change (24 rows back for 1h candles)
        idx_24h = max(0, n - 25)
        oi_24h_ago = float(oi_series.iloc[idx_24h])
        chg_24h = (current_oi - oi_24h_ago) / oi_24h_ago if oi_24h_ago > 0 else 0.0

        return float(chg_4h), float(chg_24h)

    @staticmethod
    def classify_positioning_quadrant(
        price_change_24h_pct: float,
        oi_change_24h_pct: float,
        threshold: float = 0.005,
    ) -> PositioningQuadrant:
        """
        Classifies market regime into classical 4-quadrant derivatives matrix:
        - Price UP, OI UP     -> LONG_ACCUMULATION
        - Price UP, OI DOWN   -> SHORT_COVERING
        - Price DOWN, OI UP   -> SHORT_ACCUMULATION
        - Price DOWN, OI DOWN -> LONG_LIQUIDATION
        """
        p_up = price_change_24h_pct > threshold
        p_down = price_change_24h_pct < -threshold
        oi_up = oi_change_24h_pct > threshold
        oi_down = oi_change_24h_pct < -threshold

        if p_up and oi_up:
            return PositioningQuadrant.LONG_ACCUMULATION
        elif p_up and oi_down:
            return PositioningQuadrant.SHORT_COVERING
        elif p_down and oi_up:
            return PositioningQuadrant.SHORT_ACCUMULATION
        elif p_down and oi_down:
            return PositioningQuadrant.LONG_LIQUIDATION
        else:
            return PositioningQuadrant.BALANCED

    @staticmethod
    def calculate_crowding_and_penalty(
        funding_zscore: float,
        oi_change_24h_pct: float,
        top_trader_ls: float,
        fgi_value: int,
    ) -> Tuple[CrowdingBias, float, Optional[str]]:
        """
        Evaluates leverage crowding, sets crowding penalty factor [0.0, 0.50],
        and flags imminent squeeze warnings.
        """
        penalty = 0.0
        warning = None

        # Long Crowding Conditions: High funding + rising OI + Greed
        if funding_zscore >= 1.5:
            bias = CrowdingBias.CROWDED_LONG
            # Base penalty scales with funding extremity
            penalty += (funding_zscore - 1.5) * 0.12

            signals = [
                funding_zscore >= 1.5,
                oi_change_24h_pct > 0.04,
                fgi_value >= 75,
                top_trader_ls < 0.90,
            ]

            if oi_change_24h_pct > 0.04:
                penalty += 0.10

            if fgi_value >= 75:
                penalty += 0.08

            # Smart money divergence: retail long (funding high) but top traders short
            if top_trader_ls < 0.90:
                penalty += 0.10
                warning = "TOP_TRADERS_SHORT_DIVERGENCE"

            # Compound crowding multiplier when >= 3 indicators align
            signal_count = sum(signals)
            if signal_count >= 3:
                penalty *= (1.0 + 0.20 * (signal_count - 2))

            # Tighter squeeze threshold: Z >= 2.0 and OI > 2%
            if funding_zscore >= 2.0 and oi_change_24h_pct > 0.02:
                warning = "IMMINENT_LONG_SQUEEZE"

        # Short Crowding Conditions: Deep negative funding + rising OI + Fear
        elif funding_zscore <= -1.5:
            bias = CrowdingBias.CROWDED_SHORT
            penalty += abs(funding_zscore + 1.5) * 0.12

            signals = [
                funding_zscore <= -1.5,
                oi_change_24h_pct > 0.04,
                fgi_value <= 25,
                top_trader_ls > 1.15,
            ]

            if oi_change_24h_pct > 0.04:
                penalty += 0.10

            if fgi_value <= 25:
                penalty += 0.08

            if top_trader_ls > 1.15:
                penalty += 0.10
                warning = "TOP_TRADERS_LONG_DIVERGENCE"

            # Compound crowding multiplier when >= 3 indicators align
            signal_count = sum(signals)
            if signal_count >= 3:
                penalty *= (1.0 + 0.20 * (signal_count - 2))

            # Tighter squeeze threshold: Z <= -2.0 and OI > 2%
            if funding_zscore <= -2.0 and oi_change_24h_pct > 0.02:
                warning = "IMMINENT_SHORT_SQUEEZE"

        else:
            bias = CrowdingBias.BALANCED
            penalty = 0.0

        clamped_penalty = float(np.clip(penalty, 0.0, 0.50))
        return bias, clamped_penalty, warning
