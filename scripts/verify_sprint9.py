"""Sprint 9 End-to-End Verification Script: 9-Agent Autonomous Pipeline & Execution Engine."""

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
from agents.executor_agent import TradeExecutionAgent
from agents.market_agent import MarketIntelligenceAgent
from agents.money_agent import MoneyManagementAgent
from agents.risk_agent import RiskManagementAgent
from agents.strategy_evolution_agent import StrategyEvolutionAgent
from agents.technical_agent import TechnicalAgent
from agents.volatility_agent import VolatilityRegimeAgent
from core.events import (
    EVENT_EMERGENCY_FLATTEN,
    EVENT_EXECUTION_REPORT,
    EVENT_ORDER_INTENT,
    EVENT_POSITION_CLOSED,
    EVENT_POSITION_OPENED,
    event_bus,
)
from core.types import ExecutionMode, OrderRole, OrderStatus
from engine.paper_exchange import PaperExchange
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
    print("🏛️  STRATEGYONE - SPRINT 9 9-AGENT AUTONOMOUS GOVERNANCE & EXECUTION VERIFICATION")
    print("=" * 80)

    # Telemetry tracking
    order_intents = []
    execution_reports = []
    positions_opened = []
    positions_closed = []

    event_bus.subscribe(EVENT_ORDER_INTENT, lambda oi: order_intents.append(oi))
    event_bus.subscribe(EVENT_EXECUTION_REPORT, lambda er: execution_reports.append(er))
    event_bus.subscribe(EVENT_POSITION_OPENED, lambda po: positions_opened.append(po))
    event_bus.subscribe(EVENT_POSITION_CLOSED, lambda pc: positions_closed.append(pc))

    # [1/9] Agent 1: Data Quality
    print("\n[1/9] Executing Agent 1 (Data Quality Agent)...")
    dq_agent = DataQualityAgent()
    market_data = generate_market(periods_15m=1200, trend=0.0002)
    dq_agent.evaluate_data("BTC/USDT", market_data)
    packet = dq_agent.build_data_packet("BTC/USDT")
    assert packet is not None
    print(f"  ✓ Data Quality Score: {packet.quality.overall_quality:.1%} (Status: {packet.quality.status.value})")

    # [2/9] Agent 2: Technical Analysis
    print("\n[2/9] Executing Agent 2 (Technical Analysis Agent)...")
    tech_agent = TechnicalAgent()
    tech_report = tech_agent.analyze(packet)
    print(f"  ✓ Confluence: {tech_report.confluence_score:+.2f} ({tech_report.bias.value}) | Invalidation: ${tech_report.invalidation_price:,.2f}")

    # [3/9] Agent 3: Market Intelligence
    print("\n[3/9] Executing Agent 3 (Market Intelligence Agent)...")
    market_agent = MarketIntelligenceAgent()
    market_report = await market_agent.analyze_live(packet)
    print(f"  ✓ Funding Z-Score: {market_report.funding_zscore:+.2f} | Quadrant: {market_report.positioning_quadrant.value} | FGI: {market_report.fear_and_greed_index}")

    # [4/9] Agent 4: Volatility & Regime Forecaster
    print("\n[4/9] Executing Agent 4 (Volatility & Regime Forecaster Agent)...")
    vol_agent = VolatilityRegimeAgent()
    vol_report = vol_agent.analyze(packet)
    print(f"  ✓ Regime: {vol_report.regime.value} | 24h Vol Forecast: {vol_report.forecasted_volatility_24h:.1f}% | Sizing Mult: {vol_report.volatility_multiplier:.2f}x")

    # [5/9] Agent 5: Strategy Evolution Agent
    print("\n[5/9] Executing Agent 5 (Strategy Evolution Agent - GA Training)...")
    strat_agent = StrategyEvolutionAgent(population_size=40, tournament_k=3)
    df_1h = packet.timeframes["1h"]
    champion = strat_agent.train(df_1h, generations=3, regime=vol_report.regime)
    proposal = strat_agent.evaluate_live(packet)
    assert proposal is not None
    print(f"  ✓ Champion: {champion.strategy_id} ({champion.species.value}) | Proposal: {proposal.action} @ ${proposal.entry_price:,.2f}")

    # [6/9] Agent 6: Risk Management Agent (Institutional Shield)
    print("\n[6/9] Executing Agent 6 (Risk Management Agent - 7-Gate Proposal Audit)...")
    tracker = PortfolioTracker(initial_equity=10000.0, state_file_path="data/portfolio_state_sprint9.json")
    risk_agent = RiskManagementAgent(portfolio_tracker=tracker)
    returns_15m = packet.timeframes["15m"]["close"].pct_change().dropna().values
    risk_assessment = risk_agent.audit_trade_proposal(
        proposal=proposal,
        recent_returns=returns_15m,
        market_report=market_report,
        volatility_report=vol_report,
        proposed_position_usd=2000.0,
    )
    print(f"  ✓ Risk Tier: {risk_assessment.risk_level.value} | Approved: {risk_assessment.is_proposal_approved} | Dollar Risk Cap: ${risk_assessment.dollar_risk_cap_usd:,.2f}")

    # [7/9] Agent 7: Money Management Agent (Half-Kelly Sizing)
    print("\n[7/9] Executing Agent 7 (Money Management Agent - Fractional Kelly Sizing)...")
    money_agent = MoneyManagementAgent(reserve_ratio=0.40, kelly_fraction=0.50)
    money_decision = money_agent.evaluate_position_size(
        proposal=proposal,
        risk_assessment=risk_assessment,
        market_report=market_report,
        volatility_report=vol_report,
    )
    print(f"  ✓ Sizing Approved: {money_decision.is_sizing_approved} | Kelly Size: ${money_decision.position_size_usd:,.2f} ({money_decision.position_size_asset:.4f} BTC)")
    print(f"  ✓ Dollar Risk at Stop: ${money_decision.dollar_risk_at_stop:,.2f} ({money_decision.dollar_risk_pct:.2%}) | Fee Ratio: {money_decision.fee_drag_ratio:.1f}x")

    # [8/9] Agent 8: Trade Decider Agent (Boardroom Consensus)
    print("\n[8/9] Executing Agent 8 (Trade Decider Agent - Boardroom Consensus Matrix)...")
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
    assert order_intent is not None
    print(f"  ✓ Consensus Score: {final_decision.consensus_score:.1%} (Verdict: {final_decision.decision})")
    print(f"  ✓ Dispatched Actionable OrderIntent: {order_intent.side} {order_intent.quantity_asset:.6f} {order_intent.symbol} (${order_intent.notional_usd:,.2f})")

    # [9/9] Agent 9: Trade Execution Agent (Execution Engine & Bracket Lifecycle)
    print("\n[9/9] Executing Agent 9 (Trade Execution Agent - Order Routing & Bracket Management)...")
    paper_ex = PaperExchange(initial_balance_usd=10000.0)
    current_entry_price = order_intent.limit_price
    paper_ex.set_current_price("BTC/USDT", current_entry_price)

    executor_agent = TradeExecutionAgent(
        exchange=paper_ex,
        portfolio_tracker=tracker,
        mode=ExecutionMode.PAPER,
    )

    bracket, entry_report = executor_agent.execute_order_intent(order_intent)
    assert bracket.parent_status == OrderStatus.OPEN

    print("  ✓ Parent Entry Order Resting on Order Book:")
    print(f"    • Order ID:         {entry_report.order_id}")
    print(f"    • Type & Side:      {entry_report.order_type} {entry_report.side}")
    print(f"    • Requested Price:  ${entry_report.requested_price:,.2f}")
    print(f"    • Quantity:         {entry_report.requested_qty:.6f} BTC")
    print(f"    • Status:           {entry_report.status.value}")

    # Simulate price action dipping to fill limit entry
    print("\n⚡ [SIMULATION PHASE A] Market Dips to Fill Entry...")
    entry_fills = executor_agent.on_price_update(
        symbol="BTC/USDT",
        current_price=current_entry_price - 50.0,
        low_price=current_entry_price - 50.0,
    )
    assert any(f.role == OrderRole.PARENT_ENTRY for f in entry_fills)
    print(f"  ✓ Parent Entry FILLED at ${current_entry_price:,.2f}!")

    active_pos = list(executor_agent.bracket_manager.positions.values())[0]
    print(f"  ✓ Active Position Inception: {active_pos.side} {active_pos.quantity:.6f} BTC (${active_pos.notional_usd:,.2f})")
    print(f"  ✓ Server-Side Stop Loss Order:     ${active_pos.stop_loss_price:,.2f} (100% position)")
    print(f"  ✓ Tier-1 Take Profit (1.5R) Order:  ${active_pos.take_profit_price_1:,.2f} (50% scale-out)")
    print(f"  ✓ Tier-2 Runner Target (2.5R) Order: ${active_pos.take_profit_price_2:,.2f} (Trailing runner)")

    # Simulate market rally to TP1 (1.5R target)
    tp1_price = order_intent.take_profit_price
    print(f"\n⚡ [SIMULATION PHASE B] Market Rallies to TP1 Target (${tp1_price:,.2f})...")
    tp1_fills = executor_agent.on_price_update(
        symbol="BTC/USDT",
        current_price=tp1_price + 10.0,
        high_price=tp1_price + 10.0,
    )
    assert any(f.role == OrderRole.TAKE_PROFIT_1 for f in tp1_fills)
    print(f"  ✓ TP1 FILLED! Scaled out 50% ({active_pos.quantity:.6f} BTC remaining)")
    print(f"  ✓ Stop Loss Ratcheted to Breakeven: ${active_pos.stop_loss_price:,.2f} (Entry: ${active_pos.entry_price:,.2f})")
    assert active_pos.is_scale_out_executed is True
    assert active_pos.is_breakeven_active is True
    print(f"  ✓ Realized PnL from Scale-Out Recorded in Portfolio: +${tracker.trade_history[-1]['net_pnl']:.2f}")

    # Simulate Emergency Circuit Breaker Trigger
    print("\n⚡ [SIMULATION PHASE C] Emergency Circuit Breaker Event Triggered...")
    flatten_reports = executor_agent.emergency_flatten("BTC/USDT")
    assert any(r.role == OrderRole.EMERGENCY_FLATTEN for r in flatten_reports)
    print(f"  ✓ Active Inventory Liquidated at Market: Remaining Quantity = {active_pos.quantity:.6f} BTC")
    open_orders = paper_ex.fetch_open_orders("BTC/USDT")
    assert len(open_orders) == 0
    print(f"  ✓ Open Order Count on Exchange: {len(open_orders)} (All brackets cancelled cleanly!)")

    # Final telemetry report
    status = executor_agent.get_status()
    print("\n" + "=" * 80)
    print("📊 TRADE EXECUTION AGENT (AGENT #9) TELEMETRY & AUDIT SUMMARY")
    print("=" * 80)
    print(f"  • Execution Mode:             {status['execution_mode']}")
    print(f"  • Total Orders Executed:      {status['total_orders_executed']}")
    print(f"  • Total Turnover Volume:      ${status['total_volume_usd']:,.2f}")
    print(f"  • Total Trading Fees Paid:    ${status['total_fees_paid_usd']:.4f}")
    print(f"  • Active Open Positions:      {status['active_positions_count']}")
    print(f"  • Portfolio Cash Balance:     ${tracker.current_cash:,.2f}")
    print(f"  • Total Closed Trades Logged: {len(tracker.trade_history)}")
    # Graceful shutdown of async network sessions
    await market_agent.close()

    # Clean up test state file
    test_json = Path("data/portfolio_state_sprint9.json")
    if test_json.exists():
        test_json.unlink()

    print("=" * 80)
    print("🎉 ALL 9 AGENTS FULLY INTEGRATED & SPRINT 9 VERIFICATION SUCCESSFUL!")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(main())
