"""Statistical volatility regime classifier: Compression, Expansion, and Chaos."""

from typing import Dict, Optional, Tuple
import numpy as np
import pandas as pd
from scipy import stats
from core.types import VolatilityRegime
from indicators.volatility import calculate_bollinger_bands
from models.volatility_models import calculate_parkinson_volatility


class RegimeClassifier:
    """
    Classifies market state into 3 distinct quantitative regimes based on
    rolling Parkinson volatility percentile ranks and Bollinger Bandwidth compression.
    """

    @staticmethod
    def calculate_volatility_percentile(
        df: pd.DataFrame,
        current_vol: float,
        lookback_candles: int = 720,  # 30 days of 1h
        rolling_window: int = 24,
    ) -> float:
        """
        Calculates empirical percentile rank (0 to 100) of current volatility vs history.
        """
        if df is None or len(df) < 50:
            return 50.0

        hist_slice = df.iloc[-lookback_candles:] if len(df) >= lookback_candles else df
        # Compute historical rolling Parkinson values in steps of 4 hours
        hist_vols = []
        step = max(1, len(hist_slice) // 40)
        for i in range(rolling_window, len(hist_slice), step):
            sub_df = hist_slice.iloc[max(0, i - rolling_window):i]
            v = calculate_parkinson_volatility(sub_df, window=rolling_window, timeframe="1h")
            if v > 0:
                hist_vols.append(v)

        if len(hist_vols) < 5:
            return 50.0

        pct_rank = float(stats.percentileofscore(hist_vols, current_vol))
        return float(np.clip(pct_rank, 0.0, 100.0))

    @staticmethod
    def detect_bollinger_squeeze(df: pd.DataFrame, period: int = 20) -> Tuple[bool, float]:
        """
        Detects volatility compression via Bollinger Bandwidth.
        Bandwidth = (Upper - Lower) / Middle
        """
        if len(df) < period:
            return False, 0.05

        bb = calculate_bollinger_bands(df["close"], period, 2.0)
        bw_series = bb["bandwidth"].dropna()
        if len(bw_series) == 0:
            return False, 0.05

        current_bw = float(bw_series.iloc[-1])
        # In crypto, bandwidth < 0.03 (3% spread between upper and lower) is extreme compression
        is_squeezed = current_bw <= 0.035
        return is_squeezed, current_bw

    @classmethod
    def classify_regime(
        cls,
        df: pd.DataFrame,
        current_parkinson_vol: float,
    ) -> Tuple[VolatilityRegime, float, bool]:
        """
        Classifies regime, returns:
        - regime: VolatilityRegime
        - vol_percentile: float (0 to 100)
        - is_breakout_imminent: bool
        """
        percentile = cls.calculate_volatility_percentile(df, current_parkinson_vol)
        is_squeezed, bandwidth = cls.detect_bollinger_squeeze(df)

        is_breakout_imminent = (percentile <= 20.0 and is_squeezed) or bandwidth <= 0.025

        if percentile < 25.0 or is_breakout_imminent:
            regime = VolatilityRegime.LOW_VOL_COMPRESSION
        elif percentile > 75.0:
            regime = VolatilityRegime.HIGH_VOL_CHAOS
        else:
            regime = VolatilityRegime.TRENDING_EXPANSION

        return regime, percentile, is_breakout_imminent
