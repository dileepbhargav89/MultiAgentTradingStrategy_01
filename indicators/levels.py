"""Structural key levels, dynamic support/resistance, and invalidation calculation."""

from typing import List, Tuple
import numpy as np
import pandas as pd
from indicators.trend import calculate_ema
from indicators.volatility import calculate_atr, calculate_bollinger_bands


class KeyLevelsCalculator:
    """
    Computes structural support/resistance zones and exact invalidation pricing.
    """

    @staticmethod
    def calculate_swing_levels(df: pd.DataFrame, lookback: int = 20) -> Tuple[float, float]:
        """Returns lowest low and highest high over lookback window."""
        if len(df) == 0:
            return 0.0, 0.0

        window = df.iloc[-lookback:] if len(df) >= lookback else df
        swing_low = float(window["low"].min())
        swing_high = float(window["high"].max())
        return swing_low, swing_high

    @staticmethod
    def calculate_support_resistance_zones(df: pd.DataFrame) -> Tuple[List[float], List[float]]:
        """
        Derives key institutional support and resistance levels from:
        - Swing Lows and Highs (lookback 20 and 50)
        - Bollinger Bands
        - 200 EMA
        """
        if len(df) < 20:
            return [], []

        current_close = float(df["close"].iloc[-1])
        sw_low_20, sw_high_20 = KeyLevelsCalculator.calculate_swing_levels(df, 20)
        sw_low_50, sw_high_50 = KeyLevelsCalculator.calculate_swing_levels(df, min(len(df), 50))

        bb = calculate_bollinger_bands(df["close"], 20, 2.0)
        bb_upper = float(bb["upper"].iloc[-1])
        bb_lower = float(bb["lower"].iloc[-1])

        levels_pool = {sw_low_20, sw_high_20, sw_low_50, sw_high_50, bb_upper, bb_lower}

        if len(df) >= 200:
            ema200 = float(calculate_ema(df["close"], 200).iloc[-1])
            levels_pool.add(ema200)

        supports = sorted([p for p in levels_pool if p < current_close], reverse=True)[:3]
        resistances = sorted([p for p in levels_pool if p > current_close])[:3]

        return supports, resistances

    @staticmethod
    def calculate_invalidation_price(
        df: pd.DataFrame,
        is_bullish: bool,
        atr_value: float,
        lookback: int = 20,
    ) -> float:
        """
        Calculates setup invalidation price:
        - For Longs: max(swing_low, current_close - 2.0 * ATR)
        - For Shorts: min(swing_high, current_close + 2.0 * ATR)
        """
        if len(df) == 0:
            return 0.0

        current_close = float(df["close"].iloc[-1])
        swing_low, swing_high = KeyLevelsCalculator.calculate_swing_levels(df, lookback)

        if is_bullish:
            atr_stop = current_close - (2.0 * atr_value)
            # Add institutional liquidity buffer below swing low to avoid stop hunts
            buffered_swing = swing_low - (0.20 * atr_value)
            invalidation = min(buffered_swing, current_close - (1.2 * atr_value)) if buffered_swing < current_close else atr_stop
            # Invalidation must always be strictly below current close
            if invalidation >= current_close:
                invalidation = current_close - (1.5 * atr_value)
        else:
            atr_stop = current_close + (2.0 * atr_value)
            buffered_swing = swing_high + (0.20 * atr_value)
            invalidation = max(buffered_swing, current_close + (1.2 * atr_value)) if buffered_swing > current_close else atr_stop
            if invalidation <= current_close:
                invalidation = current_close + (1.5 * atr_value)

        return float(invalidation)

    @staticmethod
    def calculate_risk_targets(
        entry_price: float,
        invalidation_price: float,
        r1: float = 2.0,
        r2: float = 3.5,
    ) -> Tuple[float, float]:
        """Calculates 2.0R and 3.5R profit targets based on distance to invalidation."""
        risk = abs(entry_price - invalidation_price)
        if entry_price >= invalidation_price:  # Long
            return entry_price + (r1 * risk), entry_price + (r2 * risk)
        else:  # Short
            return entry_price - (r1 * risk), entry_price - (r2 * risk)
