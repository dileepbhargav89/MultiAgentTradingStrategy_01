"""Data Quality Agent: Autonomous guardian of data integrity with absolute veto power."""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
import numpy as np
import pandas as pd
from loguru import logger

from config.settings import get_settings
from core.events import (
    EVENT_DATA_QUALITY_ANOMALY,
    EVENT_DATA_QUALITY_HALT,
    EVENT_DATA_QUALITY_REPORT,
    event_bus,
)
from core.types import AgentState, DataPacket, DataQualityReport
from data.cleaner import DataCleaner
from data.features import FeatureEngineer
from data.fetcher import DataFetcher


TIMEFRAME_WEIGHTS = {
    "15m": 0.35,
    "1h": 0.35,
    "4h": 0.20,
    "1d": 0.10,
}


class DataQualityAgent:
    """
    Autonomous Data Quality Agent.
    Evaluates multi-timeframe market data reliability, detects anomalies,
    verifies cross-timeframe consistency, and exercises ABSOLUTE VETO power.
    """

    def __init__(
        self,
        fetcher: Optional[DataFetcher] = None,
        cleaner: Optional[DataCleaner] = None,
        features: Optional[FeatureEngineer] = None,
    ) -> None:
        self.settings = get_settings()
        self.fetcher = fetcher or DataFetcher()
        self.cleaner = cleaner or DataCleaner()
        self.features = features or FeatureEngineer()

        self.consecutive_fetch_failures: int = 0
        self.state: AgentState = AgentState.HEALTHY
        self.last_report: Optional[DataQualityReport] = None

    async def evaluate_live(self, symbol: Optional[str] = None) -> DataQualityReport:
        """
        Fetches live multi-timeframe data from exchange, cleans, validates,
        computes features, evaluates system state, and publishes event reports.
        """
        target_symbol = symbol or self.settings.SYMBOL
        spread_data = {"spread_pct": 0.0, "last": 0.0}
        try:
            raw_dfs = await self.fetcher.fetch_all_timeframes(target_symbol)
            spread_data = await self.fetcher.fetch_spread(target_symbol)
            self.consecutive_fetch_failures = 0
        except Exception as e:
            self.consecutive_fetch_failures += 1
            logger.error(
                f"Fetch failure #{self.consecutive_fetch_failures} for {target_symbol}: {e}"
            )
            return self._build_failure_report(target_symbol, str(e))

        return self.evaluate_data(
            target_symbol,
            raw_dfs,
            spread_pct=spread_data.get("spread_pct", 0.0),
            live_price=spread_data.get("last", 0.0),
        )

    def evaluate_data(
        self,
        symbol: str,
        raw_dfs: Dict[str, pd.DataFrame],
        spread_pct: float = 0.0,
        live_price: float = 0.0,
    ) -> DataQualityReport:
        """
        Synchronously validates and analyzes provided multi-timeframe DataFrames.
        """
        cleaned_dfs: Dict[str, pd.DataFrame] = {}
        tf_features: Dict[str, pd.DataFrame] = {}
        quality_scores: Dict[str, float] = {}
        all_anomalies: List[Dict[str, Any]] = []
        warnings: List[str] = []
        total_gaps_filled = 0
        all_fresh = True

        for tf, df in raw_dfs.items():
            cleaned, metrics = self.cleaner.clean_ohlcv(df, timeframe=tf)
            cleaned_dfs[tf] = cleaned
            quality_scores[tf] = metrics["quality_score"]
            total_gaps_filled += metrics["gap_count"]

            if metrics["anomalies"]:
                for anom in metrics["anomalies"]:
                    anom_record = {"timeframe": tf, **anom}
                    all_anomalies.append(anom_record)

            if metrics["is_stale"]:
                all_fresh = False
                warnings.append(
                    f"{tf} data is stale ({metrics['freshness_seconds']:.0f}s elapsed)"
                )

            # Compute features for cleaned data
            tf_features[tf] = self.features.compute_features(cleaned, timeframe=tf)

        # 1. Calculate Weighted Overall Quality Score
        overall_quality = 0.0
        weight_sum = 0.0
        for tf, score in quality_scores.items():
            w = TIMEFRAME_WEIGHTS.get(tf, 0.25)
            overall_quality += score * w
            weight_sum += w

        overall_quality = overall_quality / weight_sum if weight_sum > 0 else 0.0

        # 2. Check Cross-Timeframe Consistency
        cross_ok, cross_warning = self._check_cross_timeframe_consistency(cleaned_dfs)
        if not cross_ok:
            warnings.append(cross_warning)
            overall_quality = min(overall_quality, 0.60)  # Heavy penalty for contradictory data

        # 3. Determine latest price
        current_price = live_price
        if current_price <= 0.0:
            for tf in ["15m", "1h", "4h", "1d"]:
                if tf in cleaned_dfs and not cleaned_dfs[tf].empty:
                    current_price = float(cleaned_dfs[tf]["close"].iloc[-1])
                    break

        # 4. Check Spread Thresholds
        if spread_pct > 0.005:
            warnings.append(f"Elevated bid-ask spread: {spread_pct:.2%}")
        if spread_pct > 0.015:
            overall_quality = max(0.0, overall_quality - 0.15)
            warnings.append(f"Severe bid-ask spread blowout: {spread_pct:.2%}")

        # 5. Determine Operational Agent State & Tradeability
        stale_count = len([w for w in warnings if "stale" in w.lower()])
        if self.consecutive_fetch_failures >= 3:
            self.state = AgentState.HALTED
            is_tradeable = False
            warnings.append("Halted due to multiple consecutive fetch failures.")
        elif not all_fresh and len(raw_dfs) > 0 and stale_count >= len(raw_dfs):
            # ALL timeframes are stale → data is completely outdated
            self.state = AgentState.HALTED
            is_tradeable = False
            warnings.append("ALL timeframes stale. Trading halted.")
        elif overall_quality < self.settings.MIN_DATA_QUALITY or not cross_ok:
            self.state = AgentState.HALTED
            is_tradeable = False
        elif overall_quality < 0.90 or not all_fresh:
            self.state = AgentState.DEGRADED
            is_tradeable = True  # Can trade in reduced capacity
        else:
            self.state = AgentState.HEALTHY
            is_tradeable = True

        report = DataQualityReport(
            status=self.state,
            quality_scores=quality_scores,
            overall_quality=float(overall_quality),
            is_tradeable=is_tradeable,
            freshness_ok=all_fresh,
            anomalies=all_anomalies,
            gaps_filled=total_gaps_filled,
            warnings=warnings,
            data=cleaned_dfs,
            features=tf_features,
            latest_price=current_price,
            spread_pct=spread_pct,
            timestamp=datetime.now(timezone.utc),
        )

        self.last_report = report

        # Publish Events via Event Bus
        event_bus.publish(EVENT_DATA_QUALITY_REPORT, report)

        if not is_tradeable:
            logger.warning(
                f"DATA QUALITY VETO: Trading HALTED. Overall Quality: {overall_quality:.2%}. Reasons: {warnings}"
            )
            event_bus.publish(EVENT_DATA_QUALITY_HALT, {
                "symbol": symbol,
                "report": report,
                "reason": warnings or ["Quality score below threshold"],
            })

        if all_anomalies:
            event_bus.publish(EVENT_DATA_QUALITY_ANOMALY, {
                "symbol": symbol,
                "anomalies": all_anomalies,
            })

        return report

    def _check_cross_timeframe_consistency(
        self,
        timeframe_dfs: Dict[str, pd.DataFrame]
    ) -> Tuple[bool, str]:
        """
        Verifies that higher and lower timeframes do not report conflicting prices
        at the same timestamp (e.g. 1h candle close vs 4h candle close).
        """
        df_1h = timeframe_dfs.get("1h")
        df_4h = timeframe_dfs.get("4h")

        if df_1h is None or df_4h is None or df_1h.empty or df_4h.empty:
            return True, ""

        # Merge on exact timestamp matches
        merged = pd.merge(
            df_1h[["timestamp", "close"]],
            df_4h[["timestamp", "close"]],
            on="timestamp",
            suffixes=("_1h", "_4h"),
        )

        if merged.empty:
            return True, ""

        # Check latest overlapping candle
        latest = merged.iloc[-1]
        c_1h = latest["close_1h"]
        c_4h = latest["close_4h"]

        if c_1h > 0:
            discrepancy = abs(c_1h - c_4h) / c_1h
            if discrepancy > 0.02:  # >2% discrepancy between timeframes at same timestamp
                return False, f"Cross-timeframe price discrepancy of {discrepancy:.2%} between 1h and 4h at {latest['timestamp']}"

        return True, ""

    def _build_failure_report(self, symbol: str, error_msg: str) -> DataQualityReport:
        self.state = AgentState.HALTED
        report = DataQualityReport(
            status=AgentState.HALTED,
            quality_scores={},
            overall_quality=0.0,
            is_tradeable=False,
            freshness_ok=False,
            warnings=[f"Fetch error: {error_msg}"],
            timestamp=datetime.now(timezone.utc),
        )
        self.last_report = report
        event_bus.publish(EVENT_DATA_QUALITY_HALT, {
            "symbol": symbol,
            "report": report,
            "reason": [error_msg],
        })
        return report

    def build_data_packet(self, symbol: str) -> Optional[DataPacket]:
        """Bundles latest validated data and features into an immutable packet for trading agents."""
        if not self.last_report:
            return None

        return DataPacket(
            symbol=symbol,
            timeframes=self.last_report.data,
            features=self.last_report.features,
            quality=self.last_report,
            latest_price=self.last_report.latest_price,
            spread_pct=self.last_report.spread_pct,
            fetched_at=self.last_report.timestamp,
        )
