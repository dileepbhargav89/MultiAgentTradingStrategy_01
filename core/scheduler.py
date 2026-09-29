"""Multi-horizon timing engine and candle boundary alignment scheduler for StrategyOne."""

import math
from datetime import datetime, timezone
from typing import Optional
from loguru import logger


class TimingScheduler:
    """Computes exact execution offsets aligned with exchange candle closes and retraining schedules."""

    TIMEFRAME_SECONDS = {
        "1m": 60,
        "3m": 180,
        "5m": 300,
        "15m": 900,
        "30m": 1800,
        "1h": 3600,
        "2h": 7200,
        "4h": 14400,
        "6h": 21600,
        "8h": 28800,
        "12h": 43200,
        "1d": 86400,
    }

    @classmethod
    def get_timeframe_seconds(cls, timeframe: str) -> int:
        """Returns the duration of a timeframe in seconds."""
        tf = timeframe.lower().strip()
        if tf not in cls.TIMEFRAME_SECONDS:
            raise ValueError(f"Unsupported timeframe: {timeframe}")
        return cls.TIMEFRAME_SECONDS[tf]

    @classmethod
    def seconds_until_next_candle(
        cls,
        timeframe: str = "15m",
        now: Optional[datetime] = None,
        buffer_seconds: float = 1.5,
    ) -> float:
        """
        Calculates exact seconds remaining until the close of the current candle on the exchange,
        plus an optional safety buffer (default 1.5s) to ensure exchange data availability.
        """
        current_time = now or datetime.now(timezone.utc)
        current_ts = current_time.timestamp()
        tf_sec = cls.get_timeframe_seconds(timeframe)

        # Elapsed seconds in the current candle interval
        elapsed = current_ts % tf_sec
        remaining = tf_sec - elapsed

        # Add buffer to ensure exchange candle has finalized
        sleep_duration = remaining + buffer_seconds
        return round(sleep_duration, 3)

    @classmethod
    def is_retrain_due(
        cls,
        last_retrain_time: Optional[datetime],
        interval_hours: int = 24,
        now: Optional[datetime] = None,
    ) -> bool:
        """Determines if a genetic algorithm retraining cycle is due."""
        if last_retrain_time is None:
            return True
        current_time = now or datetime.now(timezone.utc)
        elapsed_sec = (current_time - last_retrain_time).total_seconds()
        return elapsed_sec >= (interval_hours * 3600.0)

    @classmethod
    def get_current_candle_timestamp(
        cls, timeframe: str = "15m", now: Optional[datetime] = None
    ) -> datetime:
        """Returns the start timestamp of the current open candle interval in UTC."""
        current_time = now or datetime.now(timezone.utc)
        current_ts = current_time.timestamp()
        tf_sec = cls.get_timeframe_seconds(timeframe)
        candle_start_ts = math.floor(current_ts / tf_sec) * tf_sec
        return datetime.fromtimestamp(candle_start_ts, tz=timezone.utc)

    @classmethod
    def get_seconds_until_next_candle(
        cls, timeframe: str = "15m", buffer_seconds: float = 0.0
    ) -> float:
        """Alias for seconds_until_next_candle."""
        return cls.seconds_until_next_candle(timeframe=timeframe, buffer_seconds=buffer_seconds)

    @property
    def tick_interval_sec(self) -> float:
        """Default tick polling interval in seconds."""
        return 2.0

