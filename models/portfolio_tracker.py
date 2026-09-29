"""Institutional Portfolio Tracker and Equity Drawdown Engine.

Maintains continuous Mark-to-Market (MtM) equity, High Water Mark (HWM),
multi-horizon calendar loss baselines (Daily UTC, Weekly Monday UTC, Monthly),
consecutive loss cooling-off latches, and atomic disk persistence.
"""

import json
import os
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import pandas as pd
from loguru import logger

from core.types import RiskLevel


class PortfolioTracker:
    """Tracks portfolio equity, peak-to-trough drawdowns, and loss limits with atomic persistence."""

    def __init__(
        self,
        initial_equity: float = 10000.0,
        daily_loss_limit_pct: float = 0.03,     # 3.0% daily cap
        weekly_loss_limit_pct: float = 0.07,    # 7.0% weekly cap
        monthly_loss_limit_pct: float = 0.15,   # 15.0% monthly cap
        max_consecutive_losses: int = 4,        # 4 consecutive losses triggers cooldown
        cooldown_duration_hours: float = 2.0,   # 2 hours cooling off
        state_file_path: Optional[str] = "data/portfolio_state.json",
        is_backtest: bool = False,
    ) -> None:
        self.is_backtest = is_backtest
        self.daily_loss_limit_pct = daily_loss_limit_pct
        self.weekly_loss_limit_pct = weekly_loss_limit_pct
        self.monthly_loss_limit_pct = monthly_loss_limit_pct
        self.max_consecutive_losses = max_consecutive_losses
        self.cooldown_duration = timedelta(hours=cooldown_duration_hours)
        self.state_file_path = Path(state_file_path) if state_file_path else None

        # Baseline state
        self.initial_equity = float(initial_equity)
        self.current_cash = float(initial_equity)
        self.unrealized_pnl = 0.0
        self.high_water_mark = float(initial_equity)
        self.current_exposure_usd = 0.0

        # Multi-horizon baseline trackers
        now = datetime.now(timezone.utc)
        self.daily_start_equity = float(initial_equity)
        self.daily_reset_date = now.strftime("%Y-%m-%d")
        self.weekly_start_equity = float(initial_equity)
        self.weekly_reset_key = f"{now.isocalendar().year}-W{now.isocalendar().week:02d}"
        self.monthly_start_equity = float(initial_equity)
        self.monthly_reset_key = now.strftime("%Y-%m")

        # Circuit breaker & cooldown state
        self.consecutive_losses = 0
        self.cooldown_until: Optional[datetime] = None
        self.consecutive_recovery_wins = 0
        self.recovery_entered_at: Optional[datetime] = None
        self.trade_history: List[Dict[str, Any]] = []
        self.open_positions: List[Dict[str, Any]] = []

        # Attempt to load persisted state if exists
        if self.state_file_path:
            self.load_state()

    @property
    def mtm_equity(self) -> float:
        """Mark-to-market total portfolio equity (cash + open unrealized PnL)."""
        return max(0.0, self.current_cash + self.unrealized_pnl)

    @property
    def drawdown_pct(self) -> float:
        """Current peak-to-trough drawdown fraction relative to High Water Mark."""
        if self.high_water_mark <= 0.0:
            return 0.0
        dd = (self.high_water_mark - self.mtm_equity) / self.high_water_mark
        return float(max(0.0, dd))

    @property
    def current_exposure_pct(self) -> float:
        """Current gross portfolio exposure as a fraction of MtM equity."""
        equity = self.mtm_equity
        if equity <= 0.0:
            return 0.0
        return float(min(1.0, max(0.0, self.current_exposure_usd / equity)))

    @property
    def daily_loss_pct(self) -> float:
        """Loss fraction relative to starting daily equity at 00:00 UTC."""
        self._check_calendar_resets(now=getattr(self, "current_time", None))
        if self.daily_start_equity <= 0.0:
            return 0.0
        loss = (self.daily_start_equity - self.mtm_equity) / self.daily_start_equity
        return float(max(0.0, loss))

    @property
    def weekly_loss_pct(self) -> float:
        """Loss fraction relative to starting weekly equity at Monday 00:00 UTC."""
        self._check_calendar_resets(now=getattr(self, "current_time", None))
        if self.weekly_start_equity <= 0.0:
            return 0.0
        loss = (self.weekly_start_equity - self.mtm_equity) / self.weekly_start_equity
        return float(max(0.0, loss))

    @property
    def is_cooldown_active(self) -> bool:
        """True if the system is currently in a consecutive-loss cooldown window."""
        if self.cooldown_until is None:
            return False
        current_now = getattr(self, "current_time", None) or datetime.now(timezone.utc)
        return current_now < self.cooldown_until

    def update_calendar_time(self, current_time: Any) -> None:
        """Updates internal clock and executes calendar resets for historical simulations."""
        if current_time is None:
            return
        ts = pd.to_datetime(current_time)
        if hasattr(ts, "to_pydatetime"):
            py_ts = ts.to_pydatetime()
        else:
            py_ts = ts
        if py_ts.tzinfo is None:
            py_ts = py_ts.replace(tzinfo=timezone.utc)
        self.current_time = py_ts
        self._check_calendar_resets(now=py_ts)

        # Auto-reset consecutive loss streak when cooldown expires
        if self.cooldown_until is not None and py_ts >= self.cooldown_until:
            logger.info(
                f"Consecutive loss cooldown expired at {py_ts.isoformat()}. "
                f"Resetting consecutive losses from {self.consecutive_losses} to 0."
            )
            self.consecutive_losses = 0
            self.cooldown_until = None

    def _check_calendar_resets(self, now: Optional[datetime] = None) -> None:
        """Checks and executes daily (UTC 00:00) and weekly (Mon UTC 00:00) equity resets."""
        current_time = now or getattr(self, "current_time", None) or datetime.now(timezone.utc)
        current_day_str = current_time.strftime("%Y-%m-%d")
        current_week_str = f"{current_time.isocalendar().year}-W{current_time.isocalendar().week:02d}"
        current_month_str = current_time.strftime("%Y-%m")

        # First initialization if empty
        if not getattr(self, "daily_reset_date", None):
            self.daily_start_equity = self.mtm_equity
            self.daily_reset_date = current_day_str
            self.weekly_start_equity = self.mtm_equity
            self.weekly_reset_key = current_week_str
            self.monthly_start_equity = self.mtm_equity
            self.monthly_reset_key = current_month_str
            return

        # Daily reset at UTC midnight
        if current_day_str != self.daily_reset_date:
            logger.info(
                f"Resetting daily equity baseline. Previous: ${self.daily_start_equity:.2f} -> "
                f"New: ${self.mtm_equity:.2f} (Date: {current_day_str})"
            )
            self.daily_start_equity = self.mtm_equity
            self.daily_reset_date = current_day_str

        # Weekly reset at Monday UTC
        if current_week_str != self.weekly_reset_key:
            logger.info(
                f"Resetting weekly equity baseline. Previous: ${self.weekly_start_equity:.2f} -> "
                f"New: ${self.mtm_equity:.2f} (Week: {current_week_str})"
            )
            self.weekly_start_equity = self.mtm_equity
            self.weekly_reset_key = current_week_str

        # Monthly reset
        if current_month_str != self.monthly_reset_key:
            self.monthly_start_equity = self.mtm_equity
            self.monthly_reset_key = current_month_str

    def update_unrealized_pnl(self, unrealized_pnl: float, open_exposure_usd: float = 0.0) -> None:
        """Updates open position unrealized PnL and recalculates High Water Mark."""
        self._check_calendar_resets()
        self.unrealized_pnl = float(unrealized_pnl)
        self.current_exposure_usd = float(max(0.0, open_exposure_usd))

        # Check for new High Water Mark
        current_eq = self.mtm_equity
        if current_eq > self.high_water_mark:
            self.high_water_mark = current_eq

    def record_trade_result(
        self,
        net_pnl: float,
        timestamp: Optional[datetime] = None,
        notes: str = "",
    ) -> None:
        """Records a closed trade result, updates cash balance, HWM, and consecutive loss state."""
        trade_time = timestamp or datetime.now(timezone.utc)
        self._check_calendar_resets(trade_time)

        self.current_cash += net_pnl
        # High Water Mark update
        if self.mtm_equity > self.high_water_mark:
            self.high_water_mark = self.mtm_equity

        # Consecutive loss logic (any trade with net PnL <= 0 is a loss)
        if net_pnl <= 0.0:
            self.consecutive_losses += 1
            self.consecutive_recovery_wins = 0
            if self.consecutive_losses >= self.max_consecutive_losses:
                self.cooldown_until = trade_time + self.cooldown_duration
                logger.warning(
                    f"Consecutive loss limit reached ({self.consecutive_losses} losses). "
                    f"Cooldown engaged until {self.cooldown_until.isoformat()}"
                )
        else:
            self.consecutive_losses = 0
            self.consecutive_recovery_wins += 1

        self.trade_history.append({
            "timestamp": trade_time.isoformat(),
            "net_pnl": round(net_pnl, 2),
            "resulting_cash": round(self.current_cash, 2),
            "high_water_mark": round(self.high_water_mark, 2),
            "drawdown_pct": round(self.drawdown_pct, 4),
            "consecutive_losses": self.consecutive_losses,
            "notes": notes,
        })

        self.save_state()

    def get_circuit_breaker_status(self) -> Tuple[bool, Optional[str]]:
        """Evaluates whether any calendar loss limit, cooldown, or critical drawdown is breached."""
        self._check_calendar_resets()

        # 1. Critical Drawdown check (>= 10%)
        if self.drawdown_pct >= 0.10:
            return True, f"CRITICAL_DRAWDOWN_LIMIT ({self.drawdown_pct * 100:.2f}% >= 10.0%)"

        # 2. Daily Loss Limit check (>= 3%)
        if self.daily_loss_pct >= self.daily_loss_limit_pct:
            return True, f"DAILY_LOSS_LIMIT_BREACHED ({self.daily_loss_pct * 100:.2f}% >= {self.daily_loss_limit_pct * 100:.1f}%)"

        # 3. Weekly Loss Limit check (>= 7%)
        if self.weekly_loss_pct >= self.weekly_loss_limit_pct:
            return True, f"WEEKLY_LOSS_LIMIT_BREACHED ({self.weekly_loss_pct * 100:.2f}% >= {self.weekly_loss_limit_pct * 100:.1f}%)"

        # 4. Consecutive Loss Cooldown check
        if self.is_cooldown_active and self.cooldown_until is not None:
            now_dt = getattr(self, "current_time", None) or datetime.now(timezone.utc)
            time_left = max(0.0, (self.cooldown_until - now_dt).total_seconds() / 60.0)
            return True, f"CONSECUTIVE_LOSS_COOLDOWN ({time_left:.1f} min remaining)"

        return False, None

    def get_open_positions(self) -> List[Dict[str, Any]]:
        """Returns currently tracked open positions."""
        return self.open_positions

    def update_open_positions(self, positions: List[Dict[str, Any]]) -> None:
        """Updates the list of active open positions."""
        self.open_positions = list(positions)

    def save_state(self) -> None:
        """Atomically saves portfolio state to disk via temporary file rename."""
        if not self.state_file_path:
            return

        state = {
            "initial_equity": self.initial_equity,
            "current_cash": self.current_cash,
            "unrealized_pnl": self.unrealized_pnl,
            "high_water_mark": self.high_water_mark,
            "current_exposure_usd": self.current_exposure_usd,
            "daily_start_equity": self.daily_start_equity,
            "daily_reset_date": self.daily_reset_date,
            "weekly_start_equity": self.weekly_start_equity,
            "weekly_reset_key": self.weekly_reset_key,
            "monthly_start_equity": self.monthly_start_equity,
            "monthly_reset_key": self.monthly_reset_key,
            "consecutive_losses": self.consecutive_losses,
            "consecutive_recovery_wins": self.consecutive_recovery_wins,
            "cooldown_until": self.cooldown_until.isoformat() if self.cooldown_until else None,
            "recovery_entered_at": self.recovery_entered_at.isoformat() if self.recovery_entered_at else None,
            "open_positions": self.open_positions,
            "last_saved": datetime.now(timezone.utc).isoformat(),
        }

        try:
            self.state_file_path.parent.mkdir(parents=True, exist_ok=True)
            # Atomic write pattern
            dir_name = self.state_file_path.parent
            with tempfile.NamedTemporaryFile("w", dir=dir_name, delete=False, encoding="utf-8") as tf:
                json.dump(state, tf, indent=2)
                temp_path = tf.name

            # Atomic replace
            os.replace(temp_path, self.state_file_path)
            logger.debug(f"Portfolio state persisted successfully to {self.state_file_path}")
        except Exception as e:
            logger.error(f"Failed to persist portfolio state: {e}")

    def load_state(self) -> bool:
        """Loads persisted state from disk if present."""
        if not self.state_file_path or not self.state_file_path.exists():
            return False

        try:
            with open(self.state_file_path, "r", encoding="utf-8") as f:
                state = json.load(f)

            self.initial_equity = float(state.get("initial_equity", self.initial_equity))
            self.current_cash = float(state.get("current_cash", self.current_cash))
            self.unrealized_pnl = float(state.get("unrealized_pnl", 0.0))
            self.high_water_mark = float(state.get("high_water_mark", self.high_water_mark))
            self.current_exposure_usd = float(state.get("current_exposure_usd", 0.0))
            self.daily_start_equity = float(state.get("daily_start_equity", self.daily_start_equity))
            self.daily_reset_date = str(state.get("daily_reset_date", self.daily_reset_date))
            self.weekly_start_equity = float(state.get("weekly_start_equity", self.weekly_start_equity))
            self.weekly_reset_key = str(state.get("weekly_reset_key", self.weekly_reset_key))
            self.monthly_start_equity = float(state.get("monthly_start_equity", self.monthly_start_equity))
            self.monthly_reset_key = str(state.get("monthly_reset_key", self.monthly_reset_key))
            self.consecutive_losses = int(state.get("consecutive_losses", 0))
            self.consecutive_recovery_wins = int(state.get("consecutive_recovery_wins", 0))
            self.open_positions = list(state.get("open_positions", []))

            cd_str = state.get("cooldown_until")
            if cd_str:
                self.cooldown_until = datetime.fromisoformat(cd_str)
            else:
                self.cooldown_until = None

            rec_str = state.get("recovery_entered_at")
            if rec_str:
                self.recovery_entered_at = datetime.fromisoformat(rec_str)
            else:
                self.recovery_entered_at = None

            # Re-check calendar resets against current timestamp
            self._check_calendar_resets()
            logger.info(
                f"Portfolio state reloaded: Cash=${self.current_cash:.2f}, HWM=${self.high_water_mark:.2f}, "
                f"DD={self.drawdown_pct*100:.2f}%"
            )
            return True
        except Exception as e:
            logger.warning(f"Failed to load portfolio state from {self.state_file_path}: {e}")
            return False
