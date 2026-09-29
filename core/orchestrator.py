"""Master System Orchestrator: Autonomous multi-agent conductor and daemon loop."""

import asyncio
import signal
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
import numpy as np
import pandas as pd
from loguru import logger

from agents.data_quality_agent import DataQualityAgent
from agents.decider_agent import TradeDeciderAgent
from agents.executor_agent import TradeExecutionAgent
from agents.market_agent import MarketIntelligenceAgent
from agents.money_agent import MoneyManagementAgent
from agents.risk_agent import RiskManagementAgent
from agents.strategy_evolution_agent import StrategyEvolutionAgent
from agents.technical_agent import TechnicalAgent
from agents.volatility_agent import VolatilityRegimeAgent
from config.settings import Settings, get_settings
from core.events import (
    EVENT_CIRCUIT_BREAKER_TRIPPED,
    EVENT_EMERGENCY_FLATTEN,
    EVENT_VOLATILITY_REGIME_CHANGE,
    event_bus,
)
from core.scheduler import TimingScheduler
from core.types import (
    AgentState,
    DataPacket,
    ExecutionMode,
    FinalTradeDecision,
    OrderIntent,
    RiskAssessment,
    TradeProposal,
)
from engine.exchange_client import BinanceExchangeClient
from engine.paper_exchange import PaperExchange
from models.portfolio_tracker import PortfolioTracker
from models.system_state import SystemStateManager


class OrchestratorMode(str, Enum):
    """Operational mode of the master system orchestrator."""
    BACKTEST = "BACKTEST"
    PAPER_DAEMON = "PAPER_DAEMON"
    LIVE_DAEMON = "LIVE_DAEMON"


class SystemOrchestrator:
    """Agent Committee Master Conductor coordinating autonomous trading cycles, timing, and recovery."""

    def __init__(
        self,
        mode: OrchestratorMode = OrchestratorMode.PAPER_DAEMON,
        settings: Optional[Settings] = None,
        exchange: Optional[Any] = None,
        portfolio_tracker: Optional[PortfolioTracker] = None,
        checkpoint_path: Optional[str] = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.mode = mode
        self.is_running: bool = False
        self.cycle_count: int = 0
        self.last_retrain_time: Optional[datetime] = None

        # State and Timing engines
        self.scheduler = TimingScheduler()
        self.state_manager = SystemStateManager(checkpoint_path)

        # Portfolio Tracker
        self.tracker = portfolio_tracker or PortfolioTracker(
            initial_equity=10000.0,
            state_file_path=self.settings.CACHE_DIR + "/portfolio_state.json",
        )

        # Execution engine
        exec_mode = ExecutionMode.PAPER if mode != OrchestratorMode.LIVE_DAEMON else ExecutionMode.LIVE_TESTNET
        if exchange is not None:
            self.exchange = exchange
        else:
            self.exchange = (
                PaperExchange(initial_balance_usd=self.tracker.initial_equity)
                if exec_mode == ExecutionMode.PAPER
                else BinanceExchangeClient(testnet=self.settings.TESTNET)
            )

        # Initialize All 9 Autonomous Domain Agents
        logger.info("SystemOrchestrator: Initializing 9-Agent Autonomous Committee...")
        self.dq_agent = DataQualityAgent()
        self.tech_agent = TechnicalAgent()
        self.market_agent = MarketIntelligenceAgent()
        self.vol_agent = VolatilityRegimeAgent()
        self.strat_agent = StrategyEvolutionAgent(population_size=48, tournament_k=3)
        self.risk_agent = RiskManagementAgent(portfolio_tracker=self.tracker)
        self.money_agent = MoneyManagementAgent(reserve_ratio=0.40, kelly_fraction=0.50)
        self.decider_agent = TradeDeciderAgent(consensus_threshold=0.50)
        self.executor_agent = TradeExecutionAgent(
            exchange=self.exchange,
            portfolio_tracker=self.tracker,
            mode=exec_mode,
        )

        # Subscribe to internal cross-agent control events
        event_bus.subscribe(EVENT_VOLATILITY_REGIME_CHANGE, self._on_regime_change)

    def _on_regime_change(self, regime_data: Any) -> None:
        """Forces an out-of-band GA retraining cycle when a volatility regime change is detected."""
        if self.mode != OrchestratorMode.BACKTEST:
            logger.warning("SystemOrchestrator: Regime change detected! Queuing immediate GA retraining.")
            self.last_retrain_time = None

    def recover_state(self) -> bool:
        """Recovers state checkpoint from disk and restores open positions and bracket managers."""
        checkpoint = self.state_manager.load_checkpoint()
        if not checkpoint:
            return False

        try:
            # Restore cycle counter
            self.cycle_count = int(checkpoint.get("cycles_count", 0))

            # Restore champion
            champ_data = checkpoint.get("champion", {})
            if champ_data.get("strategy_id"):
                retrain_str = champ_data.get("last_retrain_time")
                if retrain_str:
                    self.last_retrain_time = datetime.fromisoformat(retrain_str)

            # Restore portfolio tracker metrics
            port_data = checkpoint.get("portfolio", {})
            if port_data:
                self.tracker.current_cash = float(port_data.get("cash", self.tracker.current_cash))
                self.tracker.high_water_mark = float(port_data.get("high_water_mark", self.tracker.high_water_mark))

            # Restore active positions and brackets
            restored_positions = self.state_manager.restore_positions(
                checkpoint, self.executor_agent.bracket_manager
            )

            logger.info(f"SystemOrchestrator: Recovery complete. Resumed with {restored_positions} active positions.")
            return True
        except Exception as e:
            logger.error(f"SystemOrchestrator: Failed to restore checkpoint state: {e}")
            return False

    async def run_single_cycle(
        self,
        packet: DataPacket,
        execute_orders: bool = True,
    ) -> Dict[str, Any]:
        """
        Executes a single end-to-end multi-agent governance and decision cycle:
        Data Quality -> Technical & Market & Volatility -> Strategy Signal -> 3-Layer Gate -> Execution.
        """
        self.cycle_count += 1
        cycle_start_time = datetime.now(timezone.utc)
        logger.info(f"SystemOrchestrator: Starting Cycle #{self.cycle_count} for {packet.symbol}...")

        # [Step 1] Agent 1: Data Quality Audit (Fail-Closed Veto)
        if not packet.quality.is_tradeable or packet.quality.overall_quality < self.settings.MIN_DATA_QUALITY:
            logger.warning(
                f"SystemOrchestrator: Cycle #{self.cycle_count} HALTED by Data Quality Agent! "
                f"Score: {packet.quality.overall_quality:.1%}"
            )
            self._save_checkpoint()
            return {
                "cycle": self.cycle_count,
                "status": "HALTED_DATA_QUALITY_VETO",
                "quality_score": packet.quality.overall_quality,
            }

        if self.mode != OrchestratorMode.BACKTEST:
            self.dq_agent.evaluate_data(packet.symbol, packet.timeframes)
            dq_report = self.dq_agent.build_data_packet(packet.symbol)
            if dq_report is None or not dq_report.quality.is_tradeable or dq_report.quality.overall_quality < self.settings.MIN_DATA_QUALITY:
                logger.warning(
                    f"SystemOrchestrator: Cycle #{self.cycle_count} HALTED by Data Quality Agent! "
                    f"Score: {packet.quality.overall_quality:.1%}"
                )
                self._save_checkpoint()
                return {
                    "cycle": self.cycle_count,
                    "status": "HALTED_DATA_QUALITY_VETO",
                    "quality_score": packet.quality.overall_quality,
                }

        # Early check: Maximum concurrent positions constraint, symbol concentration, or loss cooldown
        open_positions = [
            p for p in self.executor_agent.bracket_manager.positions.values() if p.quantity > 0
        ]
        symbol_pos_count = len([p for p in open_positions if p.symbol == packet.symbol])
        is_cooldown = getattr(self.tracker, "is_cooldown_active", False)

        if (
            len(open_positions) >= self.settings.MAX_CONCURRENT_POSITIONS
            or symbol_pos_count >= getattr(self.risk_agent, "max_positions_per_symbol", 2)
            or is_cooldown
        ):
            # Maintain GA Retraining cadence even while new entries are suppressed
            if self.scheduler.is_retrain_due(self.last_retrain_time, self.settings.RETRAIN_INTERVAL_HOURS):
                logger.info(f"SystemOrchestrator: GA Retraining due. Training population for {packet.symbol}...")
                df_1h = packet.timeframes.get("1h", packet.timeframes.get("15m"))
                vol_report = self.vol_agent.analyze(packet)
                self.strat_agent.train(df_1h, generations=3, regime=vol_report.regime)
                self.last_retrain_time = datetime.now(timezone.utc)

            self._save_checkpoint()
            return {
                "cycle": self.cycle_count,
                "status": "SUPPRESSED_ENTRY_GUARD",
                "active_positions": len(open_positions),
                "symbol_positions": symbol_pos_count,
                "cooldown_active": is_cooldown,
            }

        # [Step 2] Concurrent Intelligence Ingestion (Agents 2, 3, 4)
        tech_report = self.tech_agent.analyze(packet)
        vol_report = self.vol_agent.analyze(packet)

        # Market Intelligence (async live derivatives + sentiment)
        if self.mode == OrchestratorMode.BACKTEST:
            market_report = self.market_agent.analyze(packet)
        else:
            market_report = await self.market_agent.analyze_live(packet)

        # [Step 3] GA Retraining Check (Agent 5)
        if self.scheduler.is_retrain_due(self.last_retrain_time, self.settings.RETRAIN_INTERVAL_HOURS):
            logger.info(f"SystemOrchestrator: GA Retraining due. Training population for {packet.symbol}...")
            df_1h = packet.timeframes.get("1h", packet.timeframes["15m"])
            self.strat_agent.train(df_1h, generations=3, regime=vol_report.regime)
            self.last_retrain_time = datetime.now(timezone.utc)

        # [Step 4] Strategy Signal Generation (Agent 5)
        proposal: Optional[TradeProposal] = self.strat_agent.evaluate_live(packet)
        if proposal is None or proposal.action == "HOLD":
            logger.info(f"SystemOrchestrator: Cycle #{self.cycle_count} completed. No actionable trade signal (HOLD).")
            self._save_checkpoint()
            return {
                "cycle": self.cycle_count,
                "status": "HOLD",
                "consensus_decision": "NO_ACTION",
            }

        # [Step 5] 3-Layer Defense Gatekeeper
        # Layer 1: Risk Agent 7-Gate Proposal Audit
        returns_15m = packet.timeframes["15m"]["close"].pct_change().dropna().values
        risk_audit: RiskAssessment = self.risk_agent.audit_trade_proposal(
            proposal=proposal,
            recent_returns=returns_15m,
            market_report=market_report,
            volatility_report=vol_report,
            proposed_position_usd=1500.0,
        )

        # Layer 2: Money Management Fractional Kelly Sizing
        money_decision = self.money_agent.evaluate_position_size(
            proposal=proposal,
            risk_assessment=risk_audit,
            market_report=market_report,
            volatility_report=vol_report,
        )

        # Layer 3: Trade Decider Boardroom Consensus Vote
        final_decision, order_intent = self.decider_agent.evaluate_and_decide(
            proposal=proposal,
            data_report=packet.quality,
            tech_report=tech_report,
            market_report=market_report,
            vol_report=vol_report,
            risk_assessment=risk_audit,
            money_decision=money_decision,
        )

        # [Step 6] Execution Router (Agent 9)
        execution_report = None
        if execute_orders and order_intent is not None:
            bracket, execution_report = self.executor_agent.execute_order_intent(order_intent)
            logger.info(
                f"SystemOrchestrator: OrderIntent Executed by Agent #9. Bracket: {bracket.bracket_id}, Status: {execution_report.status.value}"
            )

        # [Step 7] Save atomic checkpoint
        self._save_checkpoint()

        return {
            "cycle": self.cycle_count,
            "status": "COMPLETED",
            "decision": final_decision.decision,
            "consensus_score": final_decision.consensus_score,
            "order_intent": order_intent.to_dict() if order_intent else None,
            "execution_status": execution_report.status.value if execution_report else None,
        }

    def _save_checkpoint(self) -> None:
        """Persists current state snapshot to disk."""
        if self.mode == OrchestratorMode.BACKTEST:
            return

        champion = getattr(self.strat_agent, "active_champion", None) or getattr(self.strat_agent.pop_mgr, "champion", None)
        positions = list(self.executor_agent.bracket_manager.positions.values())
        brackets = list(self.executor_agent.bracket_manager.brackets.values())

        agent_states = {
            "data_quality": self.dq_agent.state.value,
            "risk_tier": self.risk_agent.current_risk_level.value,
            "execution_agent": self.executor_agent.state.value,
        }

        champ_id = None
        champ_genome = None
        champ_species = None
        if champion is not None:
            champ_id = getattr(champion, "strategy_id", None)
            if hasattr(champion, "genome") and hasattr(champion.genome, "to_dict"):
                champ_genome = champion.genome.to_dict()
            elif hasattr(champion, "to_dict"):
                champ_genome = champion.to_dict()
            species_val = getattr(champion, "species", None)
            champ_species = species_val.value if hasattr(species_val, "value") else str(species_val) if species_val else None

        self.state_manager.save_checkpoint(
            champion_id=champ_id,
            champion_genome=champ_genome,
            champion_species=champ_species,
            last_retrain_time=self.last_retrain_time,
            positions=positions,
            brackets=brackets,
            portfolio_cash=self.tracker.current_cash,
            portfolio_hwm=self.tracker.high_water_mark,
            portfolio_drawdown=self.tracker.drawdown_pct,
            agent_states=agent_states,
            cycles_count=self.cycle_count,
        )

    async def shutdown(self) -> None:
        """Executes clean graceful shutdown: closes network sessions and flushes state snapshot."""
        logger.info("SystemOrchestrator: Initiating graceful shutdown sequence...")
        self.is_running = False

        # Close async network clients
        if hasattr(self.market_agent, "close"):
            await self.market_agent.close()

        # Save final checkpoint
        self._save_checkpoint()
        logger.info("SystemOrchestrator: Shutdown complete. System state safely checkpointed.")
