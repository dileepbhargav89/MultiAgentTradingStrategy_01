"""Unit and integration tests for SystemOrchestrator (Sprint 10)."""

from datetime import datetime, timedelta, timezone
import numpy as np
import pandas as pd
import pytest
from core.orchestrator import OrchestratorMode, SystemOrchestrator
from core.types import AgentState, DataPacket, DataQualityReport
from engine.paper_exchange import PaperExchange
from models.portfolio_tracker import PortfolioTracker


def generate_test_packet(periods_15m: int = 400, quality_score: float = 1.0) -> DataPacket:
    np.random.seed(42)
    now = datetime.now(timezone.utc)
    base_time = now - timedelta(minutes=periods_15m * 15)

    price = 65000.0
    records = []
    for i in range(periods_15m):
        ts = base_time + timedelta(minutes=i * 15)
        o = price
        c = price * (1.0001 + np.random.normal(0, 0.001))
        h = max(o, c) * 1.001
        l = min(o, c) * 0.999
        v = 100.0
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


@pytest.fixture
def orchestrator(tmp_path):
    checkpoint_file = str(tmp_path / "orch_checkpoint.json")
    tracker = PortfolioTracker(initial_equity=10000.0, state_file_path=str(tmp_path / "test_port.json"))
    paper_ex = PaperExchange(initial_balance_usd=10000.0)
    paper_ex.set_current_price("BTC/USDT", 65000.0)

    orch = SystemOrchestrator(
        mode=OrchestratorMode.PAPER_DAEMON,
        exchange=paper_ex,
        portfolio_tracker=tracker,
        checkpoint_path=checkpoint_file,
    )
    return orch


@pytest.mark.asyncio
async def test_orchestrator_initialization(orchestrator):
    assert orchestrator.mode == OrchestratorMode.PAPER_DAEMON
    assert orchestrator.cycle_count == 0
    assert orchestrator.dq_agent is not None
    assert orchestrator.executor_agent is not None


@pytest.mark.asyncio
async def test_run_single_cycle_end_to_end(orchestrator):
    packet = generate_test_packet(periods_15m=400, quality_score=1.0)
    result = await orchestrator.run_single_cycle(packet, execute_orders=True)

    assert result["cycle"] == 1
    assert result["status"] in ("COMPLETED", "HOLD")
    assert orchestrator.cycle_count == 1

    # Checkpoint must have been persisted
    loaded = orchestrator.state_manager.load_checkpoint()
    assert loaded is not None
    assert loaded["cycles_count"] == 1

    # Cleanup session
    await orchestrator.shutdown()


@pytest.mark.asyncio
async def test_data_quality_veto_short_circuits_cycle(orchestrator):
    # Packet with sub-threshold quality score (0.70 < 0.85 minimum)
    bad_packet = generate_test_packet(periods_15m=400, quality_score=0.70)
    result = await orchestrator.run_single_cycle(bad_packet, execute_orders=True)

    assert result["status"] == "HALTED_DATA_QUALITY_VETO"
    # No order should have been executed
    assert orchestrator.executor_agent.total_orders_executed == 0

    await orchestrator.shutdown()


@pytest.mark.asyncio
async def test_recovery_from_checkpoint(orchestrator, tmp_path):
    # Run a cycle and save state
    packet = generate_test_packet(periods_15m=400, quality_score=1.0)
    await orchestrator.run_single_cycle(packet, execute_orders=False)
    assert orchestrator.cycle_count == 1

    # Re-instantiate a new orchestrator pointing to the same checkpoint
    checkpoint_file = orchestrator.state_manager.checkpoint_path
    new_tracker = PortfolioTracker(initial_equity=10000.0, state_file_path=str(tmp_path / "test_port2.json"))
    new_orch = SystemOrchestrator(
        mode=OrchestratorMode.PAPER_DAEMON,
        portfolio_tracker=new_tracker,
        checkpoint_path=str(checkpoint_file),
    )

    recovered = new_orch.recover_state()
    assert recovered is True
    assert new_orch.cycle_count == 1

    await orchestrator.shutdown()
    await new_orch.shutdown()
