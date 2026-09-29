"""Sprint 8 End-to-End Verification Script: 8-Agent Autonomous Pipeline & 3-Layer Defense."""

import asyncio
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import numpy as np
import pandas as pd
from agents.data_quality_agent import DataQualityAgent
from agents.decider_agent import TradeDeciderAgent
from agents.market_agent import MarketIntelligenceAgent
from agents.money_agent import MoneyManagementAgent
from agents.risk_agent import RiskManagementAgent
from agents.strategy_evolution_agent import StrategyEvolutionAgent
from agents.technical_agent import TechnicalAgent
from agents.volatility_agent import VolatilityRegimeAgent
from core.events import (
    EVENT_MONEY_DECISION,
    EVENT_ORDER_INTENT,
    EVENT_RISK_ASSESSMENT,
    EVENT_TRADE_DECISION,
    EVENT_TRADE_PROPOSAL,
    event_bus,
)
from models.portfolio_tracker import PortfolioTracker


def generate_market(periods_15m: int = 1200, trend: float = 0.0002) -> dict[str, pd.DataFrame]:
    """Generates synthetic 15m BTC candles and resamples higher timeframes for 100% cross-TF consistency."""
    np.random.seed(42)
    now = datetime.now(timezone.utc)
    base_time = now - timedelta(minutes=periods_15m * 15)

    price = 65000.0
    records = []
    for i in range(periods_15m):
        ts = base_time + timedelta(minutes=i * 15)
        o = price
        c = price * (1.0 + trend + np.random.normal(0, 0.0015))
        h = max(o, c) * (1.0 + abs(np.random.normal(0, 0.001)))
        l = min(o, c) * (1.0 - abs(np.random.normal(0, 0.001)))
        v = 250.0 + abs(np.random.normal(0, 60.0))
        records.append({"timestamp": ts, "open": o, "high": h, "low": l, "close": c, "volume": v})
        price = c

    df_15m = pd.DataFrame(records)
    df_15m["timestamp"] = pd.to_datetime(df_15m["timestamp"])
    df_indexed = df_15m.set_index("timestamp")

    dataset = {"15m": df_15m}
    for tf, rule in [("1h", "1h"), ("4h", "4h"), ("1d", "1D")]:
        df_tf = df_indexed.resample(rule).agg({
            "open": "first",
            "high": "max",
            "low": "min",
            "close": "last",
            "volume": "sum",
        }).dropna().reset_index()
        dataset[tf] = df_tf

    return dataset


async def main():
    print("=" * 80)
    print("🏛️  STRATEGYONE - SPRINT 8 8-AGENT AUTONOMOUS GOVERNANCE VERIFICATION")
    print("=" * 80)

    # Event tracking
    order_intents = []
    trade_decisions = []
    event_bus.subscribe(EVENT_ORDER_INTENT, lambda oi: order_intents.append(oi))
    event_bus.subscribe(EVENT_TRADE_DECISION, lambda td: trade_decisions.append(td))

    # [1/8] Agent 1: Data Quality
    print("\n[1/8] Executing Agent 1 (Data Quality Agent)...")
    dq_agent = DataQualityAgent()
    market_data = generate_market(periods_15m=1200, trend=0.0002)
    dq_agent.evaluate_data("BTC/USDT", market_data)
    packet = dq_agent.build_data_packet("BTC/USDT")
    assert packet is not None
    print(f"  ✓ Data Quality Score: {packet.quality.overall_quality:.1%} (Status: {packet.quality.status.value})")

    # [2/8] Agent 2: Technical Analysis
    print("\n[2/8] Executing Agent 2 (Technical Analysis Agent)...")
    tech_agent = TechnicalAgent()
    tech_report = tech_agent.analyze(packet)
    print(f"  ✓ Confluence: {tech_report.confluence_score:+.2f} ({tech_report.bias.value}) | Invalidation: ${tech_report.invalidation_price:,.2f}")

    # [3/8] Agent 3: Market Intelligence
    print("\n[3/8] Executing Agent 3 (Market Intelligence Agent)...")
    market_agent = MarketIntelligenceAgent()
    market_report = await market_agent.analyze_live(packet)
    print(f"  ✓ Funding Z-Score: {market_report.funding_zscore:+.2f} | Quadrant: {market_report.positioning_quadrant.value} | FGI: {market_report.fear_and_greed_index}")

    # [4/8] Agent 4: Volatility & Regime Forecaster
    print("\n[4/8] Executing Agent 4 (Volatility & Regime Forecaster Agent)...")
    vol_agent = VolatilityRegimeAgent()
    vol_report = vol_agent.analyze(packet)
    print(f"  ✓ Regime: {vol_report.regime.value} | 24h Vol Forecast: {vol_report.forecasted_volatility_24h:.1f}% | Sizing Mult: {vol_report.volatility_multiplier:.2f}x")

    # [5/8] Agent 5: Strategy Evolution Agent
    print("\n[5/8] Executing Agent 5 (Strategy Evolution Agent)...")
    strat_agent = StrategyEvolutionAgent(population_size=40, tournament_k=3)
    df_1h = packet.timeframes["1h"]
    champion = strat_agent.train(df_1h, generations=3, regime=vol_report.regime)
    proposal = strat_agent.evaluate_live(packet)
    print(f"  ✓ Champion: {champion.strategy_id} ({champion.species.value}) | Proposal: {proposal.action} @ ${proposal.entry_price:,.2f}")

    # [6/8] Agent 6: Risk Management Agent
    print("\n[6/8] Executing Agent 6 (Risk Management Agent - Institutional Shield)...")
    tracker = PortfolioTracker(initial_equity=10000.0, state_file_path="data/portfolio_s8_test.json")
    risk_agent = RiskManagementAgent(portfolio_tracker=tracker)
    returns_15m = packet.timeframes["15m"]["close"].pct_change().dropna().values
    risk_assessment = risk_agent.audit_trade_proposal(
        proposal=proposal,
        recent_returns=returns_15m,
        market_report=market_report,
        volatility_report=vol_report,
        proposed_position_usd=2000.0,
    )
    print(f"  ✓ Risk Tier: {risk_assessment.risk_level.value} | Approved: {risk_assessment.is_proposal_approved} | Dollar Risk Cap: ${risk_assessment.dollar_risk_cap_usd:.2f}")

    # [7/8] Agent 7: Money Management Agent
    print("\n[7/8] Executing Agent 7 (Money Management Agent - Kelly Sizing)...")
    money_agent = MoneyManagementAgent(reserve_ratio=0.40, kelly_fraction=0.50)
    money_decision = money_agent.evaluate_position_size(
        proposal=proposal,
        risk_assessment=risk_assessment,
        market_report=market_report,
        volatility_report=vol_report,
    )
    print(f"  ✓ Sizing Approved: {money_decision.is_sizing_approved} | Kelly Size: ${money_decision.position_size_usd:,.2f} ({money_decision.position_size_asset:.4f} BTC)")
    print(f"  ✓ Dollar Risk at Stop: ${money_decision.dollar_risk_at_stop:,.2f} ({money_decision.dollar_risk_pct:.2%}) | Fee Ratio: {money_decision.fee_drag_ratio:.1f}x")

    # [8/8] Agent 8: Trade Decider Agent
    print("\n[8/8] Executing Agent 8 (Trade Decider Agent - Boardroom Consensus)...")
    decider_agent = TradeDeciderAgent(consensus_threshold=0.65)
    final_decision, order_intent = decider_agent.evaluate_and_decide(
        proposal=proposal,
        data_report=packet.quality,
        tech_report=tech_report,
        market_report=market_report,
        vol_report=vol_report,
        risk_assessment=risk_assessment,
        money_decision=money_decision,
    )

    print("\n" + "-" * 80)
    print(f"⚖️  BOARDROOM CONSENSUS VOTE SUMMARY:")
    print(f"   • Final Verdict:             {final_decision.decision} (Consensus Score: {final_decision.consensus_score:.1%})")
    print(f"   • Consensus Threshold:       {final_decision.consensus_threshold:.1%}")
    print(f"   • Reasoning:                 {final_decision.decision_reasoning}")
    print(f"   • Approved Position Notional: ${final_decision.approved_position_size_usd:,.2f}")
    print(f"   • Approved Quantity (BTC):   {final_decision.approved_position_size_asset:.6f} BTC")
    print("-" * 80)

    if order_intent:
        print("\n" + "-" * 80)
        print(f"⚡ ACTIONABLE ORDER INTENT DISPATCHED TO EXECUTOR (AGENT #9):")
        print(f"   • Intent ID:         {order_intent.intent_id}")
        print(f"   • Symbol & Side:     {order_intent.side} {order_intent.symbol}")
        print(f"   • Order Type:        {order_intent.order_type} @ ${order_intent.limit_price:,.2f}")
        print(f"   • Quantity:          {order_intent.quantity_asset:.6f} (${order_intent.notional_usd:,.2f})")
        print(f"   • Stop Loss Order:   ${order_intent.stop_loss_price:,.2f}")
        print(f"   • Target 1 (1.5R):   ${order_intent.take_profit_price:,.2f} (50% scale-out)")
        print(f"   • Target 2 (2.5R):   ${order_intent.target_2r_price:,.2f} (Trailing runner)")
        print(f"   • Invalidation:      ${order_intent.invalidation_price:,.2f}")
        print(f"   • Urgency / Leverage:{order_intent.urgency} / {order_intent.leverage:.1f}x")
        print("-" * 80)

    assert len(order_intents) >= 1

    # VETO INVARIANCE TEST: Simulate a Risk Veto
    print("\n  • Testing 3-Layer Defense Veto Invariance (Simulated Drawdown Tier RED):")
    tracker.update_unrealized_pnl(unrealized_pnl=-850.0)  # 8.5% Drawdown
    vetoed_risk = risk_agent.audit_trade_proposal(proposal=proposal, recent_returns=returns_15m)
    vetoed_money = money_agent.evaluate_position_size(proposal=proposal, risk_assessment=vetoed_risk)
    vetoed_decision, vetoed_order = decider_agent.evaluate_and_decide(
        proposal=proposal,
        data_report=packet.quality,
        tech_report=tech_report,
        market_report=market_report,
        vol_report=vol_report,
        risk_assessment=vetoed_risk,
        money_decision=vetoed_money,
    )
    print(f"    ✓ Decision under RED tier: {vetoed_decision.decision} (Vetoes: {vetoed_decision.vetoes_triggered})")
    print(f"    ✓ OrderIntent generated:   {vetoed_order} (Strictly None on veto!)")
    assert vetoed_order is None

    # Clean up test json
    test_p = Path("data/portfolio_s8_test.json")
    if test_p.exists():
        test_p.unlink()

    await market_agent.derivatives_fetcher.close()

    print("\n" + "=" * 80)
    print("🎉 ALL SPRINT 8 MONEY MANAGEMENT & DECIDER ACCEPTANCE CRITERIA PASSING!")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(main())
