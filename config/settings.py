"""System configuration using Pydantic Settings."""

from functools import lru_cache
from typing import Dict, List
from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuration settings for the trading system."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    # Exchange
    EXCHANGE: str = Field(default="binance", description="Exchange ID (ccxt)")
    API_KEY: str = Field(default="", validation_alias="BINANCE_API_KEY", description="Binance API Key")
    API_SECRET: str = Field(default="", validation_alias="BINANCE_API_SECRET", description="Binance API Secret")
    TESTNET: bool = Field(default=True, validation_alias="BINANCE_TESTNET", description="Always start on testnet")
    DEFAULT_TYPE: str = Field(default="future", validation_alias="BINANCE_DEFAULT_TYPE", description="Default market type (future or spot)")

    # Trading Symbol & Timeframes
    SYMBOL: str = Field(default="BTC/USDT", validation_alias=AliasChoices("SYMBOL", "TRADING_SYMBOL"), description="Target trading pair")
    TIMEFRAMES: List[str] = Field(
        default=["15m", "1h", "4h", "1d"],
        description="Active timeframes for multi-timeframe analysis"
    )

    # Data History Limits (number of candles to maintain)
    CANDLE_LIMITS: Dict[str, int] = Field(
        default={
            "15m": 2688,  # 28 days of 15m candles
            "1h": 2160,   # 90 days of 1h candles
            "4h": 2160,   # 360 days of 4h candles
            "1d": 730,    # 2 years of daily candles
        },
        description="Candle fetch depth per timeframe"
    )

    # Cache
    CACHE_DIR: str = Field(default="data/cache", description="Directory to cache OHLCV CSVs")

    # Data Quality Thresholds
    MIN_DATA_QUALITY: float = Field(default=0.85, description="Minimum acceptable quality score to trade")
    MAX_GAP_RATIO: float = Field(default=0.02, description="Maximum allowable missing candles fraction")
    MAX_STALE_SECONDS: int = Field(default=120, description="Seconds before data is deemed stale")
    ANOMALY_THRESHOLD: float = Field(default=0.08, description="Body move % threshold to trigger anomaly flag (8%)")
    WICK_ANOMALY_THRESHOLD: float = Field(default=0.12, description="Wick % threshold to trigger anomaly flag (12%)")

    # Sprint 9: Order Execution Parameters
    EXECUTION_MODE: str = Field(default="PAPER", description="Execution mode: PAPER, LIVE_TESTNET, LIVE_PRODUCTION")
    DEFAULT_MAKER_TIMEOUT_SEC: int = Field(default=60, description="Timeout in seconds for unfilled maker limit orders")
    MAX_SLIPPAGE_BPS: float = Field(default=25.0, description="Maximum allowable slippage in bps for market orders")
    MIN_NOTIONAL_USD: float = Field(default=10.0, description="Minimum order size in USD enforced by Binance")

    # Sprint 10: Master Orchestrator & Live Scheduler Parameters
    TICK_INTERVAL_SEC: float = Field(default=2.0, description="Interval in seconds for high-frequency tick monitoring loop")
    RETRAIN_INTERVAL_HOURS: int = Field(default=24, description="Interval in hours between GA retraining cycles")
    CHECKPOINT_FILE_PATH: str = Field(default="data/system_checkpoint.json", description="Path to system checkpoint file")
    PORTFOLIO_STATE_PATH: str = Field(default="data/cache/portfolio_state.json", description="Path to portfolio state file")
    MAX_CONCURRENT_POSITIONS: int = Field(default=3, description="Maximum allowable concurrent open positions")


@lru_cache()
def get_settings() -> Settings:
    """Cached settings singleton provider."""
    return Settings()


# Default singleton instance
settings = get_settings()
