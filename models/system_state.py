"""System Checkpoint & Crash Recovery State Manager for StrategyOne."""

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from loguru import logger

from config.settings import get_settings
from core.types import ActivePosition, BracketOrderGroup, OrderStatus


class SystemStateManager:
    """Manages atomic disk checkpoints and crash-recovery state resumption."""

    def __init__(self, checkpoint_path: Optional[str] = None) -> None:
        settings = get_settings()
        self.checkpoint_path = Path(checkpoint_path or settings.CHECKPOINT_FILE_PATH)
        self.checkpoint_path.parent.mkdir(parents=True, exist_ok=True)

    def save_checkpoint(
        self,
        champion_id: Optional[str],
        champion_genome: Optional[Dict[str, Any]],
        champion_species: Optional[str],
        last_retrain_time: Optional[datetime],
        positions: List[ActivePosition],
        brackets: List[BracketOrderGroup],
        portfolio_cash: float,
        portfolio_hwm: float,
        portfolio_drawdown: float,
        agent_states: Dict[str, str],
        cycles_count: int,
    ) -> bool:
        """Atomically saves full system state snapshot to disk using a swap file."""
        state_data: Dict[str, Any] = {
            "version": "1.0",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "cycles_count": cycles_count,
            "champion": {
                "strategy_id": champion_id,
                "genome": champion_genome,
                "species": champion_species,
                "last_retrain_time": last_retrain_time.isoformat() if last_retrain_time else None,
            },
            "portfolio": {
                "cash": round(portfolio_cash, 2),
                "high_water_mark": round(portfolio_hwm, 2),
                "drawdown_pct": round(portfolio_drawdown, 4),
            },
            "positions": [pos.to_dict() for pos in positions if pos.quantity > 0],
            "brackets": [brk.to_dict() for brk in brackets if brk.parent_status != OrderStatus.REJECTED],
            "agent_states": agent_states,
        }

        temp_path = self.checkpoint_path.with_suffix(".tmp")
        try:
            with open(temp_path, "w", encoding="utf-8") as f:
                json.dump(state_data, f, indent=2)
                f.flush()
                os.fsync(f.fileno())

            # Atomic swap
            temp_path.replace(self.checkpoint_path)
            logger.debug(f"SystemStateManager: Checkpoint persisted to {self.checkpoint_path}")
            return True
        except Exception as e:
            logger.error(f"SystemStateManager: Failed to persist checkpoint: {e}")
            if temp_path.exists():
                try:
                    temp_path.unlink()
                except Exception:
                    pass
            return False

    def load_checkpoint(self) -> Optional[Dict[str, Any]]:
        """Loads and validates the latest checkpoint from disk."""
        if not self.checkpoint_path.exists():
            logger.info("SystemStateManager: No existing checkpoint found. Cold start.")
            return None

        try:
            with open(self.checkpoint_path, "r", encoding="utf-8") as f:
                state_data = json.load(f)

            logger.info(
                f"SystemStateManager: Checkpoint loaded successfully from {self.checkpoint_path} "
                f"(Timestamp: {state_data.get('timestamp')}, Cycles: {state_data.get('cycles_count')})"
            )
            return state_data
        except Exception as e:
            logger.error(f"SystemStateManager: Failed to read checkpoint file: {e}")
            return None

    def restore_positions(
        self,
        checkpoint: Dict[str, Any],
        bracket_manager: Any,
    ) -> int:
        """Reconstructs ActivePosition and BracketOrderGroup instances into the bracket manager."""
        raw_positions = checkpoint.get("positions", [])
        raw_brackets = checkpoint.get("brackets", [])
        restored_count = 0

        # Restore positions
        for r_pos in raw_positions:
            try:
                pos = ActivePosition(
                    position_id=r_pos["position_id"],
                    strategy_id=r_pos.get("strategy_id", "strat-recovered"),
                    symbol=r_pos["symbol"],
                    side=r_pos["side"],
                    entry_price=float(r_pos["entry_price"]),
                    quantity=float(r_pos["quantity"]),
                    notional_usd=float(r_pos["notional_usd"]),
                    current_mark_price=float(r_pos.get("current_mark_price", r_pos["entry_price"])),
                    unrealized_pnl_usd=float(r_pos.get("unrealized_pnl_usd", 0.0)),
                    unrealized_pnl_pct=float(r_pos.get("unrealized_pnl_pct", 0.0)),
                    stop_loss_price=float(r_pos["stop_loss_price"]),
                    take_profit_price_1=float(r_pos["take_profit_price_1"]),
                    take_profit_price_2=float(r_pos["take_profit_price_2"]),
                    parent_order_id=r_pos["parent_order_id"],
                    stop_order_id=r_pos.get("stop_order_id"),
                    tp1_order_id=r_pos.get("tp1_order_id"),
                    tp2_order_id=r_pos.get("tp2_order_id"),
                    is_scale_out_executed=bool(r_pos.get("is_scale_out_executed", False)),
                    is_breakeven_active=bool(r_pos.get("is_breakeven_active", False)),
                )
                bracket_manager.positions[pos.position_id] = pos
                restored_count += 1
            except Exception as e:
                logger.error(f"SystemStateManager: Error restoring position {r_pos}: {e}")

        # Restore brackets
        for r_brk in raw_brackets:
            try:
                brk = BracketOrderGroup(
                    bracket_id=r_brk["bracket_id"],
                    intent_id=r_brk["intent_id"],
                    symbol=r_brk["symbol"],
                    parent_order_id=r_brk["parent_order_id"],
                    parent_status=OrderStatus(r_brk["parent_status"]),
                    stop_order_id=r_brk.get("stop_order_id"),
                    stop_status=OrderStatus(r_brk["stop_status"]) if r_brk.get("stop_status") else None,
                    tp1_order_id=r_brk.get("tp1_order_id"),
                    tp1_status=OrderStatus(r_brk["tp1_status"]) if r_brk.get("tp1_status") else None,
                    tp2_order_id=r_brk.get("tp2_order_id"),
                    tp2_status=OrderStatus(r_brk["tp2_status"]) if r_brk.get("tp2_status") else None,
                    is_oco_active=bool(r_brk.get("is_oco_active", False)),
                )
                bracket_manager.brackets[brk.bracket_id] = brk
            except Exception as e:
                logger.error(f"SystemStateManager: Error restoring bracket {r_brk}: {e}")

        logger.info(f"SystemStateManager: Restored {restored_count} active position(s) and {len(bracket_manager.brackets)} bracket(s).")
        return restored_count
