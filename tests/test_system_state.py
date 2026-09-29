"""Unit tests for SystemStateManager and checkpoint recovery (Sprint 10)."""

from datetime import datetime, timezone
import pytest
from core.types import ActivePosition, BracketOrderGroup, OrderStatus
from engine.bracket_manager import BracketOrderManager
from engine.paper_exchange import PaperExchange
from models.system_state import SystemStateManager


@pytest.fixture
def state_manager(tmp_path):
    checkpoint_file = str(tmp_path / "test_checkpoint.json")
    return SystemStateManager(checkpoint_path=checkpoint_file)


@pytest.fixture
def sample_position():
    return ActivePosition(
        position_id="pos-test-99",
        strategy_id="strat-m1",
        symbol="BTC/USDT",
        side="LONG",
        entry_price=64000.0,
        quantity=0.05,
        notional_usd=3200.0,
        current_mark_price=64500.0,
        unrealized_pnl_usd=25.0,
        unrealized_pnl_pct=0.0078,
        stop_loss_price=62500.0,
        take_profit_price_1=66000.0,
        take_profit_price_2=68000.0,
        parent_order_id="sim-entry-99",
        stop_order_id="sim-sl-99",
        tp1_order_id="sim-tp1-99",
        tp2_order_id="sim-tp2-99",
    )


@pytest.fixture
def sample_bracket():
    return BracketOrderGroup(
        bracket_id="brk-test-99",
        intent_id="intent-99",
        symbol="BTC/USDT",
        parent_order_id="sim-entry-99",
        parent_status=OrderStatus.FILLED,
        stop_order_id="sim-sl-99",
        stop_status=OrderStatus.OPEN,
        tp1_order_id="sim-tp1-99",
        tp1_status=OrderStatus.OPEN,
        tp2_order_id="sim-tp2-99",
        tp2_status=OrderStatus.OPEN,
        is_oco_active=True,
    )


def test_save_and_load_checkpoint(state_manager, sample_position, sample_bracket):
    success = state_manager.save_checkpoint(
        champion_id="MOM-G1-champ",
        champion_genome={"ema_fast": 20, "ema_slow": 50},
        champion_species="MOMENTUM_TREND",
        last_retrain_time=datetime(2026, 9, 25, 10, 0, 0, tzinfo=timezone.utc),
        positions=[sample_position],
        brackets=[sample_bracket],
        portfolio_cash=10500.0,
        portfolio_hwm=10600.0,
        portfolio_drawdown=0.0094,
        agent_states={"data_quality": "HEALTHY", "risk": "GREEN"},
        cycles_count=12,
    )
    assert success is True

    # Load checkpoint
    loaded = state_manager.load_checkpoint()
    assert loaded is not None
    assert loaded["cycles_count"] == 12
    assert loaded["champion"]["strategy_id"] == "MOM-G1-champ"
    assert loaded["portfolio"]["cash"] == 10500.0
    assert len(loaded["positions"]) == 1
    assert loaded["positions"][0]["position_id"] == "pos-test-99"


def test_restore_positions_into_bracket_manager(state_manager, sample_position, sample_bracket):
    state_manager.save_checkpoint(
        champion_id="MOM-G1-champ",
        champion_genome={},
        champion_species="MOMENTUM_TREND",
        last_retrain_time=None,
        positions=[sample_position],
        brackets=[sample_bracket],
        portfolio_cash=10000.0,
        portfolio_hwm=10000.0,
        portfolio_drawdown=0.0,
        agent_states={},
        cycles_count=5,
    )

    loaded = state_manager.load_checkpoint()
    ex = PaperExchange()
    mgr = BracketOrderManager(ex)

    restored = state_manager.restore_positions(loaded, mgr)
    assert restored == 1
    assert "pos-test-99" in mgr.positions
    restored_pos = mgr.positions["pos-test-99"]
    assert restored_pos.quantity == 0.05
    assert restored_pos.entry_price == 64000.0

    assert "brk-test-99" in mgr.brackets
    assert mgr.brackets["brk-test-99"].is_oco_active is True
