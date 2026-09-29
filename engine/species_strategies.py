"""Vectorized strategy signal generators for the 4 core crypto species."""

from typing import Optional
import numpy as np
import pandas as pd

from core.types import StrategyGenome, StrategySpecies, VolatilityRegime
from indicators.momentum import calculate_rsi
from indicators.trend import calculate_ema, calculate_supertrend
from indicators.volatility import calculate_atr, calculate_bollinger_bands


class SpeciesStrategyBuilder:
    """
    Computes vectorized trading signals for the 4 evolutionary species.
    Outputs a numpy array or Series of signals in {-1.0, 0.0, +1.0}:
      +1.0 = Long
      -1.0 = Short
       0.0 = Flat
    """

    @staticmethod
    def prepare_indicators(df: pd.DataFrame, genome: StrategyGenome) -> pd.DataFrame:
        """Ensures all necessary indicator columns exist in the DataFrame."""
        df = df.copy()
        c = df["close"]
        h = df["high"]
        l = df["low"]
        v = df["volume"] if "volume" in df else pd.Series(1000.0, index=df.index)

        # 1. EMA for trend filter lookback
        ema_col = f"ema_{genome.trend_filter_lookback}"
        if ema_col not in df.columns:
            df[ema_col] = calculate_ema(c, genome.trend_filter_lookback)

        # 2. SuperTrend (10, 3.0)
        if "supertrend_direction" not in df.columns:
            st = calculate_supertrend(df, period=10, multiplier=3.0)
            df["supertrend_direction"] = st["direction"]

        # 3. Wilder's RSI(14)
        if "rsi" not in df.columns:
            df["rsi"] = calculate_rsi(c, period=14)

        # 4. Bollinger Bands(20, 2.0)
        if "bb_upper" not in df.columns or "bb_bandwidth" not in df.columns:
            bb = calculate_bollinger_bands(c, period=20, std_dev=2.0)
            df["bb_upper"] = bb["upper"]
            df["bb_lower"] = bb["lower"]
            df["bb_middle"] = bb["middle"]
            df["bb_bandwidth"] = bb["bandwidth"]

        # 5. ATR(14)
        if "atr" not in df.columns:
            df["atr"] = calculate_atr(df, period=14)

        # 6. Volume SMA(20)
        if "volume_sma_20" not in df.columns:
            df["volume_sma_20"] = v.rolling(window=20, min_periods=5).mean().fillna(v)

        return df

    @classmethod
    def generate_signals(cls, df: pd.DataFrame, genome: StrategyGenome) -> np.ndarray:
        """Dispatches signal calculation to the appropriate species generator."""
        df_ind = cls.prepare_indicators(df, genome)

        if genome.species == StrategySpecies.MOMENTUM_TREND:
            return cls._signals_momentum_trend(df_ind, genome)
        elif genome.species == StrategySpecies.MEAN_REVERSION:
            return cls._signals_mean_reversion(df_ind, genome)
        elif genome.species == StrategySpecies.BREAKOUT_VOLATILITY:
            return cls._signals_breakout_volatility(df_ind, genome)
        elif genome.species == StrategySpecies.REGIME_ADAPTIVE:
            return cls._signals_regime_adaptive(df_ind, genome)
        else:
            return np.zeros(len(df), dtype=float)

    @staticmethod
    def _signals_momentum_trend(df: pd.DataFrame, genome: StrategyGenome) -> np.ndarray:
        """
        MOMENTUM_TREND:
        - Long: Close > EMA(lookback) AND SuperTrend == 1 AND RSI > 50
        - Short: Close < EMA(lookback) AND SuperTrend == -1 AND RSI < 50
        """
        c = df["close"].values
        ema = df[f"ema_{genome.trend_filter_lookback}"].values
        st_dir = df["supertrend_direction"].values
        rsi = df["rsi"].values

        long_cond = (c > ema) & (st_dir > 0) & (rsi >= 50.0)
        short_cond = (c < ema) & (st_dir < 0) & (rsi <= 50.0)

        # If confluence is available in df, enforce threshold
        if "confluence" in df.columns:
            conf = df["confluence"].values
            long_cond = long_cond & (conf >= genome.entry_signal_threshold)
            short_cond = short_cond & (conf <= -genome.entry_signal_threshold)

        signals = np.zeros(len(df), dtype=float)
        signals[long_cond] = 1.0
        signals[short_cond] = -1.0
        return signals

    @staticmethod
    def _signals_mean_reversion(df: pd.DataFrame, genome: StrategyGenome) -> np.ndarray:
        """
        MEAN_REVERSION:
        - Long: RSI <= rsi_oversold AND Close <= bb_lower * 1.002
        - Short: RSI >= rsi_overbought AND Close >= bb_upper * 0.998
        - Flat: RSI crosses 50.0
        """
        c = df["close"].values
        rsi = df["rsi"].values
        bb_upper = df["bb_upper"].values
        bb_lower = df["bb_lower"].values

        n = len(df)
        signals = np.zeros(n, dtype=float)
        current_state = 0.0

        for i in range(1, n):
            # Check entry triggers
            if (rsi[i] <= genome.rsi_oversold_bound) or (c[i] <= bb_lower[i] * 1.005 and rsi[i] <= 45.0):
                current_state = 1.0
            elif (rsi[i] >= genome.rsi_overbought_bound) or (c[i] >= bb_upper[i] * 0.995 and rsi[i] >= 55.0):
                current_state = -1.0
            # Check mean-reversion exit trigger (cross back past 50)
            elif (current_state == 1.0 and rsi[i] >= 50.0) or (current_state == -1.0 and rsi[i] <= 50.0):
                current_state = 0.0

            signals[i] = current_state

        return signals

    @staticmethod
    def _signals_breakout_volatility(df: pd.DataFrame, genome: StrategyGenome) -> np.ndarray:
        """
        BREAKOUT_VOLATILITY:
        - Long: Squeezed recently (BW <= 0.040) AND Close > Upper BB AND Volume > 1.2x SMA
        - Short: Squeezed recently (BW <= 0.040) AND Close < Lower BB AND Volume > 1.2x SMA
        """
        c = df["close"].values
        bb_upper = df["bb_upper"].values
        bb_lower = df["bb_lower"].values
        bw = df["bb_bandwidth"].values
        vol = df["volume"].values if "volume" in df.columns else np.ones(len(df)) * 1000.0
        vol_sma = df["volume_sma_20"].values

        # Rolling 3-bar squeeze flag
        bw_squeezed = pd.Series(bw <= 0.040).rolling(window=3, min_periods=1).max().values > 0
        vol_surge = vol >= (vol_sma * 1.20)

        long_cond = bw_squeezed & (c > bb_upper) & vol_surge
        short_cond = bw_squeezed & (c < bb_lower) & vol_surge

        signals = np.zeros(len(df), dtype=float)
        signals[long_cond] = 1.0
        signals[short_cond] = -1.0
        return signals

    @staticmethod
    def _signals_regime_adaptive(df: pd.DataFrame, genome: StrategyGenome) -> np.ndarray:
        """
        REGIME_ADAPTIVE:
        - In LOW_VOL_COMPRESSION: acts as mean reversion
        - In TRENDING_EXPANSION: acts as momentum breakout
        - In HIGH_VOL_CHAOS: flat to protect capital unless strong edge
        """
        signals_trend = SpeciesStrategyBuilder._signals_momentum_trend(df, genome)
        signals_mr = SpeciesStrategyBuilder._signals_mean_reversion(df, genome)

        n = len(df)
        signals = np.zeros(n, dtype=float)

        # If regime column is provided in DataFrame
        if "regime" in df.columns:
            regimes = df["regime"].values
            for i in range(n):
                r = regimes[i]
                if r == VolatilityRegime.LOW_VOL_COMPRESSION or r == "LOW_VOL_COMPRESSION":
                    signals[i] = signals_mr[i]
                elif r == VolatilityRegime.TRENDING_EXPANSION or r == "TRENDING_EXPANSION":
                    signals[i] = signals_trend[i]
                else:  # HIGH_VOL_CHAOS
                    signals[i] = 0.0  # Defensive cash preservation
        else:
            # Fallback based on rolling Bollinger bandwidth
            bw = df["bb_bandwidth"].values
            for i in range(n):
                if bw[i] <= 0.035:
                    signals[i] = signals_mr[i]
                elif bw[i] >= 0.080:
                    signals[i] = 0.0  # Chaos
                else:
                    signals[i] = signals_trend[i]

        return signals
