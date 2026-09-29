"""Unit tests for the StrategyOne Streamlit Dashboard components (Sprint 11)."""

import json
from pathlib import Path
import pytest

from dashboard.state_reader import DashboardStateReader


def test_dashboard_state_reader_defaults(tmp_path: Path):
    """Verifies that DashboardStateReader returns clean defaults when files are absent."""
    non_existent_cp = tmp_path / "checkpoint.json"
    non_existent_port = tmp_path / "portfolio.json"

    reader = DashboardStateReader(
        checkpoint_path=str(non_existent_cp),
        portfolio_state_path=str(non_existent_port),
    )
    snapshot = reader.get_system_snapshot()

    assert "orchestrator" in snapshot
    assert "portfolio" in snapshot
    assert "positions" in snapshot
    assert "brackets" in snapshot
    assert snapshot["orchestrator"]["cycle_count"] == 0
    assert snapshot["portfolio"]["current_cash"] == 10000.0


def test_dashboard_state_reader_with_data(tmp_path: Path):
    """Verifies that DashboardStateReader properly normalizes populated files."""
    cp_file = tmp_path / "test_cp.json"
    port_file = tmp_path / "test_port.json"

    cp_data = {
        "cycles_count": 42,
        "timestamp": "2026-09-25T12:00:00+00:00",
        "agent_states": {"data_quality": "HEALTHY", "risk_tier": "GREEN"},
        "champion": {"strategy_id": "MOM-001", "species": "MOMENTUM_TREND"},
        "positions": [{"position_id": "pos-1", "symbol": "BTC/USDT", "side": "LONG", "quantity": 0.05}],
        "brackets": [{"bracket_id": "brk-1", "parent_status": "FILLED"}],
    }
    port_data = {
        "initial_equity": 10000.0,
        "current_cash": 10250.0,
        "high_water_mark": 10300.0,
        "drawdown_pct": 0.0048,
        "realized_pnl_cumulative": 250.0,
    }

    with open(cp_file, "w", encoding="utf-8") as f:
        json.dump(cp_data, f)
    with open(port_file, "w", encoding="utf-8") as f:
        json.dump(port_data, f)

    reader = DashboardStateReader(
        checkpoint_path=str(cp_file),
        portfolio_state_path=str(port_file),
    )
    snapshot = reader.get_system_snapshot()

    assert snapshot["orchestrator"]["cycle_count"] == 42
    assert snapshot["orchestrator"]["champion"]["strategy_id"] == "MOM-001"
    assert snapshot["portfolio"]["current_cash"] == 10250.0
    assert len(snapshot["positions"]) == 1
    assert snapshot["positions"][0]["symbol"] == "BTC/USDT"
    assert len(snapshot["brackets"]) == 1
