"""Volatility & Regime Forecaster Agent: Statistical volatility modeling and regime classification."""

from datetime import datetime, timezone
from typing import Optional
from loguru import logger

from core.events import (
    EVENT_VOLATILITY_REGIME_CHANGE,
    EVENT_VOLATILITY_REPORT,
    event_bus,
)
from core.types import DataPacket, VolatilityRegime, VolatilityReport
from models.regime_classifier import RegimeClassifier
from models.volatility_models import (
    calculate_ewma_volatility,
    calculate_garman_klass_volatility,
    calculate_parkinson_volatility,
    forecast_garch_volatility,
)
from models.volatility_multiplier import VolatilityMultiplierCalculator


class VolatilityRegimeAgent:
    """
    Agent #4: Volatility & Regime Forecaster Agent.
    Subscribes to validated DataPackets, executes continuous High-Low and conditional
    variance estimators (Parkinson, Garman-Klass, GARCH(1,1)), classifies market state into
    3 statistical regimes, and produces dynamic position and stop multipliers.
    """

    def __init__(
        self,
        regime_classifier: Optional[RegimeClassifier] = None,
        multiplier_calculator: Optional[VolatilityMultiplierCalculator] = None,
    ) -> None:
        self.classifier = regime_classifier or RegimeClassifier()
        self.multiplier_calculator = multiplier_calculator or VolatilityMultiplierCalculator()
        self.last_report: Optional[VolatilityReport] = None
        self._current_regime: Optional[VolatilityRegime] = None

    def analyze(self, packet: DataPacket) -> VolatilityReport:
        """
        Analyzes volatility structure of the provided DataPacket.
        """
        symbol = packet.symbol
        # Primary analysis on 1h candles
        df_1h = packet.timeframes.get("1h")
        if df_1h is None or len(df_1h) < 20:
            df_1h = next(iter(packet.timeframes.values()))

        # Extract features (or compute log returns on the fly)
        if "1h" in packet.features and "log_returns" in packet.features["1h"]:
            log_returns = packet.features["1h"]["log_returns"]
        else:
            prev_c = df_1h["close"].shift(1)
            log_returns = (df_1h["close"] / prev_c).apply(lambda x: 0.0 if x <= 0 else float(x)).pipe(lambda s: s.apply(lambda v: 0.0 if v == 0 else float(v)))

        # 1. Calculate Volatility Estimators
        parkinson_vol = calculate_parkinson_volatility(df_1h, window=24, timeframe="1h")
        garman_klass_vol = calculate_garman_klass_volatility(df_1h, window=24, timeframe="1h")
        ewma_vol = calculate_ewma_volatility(log_returns, lambda_param=0.94, timeframe="1h")
        forecast_vol_24h = forecast_garch_volatility(log_returns, horizon_steps=24, timeframe="1h")

        # 2. Classify Statistical Volatility Regime
        regime, percentile, is_breakout_imminent = self.classifier.classify_regime(
            df=df_1h,
            current_parkinson_vol=parkinson_vol,
        )

        # 3. Calculate Dynamic Sizing & Stop Multipliers
        size_mult, stop_mult = self.multiplier_calculator.calculate_multipliers(
            regime=regime,
            volatility_percentile=percentile,
        )

        report = VolatilityReport(
            symbol=symbol,
            forecasted_volatility_24h=forecast_vol_24h,
            parkinson_volatility=parkinson_vol,
            garman_klass_volatility=garman_klass_vol,
            ewma_volatility=ewma_vol,
            volatility_percentile=percentile,
            regime=regime,
            volatility_multiplier=size_mult,
            atr_stop_multiplier=stop_mult,
            is_breakout_imminent=is_breakout_imminent,
            timestamp=datetime.now(timezone.utc),
        )

        # Check for Regime Transition Event
        if self._current_regime is not None and self._current_regime != regime:
            logger.info(
                f"VOLATILITY REGIME TRANSITION [{symbol}]: {self._current_regime.value} -> {regime.value} (Vol Percentile: {percentile:.1f}%)"
            )
            event_bus.publish(EVENT_VOLATILITY_REGIME_CHANGE, {
                "symbol": symbol,
                "previous_regime": self._current_regime.value,
                "new_regime": regime.value,
                "report": report,
            })

        self._current_regime = regime
        self.last_report = report

        # Publish report on Event Bus
        event_bus.publish(EVENT_VOLATILITY_REPORT, report)

        logger.info(
            f"Volatility Forecaster [{symbol}]: Regime={regime.value} | 24h Forecast={forecast_vol_24h:.1f}% | Sizing Mult={size_mult:.2f}x | Stop Mult={stop_mult:.2f}x | Imminent Breakout={is_breakout_imminent}"
        )
        return report
