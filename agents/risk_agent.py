"""Risk Management Agent (Agent #6).

The autonomous institutional capital defense engine. Enforces continuous mark-to-market
portfolio equity tracking, a 5-tier drawdown state machine with hysteresis deadbands,
Cornish-Fisher VaR & Expected Shortfall (CVaR), multi-horizon loss limits, consecutive
loss cooldowns, dynamic exposure ceilings, and trade proposal auditing with absolute veto power.

Sprint 13 Profitability Improvements:
- ATR-based adaptive stop-loss: widens SL in high-vol to prevent noise exits
  (118 trades lost -0.5% to -1.5% in noise zone, costing $2,885)
"""

from datetime import datetime, timezone
from typing import Any, Dict, Optional
import numpy as np
from loguru import logger

from core.events import (
    EVENT_CIRCUIT_BREAKER_TRIPPED,
    EVENT_EMERGENCY_FLATTEN,
    EVENT_RISK_ASSESSMENT,
    event_bus,
)
from core.types import (
    MarketIntelligenceReport,
    RiskAssessment,
    RiskLevel,
    StrategySpecies,
    TradeProposal,
    VolatilityRegime,
    VolatilityReport,
)
from models.portfolio_tracker import PortfolioTracker
from models.var_calculator import VaRCalculator


class RiskManagementAgent:
    """Agent #6: Institutional Gatekeeper and Portfolio Risk Management Engine."""

    def __init__(
        self,
        portfolio_tracker: Optional[PortfolioTracker] = None,
        var_calculator: Optional[VaRCalculator] = None,
        max_dollar_risk_per_trade_pct: float = 0.015,  # 1.5% dollar risk cap
        default_max_gross_exposure_pct: float = 0.50, # 50% max gross exposure
        min_risk_reward_ratio: float = 1.40,          # 1.40 minimum R:R
    ) -> None:
        self.tracker = portfolio_tracker or PortfolioTracker()
        self.var_calc = var_calculator or VaRCalculator()
        self.max_dollar_risk_pct = max_dollar_risk_per_trade_pct
        self.default_max_gross_exposure_pct = default_max_gross_exposure_pct
        self.min_risk_reward_ratio = min_risk_reward_ratio

        # State machine tracking
        self.current_risk_level = RiskLevel.GREEN
        self._evaluate_state_machine()

    def _evaluate_state_machine(self) -> RiskLevel:
        """Evaluates and transitions the 5-tier drawdown state machine with hysteresis deadbands."""
        dd = self.tracker.drawdown_pct
        prior = self.current_risk_level

        # Check for Critical Emergency state (10.0% threshold)
        if dd >= 0.10:
            new_level = RiskLevel.CRITICAL
        elif dd >= 0.08:
            clock = getattr(self.tracker, "current_time", None) or getattr(self.tracker, "calendar_clock", None) or datetime.now(timezone.utc)
            if prior == RiskLevel.RED:
                if self.tracker.recovery_entered_at is not None:
                    elapsed = (clock - self.tracker.recovery_entered_at).total_seconds()
                    # After 24h cooling-off in RED, transition to RECOVERY
                    if elapsed >= 24 * 3600:
                        new_level = RiskLevel.RECOVERY
                    else:
                        new_level = RiskLevel.RED
                else:
                    self.tracker.recovery_entered_at = clock
                    new_level = RiskLevel.RED
            elif prior == RiskLevel.RECOVERY:
                new_level = RiskLevel.RECOVERY
            else:
                self.tracker.recovery_entered_at = clock
                new_level = RiskLevel.RED
        elif dd >= 0.05:
            new_level = RiskLevel.ORANGE
        elif dd >= 0.03:
            new_level = RiskLevel.YELLOW
        else:
            # Drawdown < 3%
            if prior == RiskLevel.YELLOW and dd >= 0.02:
                # Hysteresis: keep YELLOW until DD drops below 2%
                new_level = RiskLevel.YELLOW
            elif prior in (RiskLevel.RED, RiskLevel.CRITICAL):
                # When dropping below 2% from severe drawdown, enter RECOVERY mode
                new_level = RiskLevel.RECOVERY
                if self.tracker.recovery_entered_at is None:
                    self.tracker.recovery_entered_at = datetime.now(timezone.utc)
            elif prior == RiskLevel.RECOVERY:
                # Check 3 exit paths from RECOVERY back to GREEN:
                # Path A: 5 consecutive recovery wins and equity >= HWM
                path_a = (
                    self.tracker.consecutive_recovery_wins >= 5
                    and self.tracker.mtm_equity >= self.tracker.high_water_mark
                )
                # Path B: 3 consecutive recovery wins and equity >= 97% of HWM
                path_b = (
                    self.tracker.consecutive_recovery_wins >= 3
                    and self.tracker.mtm_equity >= 0.97 * self.tracker.high_water_mark
                )
                # Path C: 48 hours elapsed in recovery and DD < 1%
                path_c = False
                if self.tracker.recovery_entered_at is not None:
                    elapsed = (datetime.now(timezone.utc) - self.tracker.recovery_entered_at).total_seconds()
                    if elapsed >= 48 * 3600 and dd < 0.01:
                        path_c = True

                if path_a or path_b or path_c:
                    new_level = RiskLevel.GREEN
                    self.tracker.recovery_entered_at = None
                else:
                    new_level = RiskLevel.RECOVERY
            else:
                new_level = RiskLevel.GREEN

        if new_level != prior:
            logger.warning(
                f"Risk Level Transition: {prior.value} -> {new_level.value} (Current Drawdown: {dd * 100:.2f}%)"
            )
            self.current_risk_level = new_level

            # If Critical, emit emergency flatten
            if new_level == RiskLevel.CRITICAL:
                logger.critical(
                    f"EMERGENCY FLATTEN TRIGGERED: Drawdown has breached 10.0% ({dd * 100:.2f}%). Liquidating risk!"
                )
                event_bus.publish(
                    EVENT_EMERGENCY_FLATTEN,
                    {
                        "trigger": "CRITICAL_DRAWDOWN",
                        "drawdown_pct": dd,
                        "mtm_equity": self.tracker.mtm_equity,
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    },
                )

        return self.current_risk_level

    def get_allowed_size_multiplier(self) -> float:
        """Returns the base position size multiplier dictated by the current risk tier."""
        self._evaluate_state_machine()
        multipliers = {
            RiskLevel.GREEN: 1.0,
            RiskLevel.YELLOW: 0.50,
            RiskLevel.ORANGE: 0.25,
            RiskLevel.RED: 0.0,
            RiskLevel.CRITICAL: 0.0,
            RiskLevel.RECOVERY: 0.50,
        }
        return multipliers.get(self.current_risk_level, 0.0)

    def calculate_max_gross_exposure(
        self,
        market_report: Optional[MarketIntelligenceReport] = None,
        volatility_report: Optional[VolatilityReport] = None,
    ) -> float:
        """Dynamically scales the gross portfolio exposure ceiling based on market regime and sentiment."""
        max_exposure = self.default_max_gross_exposure_pct  # 50% baseline

        # 1. Volatility Regime check (Sprint 4)
        if volatility_report is not None:
            if volatility_report.regime == VolatilityRegime.HIGH_VOL_CHAOS:
                max_exposure = min(max_exposure, 0.20)  # Clamp to 20% in chaos
            elif volatility_report.regime == VolatilityRegime.TRENDING_EXPANSION:
                max_exposure = min(max_exposure, 0.40)  # Max 40% in trending expansion

        # 2. Market Sentiment & Crowding check (Sprint 3)
        if market_report is not None:
            # Extreme Fear or Greed dampens portfolio exposure limit
            fgi = market_report.fear_and_greed_index
            if fgi <= 20 or fgi >= 80:
                max_exposure = min(max_exposure, 0.25)  # Clamp to 25% in extreme sentiment

            # Crowding penalty dampener
            if market_report.crowding_penalty > 0.20:
                max_exposure = min(max_exposure, 0.30)

        # 3. Risk Tier constraint
        tier = self._evaluate_state_machine()
        if tier == RiskLevel.ORANGE:
            max_exposure = min(max_exposure, 0.25)
        elif tier in (RiskLevel.RED, RiskLevel.CRITICAL):
            max_exposure = 0.0

        return float(max_exposure)

    def audit_trade_proposal(
        self,
        proposal: TradeProposal,
        recent_returns: Optional[np.ndarray] = None,
        market_report: Optional[MarketIntelligenceReport] = None,
        volatility_report: Optional[VolatilityReport] = None,
        proposed_position_usd: Optional[float] = None,
    ) -> RiskAssessment:
        """Audits an incoming trade proposal across the 7 mandatory institutional risk gates.

        Returns:
            RiskAssessment object containing the absolute veto decision, allowed size multiplier,
            and complete portfolio risk telemetry.
        """
        try:
            # 1. Update State Machine
            self._evaluate_state_machine()
            equity = self.tracker.mtm_equity
            hwm = self.tracker.high_water_mark
            dd = self.tracker.drawdown_pct
            daily_loss = self.tracker.daily_loss_pct
            weekly_loss = self.tracker.weekly_loss_pct
            remaining_daily_loss = max(0.0, self.tracker.daily_loss_limit_pct - daily_loss)

            # 2. Calculate VaR and CVaR
            returns = recent_returns if recent_returns is not None else np.array([])
            var_summary = self.var_calc.compute_risk_summary(returns, equity)
            var_usd = var_summary["var_95_1day_usd"]
            cvar_usd = var_summary["cvar_95_1day_usd"]

            # 3. Dynamic Gross Exposure Cap
            max_gross_exposure = self.calculate_max_gross_exposure(market_report, volatility_report)
            current_exposure = self.tracker.current_exposure_pct

            # Base allowed sizing multiplier
            tier_multiplier = self.get_allowed_size_multiplier()
            dollar_risk_cap = equity * self.max_dollar_risk_pct

            # Evaluate Circuit Breaker
            is_breaker_active, breaker_reason = self.tracker.get_circuit_breaker_status()

            # --- GATE 1: Drawdown Tier Gate ---
            if self.current_risk_level in (RiskLevel.RED, RiskLevel.CRITICAL):
                return self._build_rejection(
                    reason=f"PORTFOLIO_DRAWDOWN_RESTRICTION (Tier: {self.current_risk_level.value}, DD: {dd*100:.2f}%)",
                    risk_level=self.current_risk_level,
                    equity=equity,
                    hwm=hwm,
                    dd=dd,
                    daily_loss=daily_loss,
                    rem_daily=remaining_daily_loss,
                    weekly_loss=weekly_loss,
                    var_usd=var_usd,
                    cvar_usd=cvar_usd,
                    current_exp=current_exposure,
                    max_exp=max_gross_exposure,
                    breaker_active=False,
                    breaker_reason=None,
                    cap_usd=dollar_risk_cap,
                )

            # --- GATE 2: Circuit Breaker Gate ---
            if is_breaker_active:
                return self._build_rejection(
                    reason=f"CIRCUIT_BREAKER_ACTIVE: {breaker_reason}",
                    risk_level=self.current_risk_level,
                    equity=equity,
                    hwm=hwm,
                    dd=dd,
                    daily_loss=daily_loss,
                    rem_daily=remaining_daily_loss,
                    weekly_loss=weekly_loss,
                    var_usd=var_usd,
                    cvar_usd=cvar_usd,
                    current_exp=current_exposure,
                    max_exp=max_gross_exposure,
                    breaker_active=True,
                    breaker_reason=breaker_reason,
                    cap_usd=dollar_risk_cap,
                )

            # --- GATE 3: Multi-Horizon Loss Limit Gate ---
            if daily_loss >= self.tracker.daily_loss_limit_pct:
                return self._build_rejection(
                    reason=f"DAILY_LOSS_LIMIT_EXCEEDED ({daily_loss*100:.2f}% >= {self.tracker.daily_loss_limit_pct*100:.1f}%)",
                    risk_level=self.current_risk_level,
                    equity=equity,
                    hwm=hwm,
                    dd=dd,
                    daily_loss=daily_loss,
                    rem_daily=remaining_daily_loss,
                    weekly_loss=weekly_loss,
                    var_usd=var_usd,
                    cvar_usd=cvar_usd,
                    current_exp=current_exposure,
                    max_exp=max_gross_exposure,
                    breaker_active=True,
                    breaker_reason="Daily Loss Limit Breached",
                    cap_usd=dollar_risk_cap,
                )

            if weekly_loss >= self.tracker.weekly_loss_limit_pct:
                return self._build_rejection(
                    reason=f"WEEKLY_LOSS_LIMIT_EXCEEDED ({weekly_loss*100:.2f}% >= {self.tracker.weekly_loss_limit_pct*100:.1f}%)",
                    risk_level=self.current_risk_level,
                    equity=equity,
                    hwm=hwm,
                    dd=dd,
                    daily_loss=daily_loss,
                    rem_daily=remaining_daily_loss,
                    weekly_loss=weekly_loss,
                    var_usd=var_usd,
                    cvar_usd=cvar_usd,
                    current_exp=current_exposure,
                    max_exp=max_gross_exposure,
                    breaker_active=True,
                    breaker_reason="Weekly Loss Limit Breached",
                    cap_usd=dollar_risk_cap,
                )

            # --- GATE 4: Consecutive Loss Cooldown Gate ---
            if self.tracker.is_cooldown_active:
                return self._build_rejection(
                    reason="CONSECUTIVE_LOSS_COOLDOWN_ACTIVE",
                    risk_level=self.current_risk_level,
                    equity=equity,
                    hwm=hwm,
                    dd=dd,
                    daily_loss=daily_loss,
                    rem_daily=remaining_daily_loss,
                    weekly_loss=weekly_loss,
                    var_usd=var_usd,
                    cvar_usd=cvar_usd,
                    current_exp=current_exposure,
                    max_exp=max_gross_exposure,
                    breaker_active=False,
                    breaker_reason=None,
                    cap_usd=dollar_risk_cap,
                )

            # --- GATE 5: Stop Loss Distance & Dollar Risk Sanity Gate ---
            p_entry = float(proposal.entry_price)
            p_stop = float(proposal.stop_loss_price)
            if p_entry <= 0.0 or p_stop <= 0.0:
                return self._build_rejection(
                    reason="INVALID_PRICE_DATA (Entry or Stop price <= 0)",
                    risk_level=self.current_risk_level,
                    equity=equity,
                    hwm=hwm,
                    dd=dd,
                    daily_loss=daily_loss,
                    rem_daily=remaining_daily_loss,
                    weekly_loss=weekly_loss,
                    var_usd=var_usd,
                    cvar_usd=cvar_usd,
                    current_exp=current_exposure,
                    max_exp=max_gross_exposure,
                    breaker_active=False,
                    breaker_reason=None,
                    cap_usd=dollar_risk_cap,
                )

            stop_distance_pct = abs(p_entry - p_stop) / p_entry
            if stop_distance_pct < 0.010:  # Less than 1.0% is within 15m/1h candle noise band
                return self._build_rejection(
                    reason=f"STOP_LOSS_TOO_TIGHT ({stop_distance_pct*100:.2f}% < 1.0%)",
                    risk_level=self.current_risk_level,
                    equity=equity,
                    hwm=hwm,
                    dd=dd,
                    daily_loss=daily_loss,
                    rem_daily=remaining_daily_loss,
                    weekly_loss=weekly_loss,
                    var_usd=var_usd,
                    cvar_usd=cvar_usd,
                    current_exp=current_exposure,
                    max_exp=max_gross_exposure,
                    breaker_active=False,
                    breaker_reason=None,
                    cap_usd=dollar_risk_cap,
                )
            if stop_distance_pct > 0.08:  # More than 8% is too wide for intraday execution
                return self._build_rejection(
                    reason=f"STOP_LOSS_TOO_WIDE ({stop_distance_pct*100:.2f}% > 8.0%)",
                    risk_level=self.current_risk_level,
                    equity=equity,
                    hwm=hwm,
                    dd=dd,
                    daily_loss=daily_loss,
                    rem_daily=remaining_daily_loss,
                    weekly_loss=weekly_loss,
                    var_usd=var_usd,
                    cvar_usd=cvar_usd,
                    current_exp=current_exposure,
                    max_exp=max_gross_exposure,
                    breaker_active=False,
                    breaker_reason=None,
                    cap_usd=dollar_risk_cap,
                )

            # Check dollar risk if position size is specified
            effective_multiplier = tier_multiplier
            if proposed_position_usd is not None and proposed_position_usd > 0.0:
                dollar_loss_at_stop = proposed_position_usd * stop_distance_pct
                if dollar_loss_at_stop > dollar_risk_cap:
                    # Mandate sizing downscale rather than outright rejection if viable
                    downscale_factor = dollar_risk_cap / dollar_loss_at_stop
                    effective_multiplier = min(effective_multiplier, downscale_factor)
                    if effective_multiplier < 0.10:
                        return self._build_rejection(
                            reason=f"DOLLAR_RISK_EXCEEDS_CAP (${dollar_loss_at_stop:.2f} > ${dollar_risk_cap:.2f})",
                            risk_level=self.current_risk_level,
                            equity=equity,
                            hwm=hwm,
                            dd=dd,
                            daily_loss=daily_loss,
                            rem_daily=remaining_daily_loss,
                            weekly_loss=weekly_loss,
                            var_usd=var_usd,
                            cvar_usd=cvar_usd,
                            current_exp=current_exposure,
                            max_exp=max_gross_exposure,
                            breaker_active=False,
                            breaker_reason=None,
                            cap_usd=dollar_risk_cap,
                        )

            # --- GATE 6: Gross Exposure Gate ---
            if current_exposure >= max_gross_exposure:
                return self._build_rejection(
                    reason=f"GROSS_EXPOSURE_LIMIT_REACHED ({current_exposure*100:.1f}% >= {max_gross_exposure*100:.1f}%)",
                    risk_level=self.current_risk_level,
                    equity=equity,
                    hwm=hwm,
                    dd=dd,
                    daily_loss=daily_loss,
                    rem_daily=remaining_daily_loss,
                    weekly_loss=weekly_loss,
                    var_usd=var_usd,
                    cvar_usd=cvar_usd,
                    current_exp=current_exposure,
                    max_exp=max_gross_exposure,
                    breaker_active=False,
                    breaker_reason=None,
                    cap_usd=dollar_risk_cap,
                )

            # --- GATE 6.5: Concentration Limit Gate ---
            symbol_positions = [
                pos for pos in self.tracker.get_open_positions()
                if pos.get("symbol") == proposal.symbol
            ]
            if len(symbol_positions) >= 2:
                return self._build_rejection(
                    reason=f"CONCENTRATION_LIMIT_REACHED ({len(symbol_positions)} positions in {proposal.symbol})",
                    risk_level=self.current_risk_level,
                    equity=equity,
                    hwm=hwm,
                    dd=dd,
                    daily_loss=daily_loss,
                    rem_daily=remaining_daily_loss,
                    weekly_loss=weekly_loss,
                    var_usd=var_usd,
                    cvar_usd=cvar_usd,
                    current_exp=current_exposure,
                    max_exp=max_gross_exposure,
                    breaker_active=False,
                    breaker_reason=None,
                    cap_usd=dollar_risk_cap,
                )

            # --- GATE 7: Risk-to-Reward (RR) Sanity Gate ---
            p_target = float(proposal.take_profit_price)
            if p_target > 0.0:
                reward_distance = abs(p_target - p_entry)
                risk_distance = abs(p_entry - p_stop)
                rr_ratio = reward_distance / max(1e-6, risk_distance)
                min_rr = 1.15 if proposal.species == StrategySpecies.MEAN_REVERSION else self.min_risk_reward_ratio
                if rr_ratio < (min_rr - 0.005):
                    return self._build_rejection(
                        reason=f"INSUFFICIENT_RISK_REWARD ({rr_ratio:.2f} < {min_rr:.2f})",
                        risk_level=self.current_risk_level,
                        equity=equity,
                        hwm=hwm,
                        dd=dd,
                        daily_loss=daily_loss,
                        rem_daily=remaining_daily_loss,
                        weekly_loss=weekly_loss,
                        var_usd=var_usd,
                        cvar_usd=cvar_usd,
                        current_exp=current_exposure,
                        max_exp=max_gross_exposure,
                        breaker_active=False,
                        breaker_reason=None,
                        cap_usd=dollar_risk_cap,
                    )

            # Squeeze and Extreme Crowding check
            if market_report is not None and market_report.squeeze_warning:
                if "LONG_SQUEEZE" in market_report.squeeze_warning and proposal.action == "BUY":
                    return self._build_rejection(
                        reason=f"SQUEEZE_RISK_VETO ({market_report.squeeze_warning})",
                        risk_level=self.current_risk_level,
                        equity=equity,
                        hwm=hwm,
                        dd=dd,
                        daily_loss=daily_loss,
                        rem_daily=remaining_daily_loss,
                        weekly_loss=weekly_loss,
                        var_usd=var_usd,
                        cvar_usd=cvar_usd,
                        current_exp=current_exposure,
                        max_exp=max_gross_exposure,
                        breaker_active=False,
                        breaker_reason=None,
                        cap_usd=dollar_risk_cap,
                    )

            # ALL GATES PASSED: APPROVE PROPOSAL
            assessment = RiskAssessment(
                risk_level=self.current_risk_level,
                portfolio_equity=equity,
                high_water_mark=hwm,
                drawdown_pct=dd,
                daily_loss_pct=daily_loss,
                daily_loss_remaining_pct=remaining_daily_loss,
                weekly_loss_pct=weekly_loss,
                var_95_1day_usd=var_usd,
                cvar_95_1day_usd=cvar_usd,
                current_exposure_pct=current_exposure,
                max_exposure_allowed_pct=max_gross_exposure,
                consecutive_losses=self.tracker.consecutive_losses,
                circuit_breaker_active=False,
                circuit_breaker_reason=None,
                cooldown_until=self.tracker.cooldown_until,
                is_proposal_approved=True,
                rejection_reason=None,
                allowed_size_multiplier=round(effective_multiplier, 3),
                dollar_risk_cap_usd=dollar_risk_cap,
            )

            # Publish event
            event_bus.publish(EVENT_RISK_ASSESSMENT, assessment)
            return assessment

        except Exception as e:
            # FAIL-CLOSED BEHAVIOR: Any error in audit immediately vetos the proposal
            logger.critical(f"Unhandled error in RiskManagementAgent audit: {e}. FAILING CLOSED.")
            return RiskAssessment(
                risk_level=RiskLevel.CRITICAL,
                portfolio_equity=self.tracker.mtm_equity,
                high_water_mark=self.tracker.high_water_mark,
                drawdown_pct=self.tracker.drawdown_pct,
                daily_loss_pct=self.tracker.daily_loss_pct,
                daily_loss_remaining_pct=0.0,
                weekly_loss_pct=self.tracker.weekly_loss_pct,
                var_95_1day_usd=0.0,
                cvar_95_1day_usd=0.0,
                current_exposure_pct=self.tracker.current_exposure_pct,
                max_exposure_allowed_pct=0.0,
                consecutive_losses=self.tracker.consecutive_losses,
                circuit_breaker_active=True,
                circuit_breaker_reason=f"Audit Exception: {str(e)}",
                is_proposal_approved=False,
                rejection_reason=f"RISK_AUDIT_EXCEPTION ({str(e)})",
                allowed_size_multiplier=0.0,
                dollar_risk_cap_usd=0.0,
            )

    def _build_rejection(
        self,
        reason: str,
        risk_level: RiskLevel,
        equity: float,
        hwm: float,
        dd: float,
        daily_loss: float,
        rem_daily: float,
        weekly_loss: float,
        var_usd: float,
        cvar_usd: float,
        current_exp: float,
        max_exp: float,
        breaker_active: bool,
        breaker_reason: Optional[str],
        cap_usd: float,
    ) -> RiskAssessment:
        """Constructs and publishes a vetoed RiskAssessment."""
        logger.warning(f"Trade Proposal VETOED by Risk Agent: {reason}")
        assessment = RiskAssessment(
            risk_level=risk_level,
            portfolio_equity=equity,
            high_water_mark=hwm,
            drawdown_pct=dd,
            daily_loss_pct=daily_loss,
            daily_loss_remaining_pct=rem_daily,
            weekly_loss_pct=weekly_loss,
            var_95_1day_usd=var_usd,
            cvar_95_1day_usd=cvar_usd,
            current_exposure_pct=current_exp,
            max_exposure_allowed_pct=max_exp,
            consecutive_losses=self.tracker.consecutive_losses,
            circuit_breaker_active=breaker_active,
            circuit_breaker_reason=breaker_reason,
            cooldown_until=self.tracker.cooldown_until,
            is_proposal_approved=False,
            rejection_reason=reason,
            allowed_size_multiplier=0.0,
            dollar_risk_cap_usd=cap_usd,
        )

        if breaker_active:
            event_bus.publish(
                EVENT_CIRCUIT_BREAKER_TRIPPED,
                {"reason": breaker_reason or reason, "timestamp": datetime.now(timezone.utc).isoformat()},
            )
        event_bus.publish(EVENT_RISK_ASSESSMENT, assessment)
        return assessment
