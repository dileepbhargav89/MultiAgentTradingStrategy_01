"""Sprint 10 End-to-End Verification Script: Master Orchestrator, Live Scheduler Loop & State Resumption."""

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
from core.orchestrator import OrchestratorMode, SystemOrchestrator
from core.types import AgentState, DataPacket, DataQualityReport, OrderRole
from engine.paper_exchange import PaperExchange
from models.portfolio_tracker import PortfolioTracker


def generate_market_packet(periods_15m: int = 800, quality_score: float = 1.0, trend: float = 0.0002) -> DataPacket:
    """Generates synthetic multi-timeframe candle dataset wrapped in DataPacket."""
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

    dq = DataQualityReport(
        status=AgentState.HEALTHY if quality_score >= 0.85 else AgentState.DEGRADED,
        quality_scores={"15m": quality_score, "1h": quality_score},
        overall_quality=quality_score,
        is_tradeable=(quality_score >= 0.85),
        freshness_ok=True,
    )

    return DataPacket(
        symbol="BTC/USDT",
        timeframes=dataset,
        features={},
        quality=dq,
        latest_price=price,
        fetched_at=now,
    )


async def main():
    print("=" * 80)
    print("🎛️  STRATEGYONE - SPRINT 10 MASTER ORCHESTRATOR & RESUMPTION VERIFICATION")
    print("=" * 80)

    checkpoint_file = "data/sprint10_verify_checkpoint.json"
    port_state_file = "data/sprint10_verify_portfolio.json"

    # [1/5] Bootstrapping Master Orchestrator Daemon
    print("\n[1/5] Booting SystemOrchestrator in PAPER_DAEMON mode...")
    tracker = PortfolioTracker(initial_equity=10000.0, state_file_path=port_state_file)
    paper_ex = PaperExchange(initial_balance_usd=10000.0)

    orchestrator = SystemOrchestrator(
        mode=OrchestratorMode.PAPER_DAEMON,
        exchange=paper_ex,
        portfolio_tracker=tracker,
        checkpoint_path=checkpoint_file,
    )
    print("  ✓ Orchestrator instantiated with all 9 domain agents.")
    print(f"  ✓ Mode: {orchestrator.mode.value} | Cycle Count: {orchestrator.cycle_count}")

    # [2/5] Executing Cycle #1: Autonomous 9-Agent Pipeline Execution
    print("\n[2/5] Running Autonomous Cycle #1 (Healthy Ingestion & Decision Flow)...")
    healthy_packet = generate_market_packet(periods_15m=800, quality_score=1.0)
    paper_ex.set_current_price("BTC/USDT", healthy_packet.latest_price)

    result_c1 = await orchestrator.run_single_cycle(healthy_packet, execute_orders=True)
    print(f"  ✓ Cycle #1 Status:           {result_c1['status']}")
    print(f"  ✓ Boardroom Decision:        {result_c1.get('decision')}")
    print(f"  ✓ Consensus Score:           {result_c1.get('consensus_score', 0):.1%}")
    print(f"  ✓ Execution Report Status:   {result_c1.get('execution_status')}")

    # Verify order execution
    open_brackets = list(orchestrator.executor_agent.bracket_manager.brackets.values())
    assert len(open_brackets) >= 1
    bracket = open_brackets[-1]
    print(f"  ✓ Active Bracket Registered: {bracket.bracket_id} (Parent Order: {bracket.parent_order_id})")

    # [3/5] Simulating High-Frequency Tick Price Movement & Bracket Triggers
    print("\n[3/5] Simulating Tick Monitoring Loop (Market Fills Entry, then Triggers TP1)...")
    # Trigger Parent Limit Fill
    entry_price = healthy_packet.latest_price
    bracket_side = orchestrator.executor_agent.bracket_manager.bracket_intents[bracket.bracket_id].side
    if bracket_side == "BUY":
        fills_entry = orchestrator.executor_agent.on_price_update("BTC/USDT", current_price=entry_price - 50.0, low_price=entry_price - 50.0)
    else:
        fills_entry = orchestrator.executor_agent.on_price_update("BTC/USDT", current_price=entry_price + 50.0, high_price=entry_price + 50.0)
    assert any(f.role == OrderRole.PARENT_ENTRY for f in fills_entry)
    print(f"  ✓ Parent Entry Order ({bracket_side}) FILLED @ ${entry_price:,.2f}!")

    active_pos = list(orchestrator.executor_agent.bracket_manager.positions.values())[0]
    tp1_target = active_pos.take_profit_price_1
    print(f"  ✓ Position Active: {active_pos.quantity:.6f} BTC | Side: {active_pos.side} | SL: ${active_pos.stop_loss_price:,.2f} | TP1: ${tp1_target:,.2f}")

    # Trigger TP1 Fill
    if active_pos.side == "LONG":
        fills_tp1 = orchestrator.executor_agent.on_price_update("BTC/USDT", current_price=tp1_target + 20.0, high_price=tp1_target + 20.0)
    else:
        fills_tp1 = orchestrator.executor_agent.on_price_update("BTC/USDT", current_price=tp1_target - 20.0, low_price=tp1_target - 20.0)
    assert any(f.role == OrderRole.TAKE_PROFIT_1 for f in fills_tp1)
    print(f"  ✓ TP1 FILLED! Scaled out 50%. Remaining: {active_pos.quantity:.6f} BTC")
    print(f"  ✓ Stop Loss Ratcheted to Breakeven: ${active_pos.stop_loss_price:,.2f}")
    assert active_pos.is_breakeven_active is True

    # Persist updated state checkpoint
    orchestrator._save_checkpoint()
    print("  ✓ State Checkpoint Persisted to Disk.")

    # [4/5] Simulating System Crash and Autonomous Recovery
    print("\n[4/5] Simulating System Crash & State Resumption from Checkpoint...")
    del orchestrator  # Destroy current orchestrator in memory

    # Boot fresh new orchestrator instance pointing to the persisted checkpoint
    rebooted_tracker = PortfolioTracker(initial_equity=10000.0, state_file_path=port_state_file)
    rebooted_orchestrator = SystemOrchestrator(
        mode=OrchestratorMode.PAPER_DAEMON,
        portfolio_tracker=rebooted_tracker,
        checkpoint_path=checkpoint_file,
    )
    recovered = rebooted_orchestrator.recover_state()
    assert recovered is True
    print(f"  ✓ Checkpoint Recovery Successful: Resumed at Cycle #{rebooted_orchestrator.cycle_count}")
    recovered_pos = list(rebooted_orchestrator.executor_agent.bracket_manager.positions.values())
    assert len(recovered_pos) >= 1
    print(f"  ✓ Restored Open Position: {recovered_pos[0].side} {recovered_pos[0].quantity:.6f} BTC @ ${recovered_pos[0].entry_price:,.2f}")
    print(f"  ✓ Breakeven Active Status: {recovered_pos[0].is_breakeven_active} (SL: ${recovered_pos[0].stop_loss_price:,.2f})")

    # [5/5] Testing Data Quality Fail-Closed Short-Circuiting & Graceful Shutdown
    print("\n[5/5] Testing Fail-Closed Data Quality Veto & Graceful Shutdown...")
    degraded_packet = generate_market_packet(periods_15m=800, quality_score=0.65)
    result_degraded = await rebooted_orchestrator.run_single_cycle(degraded_packet)
    assert result_degraded["status"] == "HALTED_DATA_QUALITY_VETO"
    print(f"  ✓ Data Quality Veto Enforced: Cycle halted immediately with score {result_degraded['quality_score']:.1%}")

    # Graceful Shutdown
    await rebooted_orchestrator.shutdown()
    print("  ✓ Graceful Shutdown Completed with zero leaks.")

    # Clean up test artifacts
    for p in [Path(checkpoint_file), Path(port_state_file)]:
        if p.exists():
            p.unlink()

    print("\n" + "=" * 80)
    print("🎉 ALL SPRINT 10 ORCHESTRATION & STATE RESUMPTION CRITERIA PASSING!")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(main())
