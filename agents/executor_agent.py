"""Trade Execution Agent (Agent #9) for StrategyOne.

Consumes OrderIntent from Trade Decider Agent (Agent #8), executes orders via Live CCXT
or High-Fidelity PaperExchange, manages bracket order lifecycle (SL, 1.5R, 2.5R),
monitors fills/slippage, responds to emergency flatten events, and reconciles portfolio state.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from loguru import logger

from config.settings import get_settings
from core.events import (
    EVENT_CIRCUIT_BREAKER_TRIPPED,
    EVENT_EMERGENCY_FLATTEN,
    EVENT_EXECUTION_REPORT,
    EVENT_ORDER_FILLED,
    EVENT_ORDER_INTENT,
    EVENT_POSITION_CLOSED,
    EVENT_POSITION_OPENED,
    event_bus,
)
from core.types import (
    ActivePosition,
    AgentState,
    BracketOrderGroup,
    ExecutionMode,
    ExecutionReport,
    OrderIntent,
    OrderRole,
    OrderStatus,
)
from engine.bracket_manager import BracketOrderManager
from engine.exchange_client import BinanceExchangeClient
from engine.paper_exchange import PaperExchange
from models.portfolio_tracker import PortfolioTracker


class TradeExecutionAgent:
    """Agent #9: Production-grade order execution coordinator and bracket lifecycle manager."""

    def __init__(
        self,
        exchange: Optional[Any] = None,
        portfolio_tracker: Optional[PortfolioTracker] = None,
        mode: Optional[ExecutionMode] = None,
    ) -> None:
        settings = get_settings()
        self.state = AgentState.HEALTHY

        # Determine execution mode
        if mode is not None:
            self.mode = mode
        else:
            configured_mode = settings.EXECUTION_MODE.upper()
            if configured_mode == "LIVE_PRODUCTION":
                self.mode = ExecutionMode.LIVE_PRODUCTION
            elif configured_mode == "LIVE_TESTNET":
                self.mode = ExecutionMode.LIVE_TESTNET
            else:
                self.mode = ExecutionMode.PAPER

        # Initialize exchange instance
        if exchange is not None:
            self.exchange = exchange
        else:
            if self.mode == ExecutionMode.PAPER:
                self.exchange = PaperExchange()
                logger.info("TradeExecutionAgent: Initialized with High-Fidelity PaperExchange.")
            else:
                self.exchange = BinanceExchangeClient(testnet=(self.mode == ExecutionMode.LIVE_TESTNET))
                logger.info(f"TradeExecutionAgent: Initialized with BinanceExchangeClient ({self.mode.value}).")

        # Initialize Bracket Manager
        self.bracket_manager = BracketOrderManager(self.exchange)

        # Portfolio tracker reference
        self.portfolio_tracker = portfolio_tracker or PortfolioTracker()

        # Telemetry & Performance Tracking
        self.total_orders_executed: int = 0
        self.total_volume_usd: float = 0.0
        self.total_fees_paid_usd: float = 0.0
        self.execution_reports: List[ExecutionReport] = []
        self.executed_intents: Dict[str, Tuple[BracketOrderGroup, ExecutionReport]] = {}

        # Wire up event subscriptions
        self._subscribe_events()

    def _subscribe_events(self) -> None:
        """Subscribes to asynchronous pub/sub pipeline events."""
        event_bus.subscribe(EVENT_ORDER_INTENT, self._on_order_intent_event)
        event_bus.subscribe(EVENT_EMERGENCY_FLATTEN, self._on_emergency_flatten_event)
        event_bus.subscribe(EVENT_CIRCUIT_BREAKER_TRIPPED, self._on_circuit_breaker_event)

    def _on_order_intent_event(self, intent: OrderIntent) -> None:
        """Event listener for incoming OrderIntent."""
        if not isinstance(intent, OrderIntent):
            return
        logger.info(f"TradeExecutionAgent: Received {EVENT_ORDER_INTENT} for {intent.symbol} ({intent.intent_id})")
        self.execute_order_intent(intent)

    def _on_emergency_flatten_event(self, data: Any) -> None:
        """Event listener for emergency flatten command."""
        logger.critical("TradeExecutionAgent: EVENT_EMERGENCY_FLATTEN triggered! Executing market liquidation.")
        symbol = data if isinstance(data, str) else None
        self.emergency_flatten(symbol)

    def _on_circuit_breaker_event(self, reason: Any) -> None:
        """Event listener for tripped risk circuit breaker."""
        logger.critical(f"TradeExecutionAgent: Circuit breaker tripped ({reason})! Flattening active inventory.")
        self.emergency_flatten()

    def execute_order_intent(
        self, intent: OrderIntent
    ) -> Tuple[BracketOrderGroup, ExecutionReport]:
        """Processes and routes an actionable OrderIntent through the execution pipeline."""
        # Idempotency guard: prevent duplicate executions of the exact same intent
        if intent.intent_id in self.executed_intents:
            logger.info(
                f"TradeExecutionAgent: OrderIntent [{intent.intent_id}] already executed (idempotency guard). Returning registered bracket."
            )
            return self.executed_intents[intent.intent_id]

        logger.info(
            f"TradeExecutionAgent: Executing {intent.side} {intent.quantity_asset:.6f} {intent.symbol} "
            f"(${intent.notional_usd:.2f}) [{intent.urgency}]"
        )

        bracket, report = self.bracket_manager.submit_bracket_intent(intent)
        self.executed_intents[intent.intent_id] = (bracket, report)

        # Telemetry updates
        if report.status in (OrderStatus.OPEN, OrderStatus.FILLED):
            self.total_orders_executed += 1
            self.total_volume_usd += report.fill_price * report.filled_qty if report.fill_price > 0 else intent.notional_usd
            self.total_fees_paid_usd += report.fee_paid_usd
            self.execution_reports.append(report)

        # If immediately filled, update portfolio tracker exposure
        if report.status == OrderStatus.FILLED:
            self._update_portfolio_open_exposure(intent.symbol)

        return bracket, report

    def on_price_update(
        self,
        symbol: str,
        current_price: float,
        high_price: Optional[float] = None,
        low_price: Optional[float] = None,
    ) -> List[ExecutionReport]:
        """Propagates market price updates to the bracket manager and updates portfolio tracking."""
        # 1. Process fills from bracket manager
        filled_reports = self.bracket_manager.handle_market_tick(
            symbol, current_price, high_price, low_price
        )

        for report in filled_reports:
            self.total_orders_executed += 1
            self.total_volume_usd += report.fill_price * report.filled_qty
            self.total_fees_paid_usd += report.fee_paid_usd
            self.execution_reports.append(report)

            # If an exit order was filled (SL or TP), compute realized PnL and record in PortfolioTracker
            if report.role in (OrderRole.STOP_LOSS, OrderRole.TAKE_PROFIT_1, OrderRole.TAKE_PROFIT_2, OrderRole.EMERGENCY_FLATTEN):
                self._record_closed_trade_result(report)

        # 2. Check for stale positions exceeding max_hold_candles
        for pos_id, pos in list(self.bracket_manager.positions.items()):
            if (symbol is None or pos.symbol == symbol) and pos.quantity > 0:
                age_hours = (datetime.now(timezone.utc) - pos.opened_at).total_seconds() / 3600.0
                max_hold = getattr(pos, "max_hold_candles", 72)
                if age_hours >= max_hold:
                    logger.warning(
                        f"Position {pos_id} exceeded max hold time ({age_hours:.1f}h >= {max_hold}h). Force-closing."
                    )
                    close_report = self.bracket_manager.force_close_position(pos_id, current_price)
                    if close_report:
                        self.total_orders_executed += 1
                        self.total_volume_usd += close_report.fill_price * close_report.filled_qty
                        self.total_fees_paid_usd += close_report.fee_paid_usd
                        self.execution_reports.append(close_report)
                        self._record_closed_trade_result(close_report)
                        filled_reports.append(close_report)

        # 3. Update unrealized PnL and active positions in portfolio tracker
        self._update_portfolio_mark_to_market(symbol, current_price)

        return filled_reports

    def check_and_cancel_invalidations(
        self, symbol: str, current_price: float, invalidation_price: float
    ) -> List[str]:
        """Audits open resting parent limit orders and cancels them if invalidation price was violated."""
        return self.bracket_manager.cancel_on_invalidation(symbol, current_price, invalidation_price)

    def emergency_flatten(self, symbol: Optional[str] = None) -> List[ExecutionReport]:
        """Liquidates all open inventory and cancels all resting orders."""
        logger.critical(f"TradeExecutionAgent: Liquidating all inventory for {symbol or 'ALL SYMBOLS'}")
        flatten_reports = self.bracket_manager.emergency_flatten(symbol)

        for rep in flatten_reports:
            if rep.status == OrderStatus.FILLED:
                self.total_orders_executed += 1
                self.total_volume_usd += rep.fill_price * rep.filled_qty
                self.total_fees_paid_usd += rep.fee_paid_usd
                self.execution_reports.append(rep)
                self._record_closed_trade_result(rep)

        # Reset exposure in portfolio tracker
        if self.portfolio_tracker:
            self.portfolio_tracker.update_unrealized_pnl(0.0, 0.0)

        return flatten_reports

    def _update_portfolio_open_exposure(self, symbol: str) -> None:
        """Synchronizes open exposure to PortfolioTracker."""
        if not self.portfolio_tracker:
            return

        total_exposure = sum(
            pos.notional_usd
            for pos in self.bracket_manager.positions.values()
            if pos.quantity > 0
        )
        self.portfolio_tracker.update_unrealized_pnl(
            self.portfolio_tracker.unrealized_pnl, total_exposure
        )

    def _update_portfolio_mark_to_market(self, symbol: str, current_price: float) -> None:
        """Calculates unrealized PnL for active positions and updates portfolio tracker."""
        if not self.portfolio_tracker:
            return

        total_unrealized_pnl = 0.0
        total_open_exposure = 0.0

        for pos in self.bracket_manager.positions.values():
            if pos.symbol == symbol and pos.quantity > 0:
                pos.current_mark_price = current_price
                if pos.side == "LONG":
                    pnl = (current_price - pos.entry_price) * pos.quantity
                else:
                    pnl = (pos.entry_price - current_price) * pos.quantity

                pos.unrealized_pnl_usd = round(pnl, 2)
                pos.unrealized_pnl_pct = round(pnl / (pos.entry_price * pos.quantity), 4) if pos.entry_price > 0 else 0.0

                total_unrealized_pnl += pnl
                total_open_exposure += (current_price * pos.quantity)

        self.portfolio_tracker.update_unrealized_pnl(total_unrealized_pnl, total_open_exposure)
        self.portfolio_tracker.update_open_positions([
            pos.to_dict() for pos in self.bracket_manager.positions.values() if pos.quantity > 0
        ])

    def _record_closed_trade_result(self, exit_report: ExecutionReport) -> None:
        """Computes realized dollar PnL for an exit order and posts to PortfolioTracker."""
        if not self.portfolio_tracker:
            return

        # Find matching position accurately
        matched_pos: Optional[ActivePosition] = None

        # 1. Try to extract position_id from client_order_id: strat1-[sl|tp1|tp2|fc|flatten]-pos-XXXX
        if exit_report.client_order_id:
            parts = exit_report.client_order_id.split("-")
            for idx, part in enumerate(parts):
                if part == "pos" and idx + 1 < len(parts):
                    pos_key = f"pos-{parts[idx+1]}"
                    if hasattr(self.bracket_manager, "get_position"):
                        matched_pos = self.bracket_manager.get_position(pos_key)
                    if matched_pos:
                        break

        # 2. If not found by client_order_id, search active positions with quantity > 0
        if not matched_pos:
            for pos in self.bracket_manager.positions.values():
                if pos.symbol == exit_report.symbol and pos.quantity > 0:
                    matched_pos = pos
                    break

        # 3. If still not found, check recently closed positions in bracket_manager
        if not matched_pos and hasattr(self.bracket_manager, "closed_positions"):
            for pos in reversed(list(self.bracket_manager.closed_positions.values())):
                if pos.symbol == exit_report.symbol:
                    matched_pos = pos
                    break

        # 4. Fallback: match by symbol
        if not matched_pos:
            for pos in self.bracket_manager.positions.values():
                if pos.symbol == exit_report.symbol:
                    matched_pos = pos
                    break

        if not matched_pos:
            logger.warning(f"TradeExecutionAgent: Could not match exit report {exit_report.order_id} to any position.")
            return

        pos = matched_pos
        if pos.side == "LONG":
            gross_pnl = (exit_report.fill_price - pos.entry_price) * exit_report.filled_qty
        else:
            gross_pnl = (pos.entry_price - exit_report.fill_price) * exit_report.filled_qty

        net_pnl = gross_pnl - exit_report.fee_paid_usd
        denom = pos.entry_price * exit_report.filled_qty
        ret_pct = (net_pnl / denom * 100) if denom > 0 else 0.0
        trade_ts = getattr(self.portfolio_tracker, "current_time", None) or datetime.now(timezone.utc)
        self.portfolio_tracker.record_trade_result(
            net_pnl=net_pnl,
            timestamp=trade_ts,
            notes=f"{pos.side} {exit_report.role.value} | Entry: ${pos.entry_price:,.2f} Exit: ${exit_report.fill_price:,.2f} Ret: {ret_pct:+.2f}%",
        )
        if self.portfolio_tracker.trade_history:
            last_trade = self.portfolio_tracker.trade_history[-1]
            last_trade.update({
                "symbol": pos.symbol,
                "side": pos.side,
                "entry_price": round(pos.entry_price, 2),
                "exit_price": round(exit_report.fill_price, 2),
                "quantity": round(exit_report.filled_qty, 6),
                "gross_pnl": round(gross_pnl, 2),
                "return_pct": round(ret_pct, 2),
                "exit_reason": exit_report.role.value,
            })
        logger.info(
            f"TradeExecutionAgent: Trade Result Posted -> Net PnL: ${net_pnl:+,.2f} "
            f"({exit_report.role.value}) | Entry: ${pos.entry_price:,.2f} Exit: ${exit_report.fill_price:,.2f} | New Cash: ${self.portfolio_tracker.current_cash:,.2f}"
        )

    def get_status(self) -> Dict[str, Any]:
        """Returns agent telemetry, balance, and position status."""
        active_pos_list = [
            pos.to_dict()
            for pos in self.bracket_manager.positions.values()
            if pos.quantity > 0
        ]
        balance_info = (
            self.exchange.fetch_balance()
            if hasattr(self.exchange, "fetch_balance")
            else {}
        )

        return {
            "agent_state": self.state.value,
            "execution_mode": self.mode.value,
            "total_orders_executed": self.total_orders_executed,
            "total_volume_usd": round(self.total_volume_usd, 2),
            "total_fees_paid_usd": round(self.total_fees_paid_usd, 4),
            "active_positions_count": len(active_pos_list),
            "active_positions": active_pos_list,
            "balance": balance_info,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
