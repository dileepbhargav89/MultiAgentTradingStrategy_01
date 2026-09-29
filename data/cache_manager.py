"""Local disk caching for OHLCV candle data with atomic writes and metadata inspection."""

import os
from pathlib import Path
from typing import Any, Dict, Optional
import pandas as pd
from loguru import logger
from config.settings import get_settings


class CacheManager:
    """
    Manages local CSV caching of OHLCV data.
    Allows quick startup, offline simulation, and delta-only live fetching.
    Uses atomic writes to prevent data corruption during unexpected halts.
    """

    def __init__(self, cache_dir: Optional[str] = None) -> None:
        self.settings = get_settings()
        self.cache_dir = Path(cache_dir or self.settings.CACHE_DIR)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _get_filepath(self, symbol: str, timeframe: str) -> Path:
        sanitized_symbol = symbol.replace("/", "").replace(":", "")
        return self.cache_dir / f"{sanitized_symbol}_{timeframe}.csv"

    def load(self, symbol: str, timeframe: str) -> Optional[pd.DataFrame]:
        """Loads cached OHLCV data from disk if present."""
        path = self._get_filepath(symbol, timeframe)
        if not path.exists():
            return None

        try:
            df = pd.read_csv(path)
            if df.empty or "timestamp" not in df.columns:
                return None
            df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
            for col in ["open", "high", "low", "close", "volume"]:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors="coerce").astype(float)
            df = df.drop_duplicates(subset=["timestamp"]).sort_values("timestamp").reset_index(drop=True)
            return df
        except Exception as e:
            logger.warning(f"Failed to read cache at {path}: {e}")
            return None

    def save(self, symbol: str, timeframe: str, df: pd.DataFrame, max_candles: Optional[int] = None) -> None:
        """Saves OHLCV data to local CSV cache via atomic swap, optionally trimming to max_candles."""
        if df is None or df.empty:
            return

        path = self._get_filepath(symbol, timeframe)
        temp_path = path.with_suffix(".csv.tmp")
        try:
            to_save = df.copy()
            to_save = to_save.drop_duplicates(subset=["timestamp"]).sort_values("timestamp")
            if max_candles and len(to_save) > max_candles:
                to_save = to_save.iloc[-max_candles:]

            # Atomic write pattern
            to_save.to_csv(temp_path, index=False)
            os.replace(temp_path, path)
            logger.debug(f"Saved {len(to_save)} candles atomically to cache: {path}")
        except Exception as e:
            logger.error(f"Failed to save cache at {path}: {e}")
            if temp_path.exists():
                temp_path.unlink(missing_ok=True)

    def update(self, symbol: str, timeframe: str, new_df: pd.DataFrame, max_candles: Optional[int] = None) -> pd.DataFrame:
        """Merges new candles with cached candles, dedupes, sorts, and persists."""
        cached_df = self.load(symbol, timeframe)
        if cached_df is None or cached_df.empty:
            merged = new_df
        else:
            merged = pd.concat([cached_df, new_df], ignore_index=True)

        if merged is not None and not merged.empty:
            merged = merged.drop_duplicates(subset=["timestamp"]).sort_values("timestamp").reset_index(drop=True)
            self.save(symbol, timeframe, merged, max_candles=max_candles)
        return merged

    def get_stats(self, symbol: str, timeframe: str) -> Dict[str, Any]:
        """Returns metadata stats for cached timeframe."""
        path = self._get_filepath(symbol, timeframe)
        if not path.exists():
            return {"exists": False, "candles": 0, "size_kb": 0.0}

        df = self.load(symbol, timeframe)
        if df is None or df.empty:
            return {"exists": True, "candles": 0, "size_kb": path.stat().st_size / 1024}

        return {
            "exists": True,
            "candles": len(df),
            "size_kb": round(path.stat().st_size / 1024, 2),
            "start": str(df["timestamp"].iloc[0]),
            "end": str(df["timestamp"].iloc[-1]),
        }
