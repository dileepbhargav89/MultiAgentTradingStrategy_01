"""State reader and aggregator for the StrategyOne Streamlit Dashboard.

Safely inspects and aggregates live disk checkpoints, portfolio states, and
agent consensus metrics with robust fallback defaults when files are initializing.
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from loguru import logger

from config.settings import settings


class DashboardStateReader:
    """Safely reads persisted state for real-time dashboard rendering."""

    def __init__(
        self,
        checkpoint_path: Optional[str] = None,
        portfolio_state_path: Optional[str] = None,
    ) -> None:
        self.checkpoint_path = Path(checkpoint_path or getattr(settings, "CHECKPOINT_FILE_PATH", "data/system_checkpoint.json"))
        default_port = getattr(settings, "PORTFOLIO_STATE_PATH", "data/cache/portfolio_state.json")
        self.portfolio_path = Path(portfolio_state_path or default_port)

    def get_system_snapshot(self) -> Dict[str, Any]:
        """Loads and consolidates the latest orchestrator and portfolio snapshot."""
        checkpoint_data = self._read_json(self.checkpoint_path)
        portfolio_data = self._read_json(self.portfolio_path)

        # Merge and normalize
        return {
            "orchestrator": {
                "cycle_count": checkpoint_data.get("cycles_count", 0),
                "timestamp": checkpoint_data.get("timestamp", datetime.now(timezone.utc).isoformat()),
                "agent_states": checkpoint_data.get("agent_states", {
                    "data_quality": "HEALTHY",
                    "risk_tier": "GREEN",
                    "execution_agent": "IDLE",
                }),
                "champion": checkpoint_data.get("champion", {
                    "strategy_id": "MOM-DEFAULT",
                    "species": "MOMENTUM_TREND",
                    "last_retrain_time": None,
                }),
            },
            "portfolio": {
                "initial_equity": portfolio_data.get("initial_equity", 10000.0),
                "current_cash": portfolio_data.get("current_cash", 10000.0),
                "high_water_mark": portfolio_data.get("high_water_mark", 10000.0),
                "drawdown_pct": portfolio_data.get("drawdown_pct", 0.0),
                "daily_loss_pct": portfolio_data.get("daily_loss_pct", 0.0),
                "weekly_loss_pct": portfolio_data.get("weekly_loss_pct", 0.0),
                "consecutive_losses": portfolio_data.get("consecutive_losses", 0),
                "is_cooldown_active": portfolio_data.get("is_cooldown_active", False),
                "realized_pnl_cumulative": portfolio_data.get("realized_pnl_cumulative", 0.0),
                "trade_history": portfolio_data.get("trade_history", []),
            },
            "positions": checkpoint_data.get("positions", []),
            "brackets": checkpoint_data.get("brackets", []),
        }

    def _read_json(self, path: Path) -> Dict[str, Any]:
        """Safely parses JSON file with error handling."""
        if not path.exists():
            return {}
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.debug(f"DashboardStateReader: Error reading {path}: {e}")
            return {}
