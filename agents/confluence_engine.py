"""Multi-Timeframe Confluence Engine with orthogonal dimension synthesis and counter-trend damping."""

from typing import Dict, Tuple
import numpy as np
import pandas as pd
from core.types import MarketBias
from indicators.normalizer import SignalNormalizer


DIMENSION_WEIGHTS = {
    "trend": 0.35,
    "momentum": 0.30,
    "volatility": 0.20,
    "volume": 0.15,
}

TIMEFRAME_WEIGHTS = {
    "15m": 0.15,
    "1h": 0.35,
    "4h": 0.35,
    "1d": 0.15,
}


class ConfluenceEngine:
    """
    Synthesizes multi-timeframe signals into a single continuous conviction metric [-1.0, +1.0].
    Applies counter-trend penalty when lower timeframe opposes institutional higher timeframe trend.
    """

    def __init__(
        self,
        dimension_weights: Dict[str, float] = None,
        timeframe_weights: Dict[str, float] = None,
    ) -> None:
        self.dim_weights = dimension_weights or DIMENSION_WEIGHTS
        self.tf_weights = timeframe_weights or TIMEFRAME_WEIGHTS

    def calculate_timeframe_score(self, df: pd.DataFrame) -> Tuple[float, Dict[str, float]]:
        """
        Calculates the single composite score for one timeframe from its 4 orthogonal dimensions.
        """
        if df is None or len(df) < 20:
            return 0.0, {"trend": 0.0, "momentum": 0.0, "volatility": 0.0, "volume": 0.0}

        dims = SignalNormalizer.normalize_all(df)
        score = sum(dims[d] * self.dim_weights.get(d, 0.25) for d in dims)
        return float(np.clip(score, -1.0, 1.0)), dims

    def calculate_confluence(
        self,
        timeframe_dfs: Dict[str, pd.DataFrame]
    ) -> Tuple[float, MarketBias, Dict[str, float], Dict[str, float]]:
        """
        Computes composite multi-timeframe confluence.

        Returns:
            - overall_confluence: float [-1.0, 1.0]
            - bias: MarketBias
            - timeframe_scores: Dict[str, float]
            - aggregate_dimensions: Dict[str, float]
        """
        tf_scores: Dict[str, float] = {}
        all_dims: Dict[str, Dict[str, float]] = {}

        for tf, df in timeframe_dfs.items():
            tf_score, dims = self.calculate_timeframe_score(df)
            tf_scores[tf] = tf_score
            all_dims[tf] = dims

        # Counter-trend damping: Prevent retail trap entries
        score_4h = tf_scores.get("4h", 0.0)
        score_15m = tf_scores.get("15m", 0.0)
        score_1h = tf_scores.get("1h", 0.0)

        # 15M vs 4H proportional damping
        if (score_4h < -0.35 and score_15m > 0.35) or (score_4h > 0.35 and score_15m < -0.35):
            divergence = abs(score_4h - score_15m)
            damp_factor = max(0.30, min(0.70, 1.0 - divergence * 0.5))
            tf_scores["15m"] = score_15m * damp_factor

        # 1H vs 4H counter-trend damping
        if score_4h < -0.35 and score_1h > 0.35:
            # 4H bear + 1H counter-trend bounce → damp 1H by 40%
            tf_scores["1h"] = score_1h * 0.60
        elif score_4h > 0.35 and score_1h < -0.35:
            # 4H bull + 1H dip → damp 1H dip signal by 40%
            tf_scores["1h"] = score_1h * 0.60

        # Weighted aggregate across active timeframes
        total_confluence = 0.0
        weight_sum = 0.0

        for tf, score in tf_scores.items():
            w = self.tf_weights.get(tf, 0.25)
            total_confluence += score * w
            weight_sum += w

        overall_confluence = total_confluence / weight_sum if weight_sum > 0 else 0.0
        overall_confluence = float(np.clip(overall_confluence, -1.0, 1.0))

        # Average dimensions across timeframes for explainability
        aggregate_dims = {"trend": 0.0, "momentum": 0.0, "volatility": 0.0, "volume": 0.0}
        for d in aggregate_dims:
            dim_values = [all_dims[tf][d] for tf in all_dims if d in all_dims[tf]]
            aggregate_dims[d] = float(np.mean(dim_values)) if dim_values else 0.0

        # Correlation dampener: If trend and momentum strongly agree,
        # they likely measure the same underlying signal. Apply diminishing returns.
        trend_avg = aggregate_dims.get("trend", 0.0)
        momentum_avg = aggregate_dims.get("momentum", 0.0)
        if abs(trend_avg) > 0.5 and abs(momentum_avg) > 0.5:
            if (trend_avg > 0 and momentum_avg > 0) or (trend_avg < 0 and momentum_avg < 0):
                correlation_penalty = 0.08
                overall_confluence = float(np.clip(
                    overall_confluence - np.sign(overall_confluence) * correlation_penalty,
                    -1.0, 1.0
                ))

        # Determine Market Bias category
        if overall_confluence >= 0.60:
            bias = MarketBias.STRONG_BULLISH
        elif overall_confluence >= 0.25:
            bias = MarketBias.BULLISH
        elif overall_confluence <= -0.60:
            bias = MarketBias.STRONG_BEARISH
        elif overall_confluence <= -0.25:
            bias = MarketBias.BEARISH
        else:
            bias = MarketBias.NEUTRAL

        return overall_confluence, bias, tf_scores, aggregate_dims
