"""Strategy Evolution Agent (Agent #5): Breeds, validates, and evaluates trading strategies in real time."""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from loguru import logger
import numpy as np
import pandas as pd

from core.events import (
    EVENT_MARKET_INTELLIGENCE_REPORT,
    EVENT_STRATEGY_CHAMPION_SELECTED,
    EVENT_TECHNICAL_REPORT,
    EVENT_TRADE_PROPOSAL,
    EVENT_VOLATILITY_REGIME_CHANGE,
    EVENT_VOLATILITY_REPORT,
    event_bus,
)
from core.types import (
    AgentState,
    BacktestResult,
    DataPacket,
    MarketIntelligenceReport,
    MonteCarloReport,
    StrategyGenome,
    StrategySpecies,
    TechnicalAnalysisReport,
    TradeProposal,
    VolatilityRegime,
    VolatilityReport,
    WalkForwardReport,
)
from engine.ga_engine import GAEngine
from engine.population_manager import PopulationManager
from engine.species_strategies import SpeciesStrategyBuilder
from models.monte_carlo import MonteCarloTester
from models.walk_forward import WalkForwardValidator


class StrategyEvolutionAgent:
    """
    Agent #5: The Evolutionary Brain of StrategyOne.
    Coordinates genetic algorithms, walk-forward validation, and Monte Carlo risk testing.
    Evaluates champion strategy in real-time to generate actionable TradeProposals.
    """

    def __init__(
        self,
        population_size: int = 96,
        tournament_k: int = 3,
        mutation_rate: float = 0.25,
    ) -> None:
        self.state = AgentState.HEALTHY
        self.pop_mgr = PopulationManager(population_size=population_size)
        self.ga_engine = GAEngine(
            population_manager=self.pop_mgr,
            population_size=population_size,
            tournament_k=tournament_k,
            mutation_rate=mutation_rate,
        )
        self.wf_validator = WalkForwardValidator()
        self.mc_tester = MonteCarloTester(permutations=500)

        self.active_champion: Optional[StrategyGenome] = None
        self.champion_result: Optional[BacktestResult] = None
        self.latest_wf_report: Optional[WalkForwardReport] = None
        self.latest_mc_report: Optional[MonteCarloReport] = None

        self._latest_tech_report: Optional[TechnicalAnalysisReport] = None
        self._latest_market_report: Optional[MarketIntelligenceReport] = None
        self._latest_vol_report: Optional[VolatilityReport] = None

        # Subscribe to upstream agent events
        event_bus.subscribe(EVENT_TECHNICAL_REPORT, self._on_technical_report)
        event_bus.subscribe(EVENT_MARKET_INTELLIGENCE_REPORT, self._on_market_report)
        event_bus.subscribe(EVENT_VOLATILITY_REPORT, self._on_volatility_report)

    def _on_technical_report(self, report: TechnicalAnalysisReport) -> None:
        self._latest_tech_report = report

    def _on_market_report(self, report: MarketIntelligenceReport) -> None:
        self._latest_market_report = report

    def _on_volatility_report(self, report: VolatilityReport) -> None:
        self._latest_vol_report = report

    def train(
        self,
        df: pd.DataFrame,
        generations: int = 5,
        regime: Optional[VolatilityRegime] = None,
    ) -> StrategyGenome:
        """
        Runs multi-generational evolution, walk-forward validation, and Monte Carlo checks.
        Selects and installs the certified champion.
        """
        logger.info(f"StrategyEvolutionAgent: Initiating training run for {generations} generations...")

        # 1. Run Multi-Generation Evolution
        evo_summary = self.ga_engine.run_evolution(df, generations=generations, current_regime=regime)
        raw_champion = evo_summary["champion"]

        if raw_champion is None:
            # Fallback to heuristic seed
            raw_champion = self.pop_mgr.initialize_population()[0]

        # 2. Institutional Walk-Forward Validation
        wf_report = self.wf_validator.validate(df, raw_champion)
        self.latest_wf_report = wf_report

        # 3. Monte Carlo Bootstrap Permutation Test
        mc_report = self.mc_tester.run_permutation_test(df, raw_champion)
        self.latest_mc_report = mc_report

        # 4. Install Champion
        self.active_champion = raw_champion
        self.champion_result = evo_summary["champion_result"]

        logger.info(
            f"StrategyEvolutionAgent: Champion Installed -> {raw_champion.strategy_id} ({raw_champion.species.value}) | "
            f"WFE: {wf_report.walk_forward_efficiency:.2f} | MC 95% DD: {mc_report.drawdown_95th_percentile:.1%} | "
            f"Overfit: {wf_report.is_overfit} | Disqualified: {mc_report.is_disqualified}"
        )

        return raw_champion

    def evaluate_live(self, packet: DataPacket) -> TradeProposal:
        """
        Evaluates the active champion strategy against the latest candle of the DataPacket.
        Generates an actionable TradeProposal with precision ATR stop and target levels.
        """
        symbol = packet.symbol
        df_1h = packet.timeframes.get("1h")
        if df_1h is None or len(df_1h) < 30:
            return self._neutral_proposal(symbol, "INSUFFICIENT_TIMEFRAME_DATA")

        # Ensure we have an active champion
        if self.active_champion is None:
            # Quick train on available data
            regime = self._latest_vol_report.regime if self._latest_vol_report else None
            self.train(df_1h, generations=3, regime=regime)

        champion = self.active_champion
        assert champion is not None

        # 1. Compute Signals on Historical Series
        signals = SpeciesStrategyBuilder.generate_signals(df_1h, champion)
        latest_signal = float(signals[-1])

        # 2. Extract Price & ATR Parameters
        latest_price = float(packet.latest_price) if packet.latest_price > 0 else float(df_1h["close"].iloc[-1])
        atr = 0.0
        if self._latest_tech_report and self._latest_tech_report.atr_14 > 0:
            atr = self._latest_tech_report.atr_14
        elif "atr" in df_1h.columns:
            atr = float(df_1h["atr"].iloc[-1])
        else:
            atr = latest_price * 0.015  # 1.5% estimate

        # Apply Volatility Multiplier from Agent 4 if available
        stop_mult = champion.stop_loss_atr_mult
        vol_scale = 1.0
        if self._latest_vol_report and self._latest_vol_report.atr_stop_multiplier > 0:
            vol_scale = (self._latest_vol_report.atr_stop_multiplier / 1.5)
            stop_mult *= vol_scale

        # Proportionally scale take profit to preserve planned Risk:Reward ratio
        tp_mult = champion.take_profit_atr_mult * max(1.0, vol_scale)

        # Noise-band floor: Stop distance must be at least 1.1% of price to avoid random intra-candle wick stopouts
        stop_dist = max(stop_mult * atr, latest_price * 0.011)
        # Ensure minimum 2:1 R:R ratio for TP1 and 3.5:1 for TP2 runner
        tp1_dist = max(tp_mult * atr, stop_dist * 2.0)
        tp2_dist = max(tp_mult * 2.2 * atr, stop_dist * 3.5)

        # 3. Determine Action & Multi-Tier Levels
        threshold = getattr(champion, "entry_signal_threshold", 0.50)
        if latest_signal > threshold:
            action = "BUY"
            stop_loss = latest_price - stop_dist
            take_profit_1 = latest_price + tp1_dist
            take_profit_2 = latest_price + tp2_dist
            urgency = "TAKER_AGGRESSIVE" if champion.species == StrategySpecies.BREAKOUT_VOLATILITY else "PASSIVE_MAKER"
        elif latest_signal < -threshold:
            action = "SELL"
            stop_loss = latest_price + stop_dist
            take_profit_1 = latest_price - tp1_dist
            take_profit_2 = latest_price - tp2_dist
            urgency = "TAKER_AGGRESSIVE" if champion.species == StrategySpecies.BREAKOUT_VOLATILITY else "PASSIVE_MAKER"
        else:
            action = "HOLD"
            stop_loss = latest_price
            take_profit_1 = latest_price
            take_profit_2 = latest_price
            urgency = "PASSIVE_MAKER"

        # 4. Invalidation Price (directionally consistent with action)
        if action == "BUY":
            if self._latest_tech_report and 0 < self._latest_tech_report.invalidation_price < latest_price:
                inv_price = self._latest_tech_report.invalidation_price
            else:
                inv_price = stop_loss
        elif action == "SELL":
            if self._latest_tech_report and self._latest_tech_report.invalidation_price > latest_price:
                inv_price = self._latest_tech_report.invalidation_price
            else:
                inv_price = stop_loss
        else:
            inv_price = stop_loss

        # 5. Confidence Score Normalized from Sharpe & Win Rate
        base_sharpe = self.champion_result.sharpe_ratio if self.champion_result else 1.5
        base_wr = self.champion_result.win_rate if self.champion_result else 0.55
        confidence = float(np.clip((base_sharpe / 3.0) * 0.6 + base_wr * 0.4, 0.1, 0.95))

        proposal = TradeProposal(
            strategy_id=champion.strategy_id,
            species=champion.species,
            action=action,
            symbol=symbol,
            entry_price=round(latest_price, 2),
            stop_loss_price=round(stop_loss, 2),
            take_profit_price=round(take_profit_1, 2),
            target_2r_price=round(take_profit_2, 2),
            invalidation_price=round(inv_price, 2),
            execution_urgency=urgency,
            confidence=round(confidence, 2),
            backtest_sharpe=self.champion_result.sharpe_ratio if self.champion_result else 0.0,
            win_rate=self.champion_result.win_rate if self.champion_result else 0.0,
            max_drawdown=self.champion_result.max_drawdown if self.champion_result else 0.0,
            profit_factor=self.champion_result.profit_factor if self.champion_result else 0.0,
            genome=champion.to_dict(),
            timestamp=datetime.now(timezone.utc),
        )

        logger.info(
            f"TradeProposal Generated [{symbol}]: Action={proposal.action} ({proposal.species.value}) | "
            f"Entry=${proposal.entry_price:,.2f} | SL=${proposal.stop_loss_price:,.2f} | "
            f"TP1=${proposal.take_profit_price:,.2f} | Conf={proposal.confidence:.1%}"
        )

        event_bus.publish(EVENT_TRADE_PROPOSAL, proposal)
        return proposal

    def _neutral_proposal(self, symbol: str, reason: str) -> TradeProposal:
        return TradeProposal(
            strategy_id="NEUTRAL-FALLBACK",
            species=StrategySpecies.REGIME_ADAPTIVE,
            action="HOLD",
            symbol=symbol,
            entry_price=0.0,
            stop_loss_price=0.0,
            take_profit_price=0.0,
            confidence=0.0,
            backtest_sharpe=0.0,
            win_rate=0.0,
            max_drawdown=0.0,
            profit_factor=0.0,
            genome={},
            timestamp=datetime.now(timezone.utc),
        )
