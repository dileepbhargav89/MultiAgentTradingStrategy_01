"""Quantitative feature engineering for multi-timeframe OHLCV data."""

from typing import Dict, Optional
import numpy as np
import pandas as pd


# Number of candles representing 24h and 7d per timeframe
TIMEFRAME_WINDOWS = {
    "15m": {"24h": 96, "7d": 672},
    "1h": {"24h": 24, "7d": 168},
    "4h": {"24h": 6, "7d": 42},
    "1d": {"24h": 5, "7d": 7},
}


class FeatureEngineer:
    """
    Computes statistical and structural price features required by downstream agents:
    - Simple and Logarithmic returns
    - Rolling Volatility (24h and 7d)
    - Normalized High-Low Range
    - Candle Body-to-Wick structure ratio
    - Volume relative to rolling SMA
    """

    def compute_features(self, df: pd.DataFrame, timeframe: str = "1h") -> pd.DataFrame:
        """
        Computes all quantitative features on an OHLCV DataFrame.

        Returns a DataFrame containing the computed feature columns.
        """
        if df is None or df.empty:
            return pd.DataFrame(
                columns=[
                    "returns",
                    "log_returns",
                    "volatility_24h",
                    "volatility_7d",
                    "range_pct",
                    "body_wick_ratio",
                    "volume_sma_ratio",
                ]
            )

        features = pd.DataFrame(index=df.index)

        # 1. Simple Returns
        features["returns"] = df["close"].pct_change().fillna(0.0)

        # 2. Log Returns: ln(P_t / P_{t-1})
        # Safe log computation avoiding division by zero
        prev_close = df["close"].shift(1)
        valid_ratio = (df["close"] / prev_close).replace(0, np.nan)
        features["log_returns"] = np.log(valid_ratio).fillna(0.0)

        # 3. Rolling Volatility (24h and 7d)
        windows = TIMEFRAME_WINDOWS.get(timeframe, {"24h": 24, "7d": 168})
        w_24h = max(2, windows["24h"])
        w_7d = max(2, windows["7d"])

        features["volatility_24h"] = (
            features["log_returns"].rolling(window=w_24h, min_periods=2).std().fillna(0.0)
        )
        features["volatility_7d"] = (
            features["log_returns"].rolling(window=w_7d, min_periods=2).std().fillna(0.0)
        )

        # 4. High-Low Range %: (High - Low) / Close
        safe_close = df["close"].replace(0, np.nan)
        features["range_pct"] = ((df["high"] - df["low"]) / safe_close).fillna(0.0)

        # 5. Body-to-Wick Ratio: |Close - Open| / (High - Low)
        hl_diff = (df["high"] - df["low"]).replace(0, np.nan)
        body = (df["close"] - df["open"]).abs()
        features["body_wick_ratio"] = (body / hl_diff).fillna(0.0)
        # Cap at 1.0 (body cannot physically exceed candle range unless data error)
        features["body_wick_ratio"] = features["body_wick_ratio"].clip(0.0, 1.0)

        # 6. Volume SMA Ratio: Volume / SMA(Volume, 20)
        vol_sma20 = df["volume"].rolling(window=20, min_periods=1).mean().replace(0, np.nan)
        features["volume_sma_ratio"] = (df["volume"] / vol_sma20).fillna(1.0)

        return features

    def compute_all_timeframes(
        self,
        timeframe_dfs: Dict[str, pd.DataFrame]
    ) -> Dict[str, pd.DataFrame]:
        """
        Computes features for all provided timeframes.
        """
        feature_dict: Dict[str, pd.DataFrame] = {}
        for tf, df in timeframe_dfs.items():
            feature_dict[tf] = self.compute_features(df, timeframe=tf)
        return feature_dict
