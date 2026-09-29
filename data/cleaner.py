"""Data cleaning, gap filling, anomaly detection, and quality validation."""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
import numpy as np
import pandas as pd
from loguru import logger
from config.settings import get_settings


TIMEFRAME_DELTAS = {
    "1m": pd.Timedelta(minutes=1),
    "5m": pd.Timedelta(minutes=5),
    "15m": pd.Timedelta(minutes=15),
    "30m": pd.Timedelta(minutes=30),
    "1h": pd.Timedelta(hours=1),
    "2h": pd.Timedelta(hours=2),
    "4h": pd.Timedelta(hours=4),
    "6h": pd.Timedelta(hours=6),
    "8h": pd.Timedelta(hours=8),
    "12h": pd.Timedelta(hours=12),
    "1d": pd.Timedelta(days=1),
    "1w": pd.Timedelta(weeks=1),
}


class DataCleaner:
    """
    Cleans OHLCV DataFrames, fills gaps, identifies anomalies, and scores data quality.
    """

    def __init__(self) -> None:
        self.settings = get_settings()

    def clean_ohlcv(
        self,
        df: pd.DataFrame,
        timeframe: str = "1h",
    ) -> Tuple[pd.DataFrame, Dict[str, Any]]:
        """
        Cleans and validates an OHLCV DataFrame.

        Returns:
            Tuple of:
            - cleaned_df (pd.DataFrame): Sorted, gap-filled, duplicate-free DataFrame.
            - quality_metrics (dict):
                - 'quality_score': float (0.0 to 1.0)
                - 'gap_count': int
                - 'anomalies': list of dicts
                - 'ohlc_violations': int
                - 'is_stale': bool
                - 'freshness_seconds': float
        """
        if df is None or df.empty:
            return pd.DataFrame(columns=["timestamp", "open", "high", "low", "close", "volume"]), {
                "quality_score": 0.0,
                "gap_count": 0,
                "anomalies": [],
                "ohlc_violations": 0,
                "is_stale": True,
                "freshness_seconds": 999999.0,
            }

        cleaned = df.copy()

        # Ensure correct column types
        cleaned["timestamp"] = pd.to_datetime(cleaned["timestamp"], utc=True)
        for col in ["open", "high", "low", "close", "volume"]:
            cleaned[col] = pd.to_numeric(cleaned[col], errors="coerce")

        # Sanitize Inf / -Inf to NaN and clean missing prices
        cleaned.replace([np.inf, -np.inf], np.nan, inplace=True)
        for col in ["open", "high", "low", "close"]:
            cleaned[col] = cleaned[col].ffill().bfill()
        cleaned["volume"] = cleaned["volume"].fillna(0.0)

        # Drop duplicates and sort
        cleaned = cleaned.drop_duplicates(subset=["timestamp"]).sort_values("timestamp").reset_index(drop=True)

        # 1. OHLC Consistency Check before filling
        ohlc_violations = self._count_ohlc_violations(cleaned)

        # 2. Detect Anomalies (flash crashes, extreme wicks, zero volume, dynamic surges)
        anomalies = self._detect_anomalies(cleaned, timeframe)

        # 3. Detect and Fill Gaps
        cleaned, gap_count = self._fill_gaps(cleaned, timeframe)

        # 4. Freshness Check
        is_stale, freshness_seconds = self._check_freshness(cleaned, timeframe)

        # 5. Compute Quality Score
        total_candles = max(len(cleaned), 1)
        quality_score = 1.0
        quality_score -= (gap_count / total_candles) * 5.0
        quality_score -= (len(anomalies) / total_candles) * 2.0
        quality_score -= (ohlc_violations / total_candles) * 10.0
        if is_stale:
            quality_score -= 0.10

        quality_score = float(np.clip(quality_score, 0.0, 1.0))

        metrics = {
            "quality_score": quality_score,
            "gap_count": gap_count,
            "anomalies": anomalies,
            "ohlc_violations": ohlc_violations,
            "is_stale": is_stale,
            "freshness_seconds": freshness_seconds,
            "total_candles": len(cleaned),
        }

        return cleaned, metrics

    def _count_ohlc_violations(self, df: pd.DataFrame) -> int:
        """Counts candles violating physical price properties (high < low, etc.)."""
        violations = (
            (df["high"] < df["low"]) |
            (df["high"] < df["open"]) |
            (df["high"] < df["close"]) |
            (df["low"] > df["open"]) |
            (df["low"] > df["close"])
        )
        return int(violations.sum())

    def _detect_anomalies(self, df: pd.DataFrame, timeframe: str) -> List[Dict[str, Any]]:
        """
        Flags single-candle flash crashes, anomalous wicks, and extreme volume spikes.
        """
        anomalies: List[Dict[str, Any]] = []
        if len(df) == 0:
            return anomalies

        body_ratio = (df["close"] - df["open"]).abs() / df["open"].replace(0, np.nan)
        upper_wick = (df["high"] - df[["open", "close"]].max(axis=1)) / df["open"].replace(0, np.nan)
        lower_wick = (df[["open", "close"]].min(axis=1) - df["low"]) / df["open"].replace(0, np.nan)

        # Rolling 24h volume average
        tf_delta = TIMEFRAME_DELTAS.get(timeframe, pd.Timedelta(hours=1))
        rolling_candles = max(1, int(pd.Timedelta(hours=24) / tf_delta))
        vol_avg = df["volume"].rolling(window=rolling_candles, min_periods=1).mean()

        for idx, row in df.iterrows():
            ts = row["timestamp"]

            # Body anomaly (> 8%)
            b_ratio = body_ratio.iloc[idx]
            if not np.isnan(b_ratio) and b_ratio >= self.settings.ANOMALY_THRESHOLD:
                anomalies.append({
                    "timestamp": ts,
                    "type": "BODY_ANOMALY",
                    "value": float(b_ratio),
                    "description": f"Abnormal body change of {b_ratio:.2%} on {timeframe}",
                })

            # Wick anomaly (> 12%)
            u_wick = upper_wick.iloc[idx]
            l_wick = lower_wick.iloc[idx]
            if not np.isnan(u_wick) and u_wick >= self.settings.WICK_ANOMALY_THRESHOLD:
                anomalies.append({
                    "timestamp": ts,
                    "type": "UPPER_WICK_ANOMALY",
                    "value": float(u_wick),
                    "description": f"Abnormal upper wick of {u_wick:.2%} on {timeframe}",
                })
            if not np.isnan(l_wick) and l_wick >= self.settings.WICK_ANOMALY_THRESHOLD:
                anomalies.append({
                    "timestamp": ts,
                    "type": "LOWER_WICK_ANOMALY",
                    "value": float(l_wick),
                    "description": f"Abnormal lower wick of {l_wick:.2%} on {timeframe}",
                })

            # Zero volume
            if row["volume"] == 0.0:
                anomalies.append({
                    "timestamp": ts,
                    "type": "ZERO_VOLUME",
                    "value": 0.0,
                    "description": f"Zero volume candle detected on {timeframe}",
                })

            # Volume spike (> 10x average)
            avg = vol_avg.iloc[idx]
            if avg > 0 and row["volume"] > 10 * avg:
                anomalies.append({
                    "timestamp": ts,
                    "type": "VOLUME_SPIKE",
                    "value": float(row["volume"] / avg),
                    "description": f"Volume spike {row['volume'] / avg:.1f}x above 24h rolling average",
                })

        return anomalies

    def _fill_gaps(self, df: pd.DataFrame, timeframe: str) -> Tuple[pd.DataFrame, int]:
        """
        Detects missing intervals and fills them conservatively using forward-fill.
        Missing candles have:
            open = prev_close
            high = prev_close
            low = prev_close
            close = prev_close
            volume = 0.0
        """
        if len(df) <= 1:
            return df, 0

        delta = TIMEFRAME_DELTAS.get(timeframe)
        if not delta:
            return df, 0

        full_range = pd.date_range(
            start=df["timestamp"].iloc[0],
            end=df["timestamp"].iloc[-1],
            freq=delta,
            tz=timezone.utc
        )

        missing_count = len(full_range) - len(df)
        if missing_count <= 0:
            return df, 0

        # Reindex to full datetime range
        df_indexed = df.set_index("timestamp").reindex(full_range)

        # Forward fill price data from previous candle
        df_indexed["close"] = df_indexed["close"].ffill()
        df_indexed["open"] = df_indexed["open"].fillna(df_indexed["close"])
        df_indexed["high"] = df_indexed["high"].fillna(df_indexed["close"])
        df_indexed["low"] = df_indexed["low"].fillna(df_indexed["close"])
        df_indexed["volume"] = df_indexed["volume"].fillna(0.0)

        df_filled = df_indexed.reset_index()
        df_filled.rename(columns={"index": "timestamp"}, inplace=True)
        return df_filled, missing_count

    def _check_freshness(self, df: pd.DataFrame, timeframe: str) -> Tuple[bool, float]:
        """
        Checks whether the latest candle timestamp is fresh compared to current UTC time.
        """
        if df.empty:
            return True, 999999.0

        latest_time = df["timestamp"].iloc[-1]
        now = datetime.now(timezone.utc)
        elapsed = (now - latest_time).total_seconds()

        tf_delta = TIMEFRAME_DELTAS.get(timeframe, pd.Timedelta(hours=1))
        allowed_delay = tf_delta.total_seconds() + self.settings.MAX_STALE_SECONDS

        is_stale = elapsed > allowed_delay
        return is_stale, elapsed
