"""Multi-Agent Weighted Consensus Matrix and Conflict Resolution Engine.

Aggregates conviction votes from Data Quality, Technical Analysis, Market Intelligence,
Volatility Forecaster, Strategy Evolution, Risk Management, and Money Management Agents.
Enforces dynamic sentiment re-weighting, inter-agent conflict detection, and absolute vetoes.
"""

from typing import Any, Dict, List, Optional, Tuple
import numpy as np
from loguru import logger

from core.types import (
    CrowdingBias,
    DataQualityReport,
    MarketIntelligenceReport,
    MoneyDecision,
    PositioningQuadrant,
    RiskAssessment,
    RiskLevel,
    StrategySpecies,
    TechnicalAnalysisReport,
    TradeProposal,
    VolatilityRegime,
    VolatilityReport,
)


class ConsensusMatrixEngine:
    """Boardroom voting engine synthesizing multi-agent conviction into an actionable verdict."""

    DEFAULT_WEIGHTS = {
        "data_quality": 0.10,
        "technical_analysis": 0.15,
        "market_intelligence": 0.15,
        "volatility_forecaster": 0.10,
        "strategy_evolution": 0.20,
        "risk_management": 0.15,
        "money_management": 0.15,
    }

    @classmethod
    def compute_dynamic_weights(
        cls,
        market_report: Optional[MarketIntelligenceReport] = None,
        volatility_report: Optional[VolatilityReport] = None,
    ) -> Dict[str, float]:
        """Dynamically reallocates voting weights based on extreme sentiment and volatility chaos."""
        weights = dict(cls.DEFAULT_WEIGHTS)

        # 1. Macro Sentiment Extremes (Smooth sigmoid-style scaling based on distance from neutral 50)
        if market_report is not None:
            fgi = market_report.fear_and_greed_index
            # Extremity: 0.0 at FGI=50 (distance <= 15), ramping continuously to 1.0 at FGI=0 or FGI=100
            fgi_extremity = max(0.0, (abs(fgi - 50) - 15) / 35.0)
            fgi_extremity = float(np.clip(fgi_extremity, 0.0, 1.0))
            weights["strategy_evolution"] -= 0.05 * fgi_extremity
            weights["market_intelligence"] += 0.03 * fgi_extremity
            weights["risk_management"] += 0.02 * fgi_extremity

        # 2. Volatility Regime Chaos (Sprint 4)
        if volatility_report is not None:
            if volatility_report.regime == VolatilityRegime.HIGH_VOL_CHAOS:
                weights["strategy_evolution"] -= 0.05
                weights["risk_management"] += 0.03
                weights["volatility_forecaster"] += 0.02

        # Normalize sum of weights to exactly 1.0
        total_w = sum(weights.values())
        return {k: v / total_w for k, v in weights.items()}

    @classmethod
    def evaluate_boardroom_vote(
        cls,
        proposal: TradeProposal,
        data_report: Optional[DataQualityReport] = None,
        tech_report: Optional[TechnicalAnalysisReport] = None,
        market_report: Optional[MarketIntelligenceReport] = None,
        vol_report: Optional[VolatilityReport] = None,
        risk_assessment: Optional[RiskAssessment] = None,
        money_decision: Optional[MoneyDecision] = None,
        consensus_threshold: float = 0.65,
    ) -> Dict[str, Any]:
        """Conducts full multi-agent boardroom vote, scanning for conflicts and vetoes."""
        weights = cls.compute_dynamic_weights(market_report, vol_report)
        agent_votes: Dict[str, Dict[str, Any]] = {}
        vetoes_triggered: List[str] = []
        conflicts_detected: List[str] = []

        # 1. Vote: Data Quality Agent (Agent #1)
        if data_report is not None:
            score_dq = float(data_report.overall_quality)
            if score_dq < 0.85 or not data_report.is_tradeable:
                vetoes_triggered.append(f"DATA_QUALITY_VETO (Score={score_dq:.2f})")
            agent_votes["data_quality"] = {
                "score": round(score_dq, 3),
                "weight": round(weights["data_quality"], 3),
                "vote": "APPROVE" if score_dq >= 0.85 else "REJECT",
            }
        else:
            agent_votes["data_quality"] = {"score": 1.0, "weight": weights["data_quality"], "vote": "APPROVE"}

        # 2. Vote: Technical Analysis Agent (Agent #2)
        if tech_report is not None:
            conf = tech_report.confluence_score
            # For Mean Reversion, counter-trend setups are valid when fading price extremes
            if proposal.species == StrategySpecies.MEAN_REVERSION:
                aligned_conf = conf if proposal.action == "BUY" else -conf
                score_tech = float(np.clip(0.60 + 0.30 * aligned_conf, 0.35, 0.90))
            else:
                aligned_conf = conf if proposal.action == "BUY" else -conf
                score_tech = float(np.clip(0.5 + 0.5 * aligned_conf, 0.0, 1.0))

            # Conflict check: Strong technical disagreement (exempt Mean Reversion fading)
            if proposal.species != StrategySpecies.MEAN_REVERSION and aligned_conf < -0.35:
                conflicts_detected.append(
                    f"TECHNICAL_DIRECTION_CONFLICT (Proposal={proposal.action}, Confluence={conf:+.2f})"
                )

            agent_votes["technical_analysis"] = {
                "score": round(score_tech, 3),
                "weight": round(weights["technical_analysis"], 3),
                "vote": "APPROVE" if score_tech >= 0.50 else "REJECT",
            }
        else:
            agent_votes["technical_analysis"] = {"score": 0.70, "weight": weights["technical_analysis"], "vote": "APPROVE"}

        # 3. Vote: Market Intelligence Agent (Agent #3)
        if market_report is not None:
            score_mkt = float(np.clip(1.0 - market_report.crowding_penalty, 0.0, 1.0))
            if market_report.squeeze_warning:
                if "LONG_SQUEEZE" in market_report.squeeze_warning and proposal.action == "BUY":
                    vetoes_triggered.append(f"MARKET_SQUEEZE_VETO ({market_report.squeeze_warning})")
                    score_mkt = 0.0
                elif "SHORT_SQUEEZE" in market_report.squeeze_warning and proposal.action == "SELL":
                    vetoes_triggered.append(f"MARKET_SQUEEZE_VETO ({market_report.squeeze_warning})")
                    score_mkt = 0.0

            agent_votes["market_intelligence"] = {
                "score": round(score_mkt, 3),
                "weight": round(weights["market_intelligence"], 3),
                "vote": "APPROVE" if score_mkt >= 0.60 else "REJECT",
            }
        else:
            agent_votes["market_intelligence"] = {"score": 0.75, "weight": weights["market_intelligence"], "vote": "APPROVE"}

        # 4. Vote: Volatility Forecaster Agent (Agent #4)
        if vol_report is not None:
            # Score scaled by sizing multiplier [0.4 to 1.3]
            score_vol = float(np.clip(vol_report.volatility_multiplier / 1.20, 0.0, 1.0))

            # Conflict check: Mean Reversion in Chaos
            if proposal.species == StrategySpecies.MEAN_REVERSION and vol_report.regime == VolatilityRegime.HIGH_VOL_CHAOS:
                conflicts_detected.append("REGIME_MISMATCH (Mean Reversion inside High Vol Chaos)")

            agent_votes["volatility_forecaster"] = {
                "score": round(score_vol, 3),
                "weight": round(weights["volatility_forecaster"], 3),
                "vote": "APPROVE" if score_vol >= 0.50 else "REJECT",
            }
        else:
            agent_votes["volatility_forecaster"] = {"score": 0.75, "weight": weights["volatility_forecaster"], "vote": "APPROVE"}

        # 5. Vote: Strategy Evolution Agent (Agent #5)
        score_strat = float(np.clip(proposal.confidence, 0.0, 1.0))

        # Check technical neutrality floor and alignment
        if tech_report is not None:
            if abs(tech_report.confluence_score) < 0.10:
                score_strat = min(score_strat, 0.60)
                conflicts_detected.append("STRATEGY_TECH_FLOOR_CONFLICT (Neutral Technical Floor)")
            else:
                aligned_conf = tech_report.confluence_score if proposal.action == "BUY" else -tech_report.confluence_score
                if aligned_conf < -0.30:
                    score_strat = min(score_strat, 0.55)

        agent_votes["strategy_evolution"] = {
            "score": round(score_strat, 3),
            "weight": round(weights["strategy_evolution"], 3),
            "vote": "APPROVE" if score_strat >= 0.50 else "REJECT",
        }

        # 6. Vote: Risk Management Agent (Agent #6)
        if risk_assessment is not None:
            if not risk_assessment.is_proposal_approved:
                vetoes_triggered.append(f"RISK_AGENT_VETO ({risk_assessment.rejection_reason})")
                score_risk = 0.0
            else:
                score_risk = float(risk_assessment.allowed_size_multiplier)
            agent_votes["risk_management"] = {
                "score": round(score_risk, 3),
                "weight": round(weights["risk_management"], 3),
                "vote": "APPROVE" if risk_assessment.is_proposal_approved else "REJECT",
            }
        else:
            agent_votes["risk_management"] = {"score": 1.0, "weight": weights["risk_management"], "vote": "APPROVE"}

        # 7. Vote: Money Management Agent (Agent #7)
        if money_decision is not None:
            if not money_decision.is_sizing_approved:
                vetoes_triggered.append(f"MONEY_AGENT_VETO ({money_decision.rejection_reason})")
                score_money = 0.0
            else:
                score_money = 1.0
            agent_votes["money_management"] = {
                "score": round(score_money, 3),
                "weight": round(weights["money_management"], 3),
                "vote": "APPROVE" if money_decision.is_sizing_approved else "REJECT",
            }
        else:
            agent_votes["money_management"] = {"score": 1.0, "weight": weights["money_management"], "vote": "APPROVE"}

        # Compute Total Weighted Consensus Score
        raw_consensus = sum(v["score"] * v["weight"] for v in agent_votes.values())

        # Penalty for detected conflicts (-0.05 per conflict, capped at -0.10 total)
        conflict_penalty = min(len(conflicts_detected) * 0.05, 0.10)
        final_consensus = float(max(0.0, raw_consensus - conflict_penalty))

        # Final Decision Logic (calibrated thresholds)
        rejection_threshold = consensus_threshold * 0.80  # ~0.52 with default 0.65
        if len(vetoes_triggered) > 0:
            decision = "REJECTED"
            reason = f"VETOED by gatekeeper: {'; '.join(vetoes_triggered)}"
        elif final_consensus < rejection_threshold:
            decision = "REJECTED"
            reason = f"INSUFFICIENT_CONSENSUS ({final_consensus:.2f} < {rejection_threshold:.2f})"
        elif final_consensus < consensus_threshold or len(conflicts_detected) >= 1:
            decision = "DOWNSIZED"
            reason = f"APPROVED_WITH_CAUTION (Consensus={final_consensus:.2f}, Conflicts={len(conflicts_detected)})"
        else:
            decision = "APPROVED"
            reason = f"STRONG_CONSENSUS_APPROVED (Score={final_consensus:.2f} >= {consensus_threshold:.2f})"

        return {
            "decision": decision,
            "consensus_score": final_consensus,
            "raw_consensus_score": raw_consensus,
            "consensus_threshold": consensus_threshold,
            "agent_votes": agent_votes,
            "vetoes_triggered": vetoes_triggered,
            "conflicts_detected": conflicts_detected,
            "reason": reason,
        }
