"""Technical Analysis Agent: Computes multi-timeframe confluence and structural invalidation levels."""

from datetime import datetime, timezone
from typing import Optional
from loguru import logger

from agents.confluence_engine import ConfluenceEngine
from core.events import EVENT_TECHNICAL_REPORT, event_bus
from core.types import DataPacket, MarketBias, TechnicalAnalysisReport
from indicators.levels import KeyLevelsCalculator
from indicators.volatility import calculate_atr


class TechnicalAgent:
    """
    Agent #2: Technical Analysis Agent.
    Subscribes to validated DataPackets from Agent #1 (Data Quality Agent),
    applies orthogonal indicator pipelines across timeframes, computes continuous
    confluence scores, derives structural invalidation levels, and publishes reports.
    """

    def __init__(self, confluence_engine: Optional[ConfluenceEngine] = None) -> None:
        self.confluence_engine = confluence_engine or ConfluenceEngine()
        self.last_report: Optional[TechnicalAnalysisReport] = None

    def analyze(self, packet: DataPacket) -> TechnicalAnalysisReport:
        """
        Analyzes a validated DataPacket and returns TechnicalAnalysisReport.
        Strictly respects Data Quality Agent veto power: if data is not tradeable,
        refuses to generate directional conviction.
        """
        # 1. Verify Data Quality Veto
        if not packet.quality.is_tradeable:
            logger.warning(
                f"Technical Agent: DataQualityAgent veto active for {packet.symbol}. Neutralizing bias."
            )
            neutral_report = TechnicalAnalysisReport(
                symbol=packet.symbol,
                bias=MarketBias.NEUTRAL,
                confluence_score=0.0,
                timeframe_scores={tf: 0.0 for tf in packet.timeframes},
                dimension_scores={"trend": 0.0, "momentum": 0.0, "volatility": 0.0, "volume": 0.0},
                invalidation_price=packet.latest_price,
                support_levels=[],
                resistance_levels=[],
                atr_14=0.0,
                target_1r=packet.latest_price,
                target_2r=packet.latest_price,
                timestamp=datetime.now(timezone.utc),
            )
            self.last_report = neutral_report
            event_bus.publish(EVENT_TECHNICAL_REPORT, neutral_report)
            return neutral_report

        # 2. Run Multi-Timeframe Confluence Engine
        confluence, bias, tf_scores, dim_scores = self.confluence_engine.calculate_confluence(
            packet.timeframes
        )

        # 3. Calculate Structural Key Levels & Invalidation Price
        # Use 1h for primary swing structure and ATR
        df_1h = packet.timeframes.get("1h")
        if df_1h is None or len(df_1h) < 20:
            # Fallback to any available timeframe
            df_1h = next(iter(packet.timeframes.values()))

        current_price = packet.latest_price
        if current_price <= 0.0:
            current_price = float(df_1h["close"].iloc[-1])

        atr_series = calculate_atr(df_1h, period=14)
        atr_14 = float(atr_series.iloc[-1]) if not atr_series.empty else (current_price * 0.015)

        supports, resistances = KeyLevelsCalculator.calculate_support_resistance_zones(df_1h)

        is_bullish = confluence >= 0.0
        invalidation = KeyLevelsCalculator.calculate_invalidation_price(
            df=df_1h,
            is_bullish=is_bullish,
            atr_value=atr_14,
            lookback=20,
        )

        target_1r, target_2r = KeyLevelsCalculator.calculate_risk_targets(
            entry_price=current_price,
            invalidation_price=invalidation,
            r1=1.5,
            r2=2.5,
        )

        # Compute Macro Institutional 200 SMA on 1h (Macro Structural Filter)
        if len(df_1h) >= 20:
            sma_200 = float(df_1h["close"].rolling(min(200, len(df_1h)), min_periods=20).mean().iloc[-1])
            is_macro_bull = current_price >= sma_200
        else:
            is_macro_bull = confluence >= 0.0
        macro_trend = "BULLISH" if is_macro_bull else "BEARISH"

        report = TechnicalAnalysisReport(
            symbol=packet.symbol,
            bias=bias,
            confluence_score=confluence,
            timeframe_scores=tf_scores,
            dimension_scores=dim_scores,
            invalidation_price=invalidation,
            support_levels=supports,
            resistance_levels=resistances,
            atr_14=atr_14,
            target_1r=target_1r,
            target_2r=target_2r,
            is_macro_bull=is_macro_bull,
            macro_trend=macro_trend,
            timestamp=datetime.now(timezone.utc),
        )

        self.last_report = report
        event_bus.publish(EVENT_TECHNICAL_REPORT, report)
        logger.info(
            f"Technical Analysis [{packet.symbol}]: Confluence={confluence:+.2f} ({bias.value}) | P_inv=${invalidation:.2f} | 1h ATR=${atr_14:.2f}"
        )
        return report
