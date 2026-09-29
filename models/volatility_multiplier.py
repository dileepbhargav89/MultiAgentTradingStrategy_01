"""Dynamic volatility multiplier calculator for risk sizing and stop-loss distance scaling."""

from typing import Tuple
import numpy as np
from core.types import VolatilityRegime


class VolatilityMultiplierCalculator:
    """
    Translates statistical volatility regimes and percentile ranks into:
    1. Capital sizing multiplier (M_vol): Sizing scales down as chaos rises.
    2. ATR stop distance multiplier (M_stop): Stop distances widen during high volatility.
    """

    @staticmethod
    def calculate_multipliers(
        regime: VolatilityRegime,
        volatility_percentile: float,
    ) -> Tuple[float, float]:
        """
        Returns:
            - size_multiplier: float [0.40, 1.25]
            - atr_stop_multiplier: float [1.20, 2.50]
        """
        if regime == VolatilityRegime.LOW_VOL_COMPRESSION:
            # Breakout direction unknown — maintain neutral/slight defensive sizing
            size_multiplier = 0.90
            atr_stop_multiplier = 1.30

        elif regime == VolatilityRegime.HIGH_VOL_CHAOS:
            # Drop size down to 0.40 for extreme 99th percentile chaos
            excess = max(0.0, volatility_percentile - 75.0)
            size_multiplier = max(0.40, 0.60 - (excess * 0.008))
            atr_stop_multiplier = min(2.50, 2.00 + (excess * 0.02))

        else:  # TRENDING_EXPANSION
            # Smooth interpolation around 1.00
            diff = volatility_percentile - 50.0
            size_multiplier = 1.00 - (diff * 0.006)
            atr_stop_multiplier = 1.80 + (diff * 0.008)

        clamped_size = float(np.clip(size_multiplier, 0.40, 1.25))
        clamped_stop = float(np.clip(atr_stop_multiplier, 1.20, 2.50))
        return clamped_size, clamped_stop
