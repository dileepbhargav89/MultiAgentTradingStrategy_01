"""Orthogonal dimension normalizer mapping technical indicators into bounded [-1.0, +1.0] signals."""

from typing import Dict
import numpy as np
import pandas as pd
from indicators.momentum import calculate_macd, calculate_macd_acceleration, calculate_rsi
from indicators.trend import calculate_ema, calculate_ema_ribbon, calculate_ema_slope
from indicators.volatility import calculate_bollinger_bands
from indicators.volume import calculate_volume_divergence, calculate_vwap, calculate_session_vwap


class SignalNormalizer:
    """
    Normalizes 4 orthogonal indicator dimensions into continuous [-1.0, +1.0] scores:
    +1.0 = Maximum Bullish conviction
     0.0 = Perfectly Neutral / Chop
    -1.0 = Maximum Bearish conviction
    """

    @staticmethod
    def normalize_trend(df: pd.DataFrame) -> float:
        """
        Normalizes Trend dimension:
        - EMA 20/50/200 Ribbon alignment (weight 0.60)
        - EMA 50 Slope velocity (weight 0.40)
        """
        if len(df) < 50:
            return 0.0

        close = df["close"]
        current_close = close.iloc[-1]
        ribbon = calculate_ema_ribbon(df)
        ema20 = ribbon["ema_20"].iloc[-1]
        ema50 = ribbon["ema_50"].iloc[-1]

        # Stack scoring
        if len(df) >= 200:
            ema200 = ribbon["ema_200"].iloc[-1]
            if current_close > ema20 > ema50 > ema200:
                stack_score = 1.0
            elif current_close > ema20 > ema50:
                stack_score = 0.6
            elif current_close < ema20 < ema50 < ema200:
                stack_score = -1.0
            elif current_close < ema20 < ema50:
                stack_score = -0.6
            else:
                # Intertwined EMAs = Chop
                stack_score = 0.0
        else:
            if current_close > ema20 > ema50:
                stack_score = 0.8
            elif current_close < ema20 < ema50:
                stack_score = -0.8
            else:
                stack_score = 0.0

        # Slope velocity scoring
        slope = calculate_ema_slope(ribbon["ema_50"], window=5)

        trend_score = (0.60 * stack_score) + (0.40 * slope)
        return float(np.clip(trend_score, -1.0, 1.0))

    @staticmethod
    def normalize_momentum(df: pd.DataFrame) -> float:
        """
        Normalizes Momentum dimension:
        - Wilder's RSI (14) distance from 50 (weight 0.55)
        - MACD Histogram sign and acceleration (weight 0.45)
        """
        if len(df) < 26:
            return 0.0

        close = df["close"]
        rsi = calculate_rsi(close, 14).iloc[-1]
        # RSI 50 -> 0.0, RSI 75 -> +1.0, RSI 25 -> -1.0
        rsi_score = (rsi - 50.0) / 25.0
        rsi_score = float(np.clip(rsi_score, -1.0, 1.0))

        macd_dict = calculate_macd(close, 12, 26, 9)
        hist = macd_dict["histogram"]
        current_hist = hist.iloc[-1]
        hist_sign = 1.0 if current_hist > 0 else (-1.0 if current_hist < 0 else 0.0)
        accel = calculate_macd_acceleration(hist, window=3)

        macd_score = (0.50 * hist_sign) + (0.50 * accel)
        macd_score = float(np.clip(macd_score, -1.0, 1.0))

        momentum_score = (0.55 * rsi_score) + (0.45 * macd_score)
        return float(np.clip(momentum_score, -1.0, 1.0))

    @staticmethod
    def normalize_volatility(df: pd.DataFrame) -> float:
        """
        Normalizes Volatility / Mean-Reversion dimension:
        - Bollinger Bands %B position:
          Healthy Trend: %B between 0.55 and 0.85 -> +0.8
          Exhaustion Pump: %B > 1.0 -> Penalized toward 0.0 / short fade
          Healthy Downtrend: %B between 0.15 and 0.45 -> -0.8
          Exhaustion Dump: %B < 0.0 -> Penalized toward 0.0 / bounce
        """
        if len(df) < 20:
            return 0.0

        bb = calculate_bollinger_bands(df["close"], 20, 2.0)
        percent_b = float(bb["percent_b"].iloc[-1])

        # Centered mapping with exhaustion penalty
        if 0.50 <= percent_b <= 0.85:
            vol_score = (percent_b - 0.50) / 0.35  # 0.0 to +1.0
        elif 0.85 < percent_b <= 1.10:
            # Overextended: linear decay from +1.0 to 0.0
            vol_score = max(0.0, 1.0 - (percent_b - 0.85) * 4.0)
        elif percent_b > 1.10:
            # Extreme exhaustion: flip negative (mean-reversion fade signal)
            vol_score = max(-0.8, -(percent_b - 1.10) * 3.0)
        elif 0.15 <= percent_b < 0.50:
            vol_score = (percent_b - 0.50) / 0.35  # 0.0 to -1.0
        elif -0.10 < percent_b < 0.15:
            # Oversold decay: from -1.0 toward 0.0
            vol_score = min(0.0, -1.0 + (0.15 - percent_b) * 4.0)
        else:
            # Extreme oversold bounce: flip positive
            vol_score = min(0.8, (0.0 - percent_b) * 3.0)

        return float(np.clip(vol_score, -1.0, 1.0))

    @staticmethod
    def normalize_volume(df: pd.DataFrame) -> float:
        """
        Normalizes Volume & Fair Value dimension:
        - Price vs Cumulative VWAP (weight 0.50)
        - VWMA vs SMA(20) Volume Accumulation Divergence (weight 0.50)
        """
        if len(df) < 20:
            return 0.0

        current_close = float(df["close"].iloc[-1])
        vwap = float(calculate_session_vwap(df, session_hours=24).iloc[-1])

        vwap_score = 1.0 if current_close > vwap else (-1.0 if current_close < vwap else 0.0)
        divergence_score = calculate_volume_divergence(df, period=20)

        vol_score = (0.50 * vwap_score) + (0.50 * divergence_score)
        return float(np.clip(vol_score, -1.0, 1.0))

    @classmethod
    def normalize_all(cls, df: pd.DataFrame) -> Dict[str, float]:
        """Calculates normalized scores across all 4 orthogonal dimensions."""
        return {
            "trend": cls.normalize_trend(df),
            "momentum": cls.normalize_momentum(df),
            "volatility": cls.normalize_volatility(df),
            "volume": cls.normalize_volume(df),
        }
