"""Bracket and OCO (One-Cancels-the-Other) Order Manager for StrategyOne."""

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from loguru import logger

from core.events import (
    EVENT_EXECUTION_REPORT,
    EVENT_ORDER_CANCELLED,
    EVENT_ORDER_FILLED,
    EVENT_ORDER_SUBMITTED,
    EVENT_POSITION_CLOSED,
    EVENT_POSITION_OPENED,
    event_bus,
)
from core.types import (
    ActivePosition,
    BracketOrderGroup,
    ExecutionMode,
    ExecutionReport,
    OrderIntent,
    OrderRole,
    OrderStatus,
)
from engine.exchange_client import BinanceExchangeClient
from engine.paper_exchange import PaperExchange


class BracketOrderManager:
    """Manages multi-tier bracket lifecycle, OCO mutual cancellation, and breakeven stop ratcheting."""

    def __init__(self, exchange: Any) -> None:
        """Exchange can be an instance of PaperExchange or BinanceExchangeClient."""
        self.exchange = exchange
        self.brackets: Dict[str, BracketOrderGroup] = {}
        self.bracket_intents: Dict[str, OrderIntent] = {}
        self.positions: Dict[str, ActivePosition] = {}
        self.closed_positions: Dict[str, ActivePosition] = {}

    def get_position(self, position_id: str) -> Optional[ActivePosition]:
        """Resolves position by ID across active and closed registries."""
        return self.positions.get(position_id) or self.closed_positions.get(position_id)

    def submit_bracket_intent(self, intent: OrderIntent) -> Tuple[BracketOrderGroup, ExecutionReport]:
        """Submits the Parent Entry order and registers the bracket structure."""
        bracket_id = f"brk-{uuid.uuid4().hex[:8]}"
        self.bracket_intents[bracket_id] = intent

        side = intent.side
        qty = intent.quantity_asset
        limit_price = intent.limit_price
        order_type = intent.order_type

        # Check pre-submission invalidation:
        current_market = getattr(self.exchange, "get_current_price", lambda s: limit_price)(intent.symbol)
        abort_entry = False
        abort_reason = ""
        if side == "BUY" and 0 < intent.invalidation_price < limit_price:
            invalidation_margin = intent.invalidation_price * 0.995  # 0.5% below invalidation
            if current_market <= invalidation_margin:
                abort_entry = True
                abort_reason = f"Market price ${current_market:,.2f} is below invalidation ${intent.invalidation_price:,.2f} (margin: ${invalidation_margin:,.2f})"
        elif side == "SELL" and intent.invalidation_price > limit_price:
            invalidation_margin = intent.invalidation_price * 1.005  # 0.5% above invalidation
            if current_market >= invalidation_margin:
                abort_entry = True
                abort_reason = f"Market price ${current_market:,.2f} is above invalidation ${intent.invalidation_price:,.2f} (margin: ${invalidation_margin:,.2f})"

        if abort_entry:
            logger.warning(f"BracketManager: Aborting entry. {abort_reason}")
            report = ExecutionReport(
                order_id=f"rej-{uuid.uuid4().hex[:6]}",
                client_order_id=intent.client_order_id or "",
                intent_id=intent.intent_id,
                symbol=intent.symbol,
                side=side,
                order_type=order_type,
                role=OrderRole.PARENT_ENTRY,
                status=OrderStatus.REJECTED,
                requested_price=limit_price,
                fill_price=0.0,
                requested_qty=qty,
                filled_qty=0.0,
                fee_paid_usd=0.0,
                slippage_bps=0.0,
                latency_ms=0.5,
            )
            bracket = BracketOrderGroup(
                bracket_id=bracket_id,
                intent_id=intent.intent_id,
                symbol=intent.symbol,
                parent_order_id=report.order_id,
                parent_status=OrderStatus.REJECTED,
            )
            return bracket, report

        # Submit Parent Order
        post_only = (intent.urgency == "PASSIVE_MAKER" and order_type == "LIMIT")
        params = {
            "client_order_id": intent.client_order_id or f"strat1-{intent.intent_id}",
            "post_only": post_only,
        }

        entry_report: ExecutionReport
        if isinstance(self.exchange, PaperExchange):
            entry_report = self.exchange.create_order(
                symbol=intent.symbol,
                order_type=order_type,
                side=side,
                amount=qty,
                price=limit_price if order_type == "LIMIT" else None,
                role=OrderRole.PARENT_ENTRY,
                params=params,
                intent_id=intent.intent_id,
            )
        else:
            # CCXT live exchange client
            raw = self.exchange.create_order(
                symbol=intent.symbol,
                order_type=order_type,
                side=side,
                amount=qty,
                price=limit_price if order_type == "LIMIT" else None,
                params=params,
            )
            entry_report = ExecutionReport(
                order_id=str(raw.get("id")),
                client_order_id=params["client_order_id"],
                intent_id=intent.intent_id,
                symbol=intent.symbol,
                side=side,
                order_type=order_type,
                role=OrderRole.PARENT_ENTRY,
                status=OrderStatus.FILLED if raw.get("status") == "closed" else OrderStatus.OPEN,
                requested_price=limit_price,
                fill_price=float(raw.get("price") or limit_price),
                requested_qty=qty,
                filled_qty=float(raw.get("filled") or 0.0),
                fee_paid_usd=0.0,
                slippage_bps=0.0,
                latency_ms=10.0,
                execution_mode=ExecutionMode.LIVE_TESTNET,
            )

        bracket = BracketOrderGroup(
            bracket_id=bracket_id,
            intent_id=intent.intent_id,
            symbol=intent.symbol,
            parent_order_id=entry_report.order_id,
            parent_status=entry_report.status,
        )
        self.brackets[bracket_id] = bracket

        event_bus.publish(EVENT_ORDER_SUBMITTED, entry_report)
        event_bus.publish(EVENT_EXECUTION_REPORT, entry_report)

        # If entry filled immediately (e.g. Market order or immediate touch)
        if entry_report.status == OrderStatus.FILLED:
            event_bus.publish(EVENT_ORDER_FILLED, entry_report)
            self._on_parent_filled(bracket_id, intent, entry_report)

        return bracket, entry_report

    def _on_parent_filled(
        self,
        bracket_id: str,
        intent: OrderIntent,
        entry_report: ExecutionReport,
    ) -> ActivePosition:
        """Triggered upon parent fill: initializes ActivePosition and places Stop Loss & Take Profit bracket."""
        bracket = self.brackets[bracket_id]
        bracket.parent_status = OrderStatus.FILLED
        bracket.is_oco_active = True

        symbol = intent.symbol
        side = intent.side
        opp_side = "SELL" if side == "BUY" else "BUY"
        filled_qty = entry_report.filled_qty
        fill_price = entry_report.fill_price

        # 1. Initialize Active Position
        position_id = f"pos-{uuid.uuid4().hex[:8]}"
        active_pos = ActivePosition(
            position_id=position_id,
            strategy_id="strat-active",
            symbol=symbol,
            side="LONG" if side == "BUY" else "SHORT",
            entry_price=fill_price,
            quantity=filled_qty,
            notional_usd=fill_price * filled_qty,
            current_mark_price=fill_price,
            unrealized_pnl_usd=0.0,
            unrealized_pnl_pct=0.0,
            stop_loss_price=intent.stop_loss_price,
            take_profit_price_1=intent.take_profit_price,
            take_profit_price_2=intent.target_2r_price,
            parent_order_id=entry_report.order_id,
        )

        # 2. Place Hard Stop Loss order for 100% of filled position
        stop_report: ExecutionReport
        stop_params = {
            "stopPrice": intent.stop_loss_price,
            "client_order_id": f"strat1-sl-{position_id}",
        }
        if isinstance(self.exchange, PaperExchange):
            stop_report = self.exchange.create_order(
                symbol=symbol,
                order_type="STOP_MARKET",
                side=opp_side,
                amount=filled_qty,
                price=intent.stop_loss_price,
                role=OrderRole.STOP_LOSS,
                params=stop_params,
                intent_id=intent.intent_id,
            )
        else:
            raw = self.exchange.create_order(
                symbol=symbol,
                order_type="STOP_MARKET",
                side=opp_side,
                amount=filled_qty,
                params=stop_params,
            )
            stop_report = ExecutionReport(
                order_id=str(raw.get("id")),
                client_order_id=stop_params["client_order_id"],
                intent_id=intent.intent_id,
                symbol=symbol,
                side=opp_side,
                order_type="STOP_MARKET",
                role=OrderRole.STOP_LOSS,
                status=OrderStatus.OPEN,
                requested_price=intent.stop_loss_price,
                fill_price=0.0,
                requested_qty=filled_qty,
                filled_qty=0.0,
                fee_paid_usd=0.0,
                slippage_bps=0.0,
                latency_ms=5.0,
            )

        active_pos.stop_order_id = stop_report.order_id
        bracket.stop_order_id = stop_report.order_id
        bracket.stop_status = OrderStatus.OPEN

        # 3. Place Take Profit 1 Limit Order (50% scale-out)
        tp1_qty = round(filled_qty * 0.50, 6)
        tp1_params = {
            "client_order_id": f"strat1-tp1-{position_id}",
            "post_only": True,
        }
        tp1_report: ExecutionReport
        if isinstance(self.exchange, PaperExchange):
            tp1_report = self.exchange.create_order(
                symbol=symbol,
                order_type="LIMIT",
                side=opp_side,
                amount=tp1_qty,
                price=intent.take_profit_price,
                role=OrderRole.TAKE_PROFIT_1,
                params=tp1_params,
                intent_id=intent.intent_id,
            )
        else:
            raw = self.exchange.create_order(
                symbol=symbol,
                order_type="LIMIT",
                side=opp_side,
                amount=tp1_qty,
                price=intent.take_profit_price,
                params=tp1_params,
            )
            tp1_report = ExecutionReport(
                order_id=str(raw.get("id")),
                client_order_id=tp1_params["client_order_id"],
                intent_id=intent.intent_id,
                symbol=symbol,
                side=opp_side,
                order_type="LIMIT",
                role=OrderRole.TAKE_PROFIT_1,
                status=OrderStatus.OPEN,
                requested_price=intent.take_profit_price,
                fill_price=0.0,
                requested_qty=tp1_qty,
                filled_qty=0.0,
                fee_paid_usd=0.0,
                slippage_bps=0.0,
                latency_ms=5.0,
            )

        active_pos.tp1_order_id = tp1_report.order_id
        bracket.tp1_order_id = tp1_report.order_id
        bracket.tp1_status = OrderStatus.OPEN

        # 4. Place Take Profit 2 Runner Order (remaining 50%)
        tp2_qty = round(filled_qty - tp1_qty, 6)
        tp2_params = {
            "client_order_id": f"strat1-tp2-{position_id}",
            "post_only": True,
        }
        tp2_report: ExecutionReport
        if isinstance(self.exchange, PaperExchange):
            tp2_report = self.exchange.create_order(
                symbol=symbol,
                order_type="LIMIT",
                side=opp_side,
                amount=tp2_qty,
                price=intent.target_2r_price,
                role=OrderRole.TAKE_PROFIT_2,
                params=tp2_params,
                intent_id=intent.intent_id,
            )
        else:
            raw = self.exchange.create_order(
                symbol=symbol,
                order_type="LIMIT",
                side=opp_side,
                amount=tp2_qty,
                price=intent.target_2r_price,
                params=tp2_params,
            )
            tp2_report = ExecutionReport(
                order_id=str(raw.get("id")),
                client_order_id=tp2_params["client_order_id"],
                intent_id=intent.intent_id,
                symbol=symbol,
                side=opp_side,
                order_type="LIMIT",
                role=OrderRole.TAKE_PROFIT_2,
                status=OrderStatus.OPEN,
                requested_price=intent.target_2r_price,
                fill_price=0.0,
                requested_qty=tp2_qty,
                filled_qty=0.0,
                fee_paid_usd=0.0,
                slippage_bps=0.0,
                latency_ms=5.0,
            )

        active_pos.tp2_order_id = tp2_report.order_id
        bracket.tp2_order_id = tp2_report.order_id
        bracket.tp2_status = OrderStatus.OPEN

        self.positions[position_id] = active_pos
        logger.info(
            f"BracketManager: Position Inception [{position_id}] {active_pos.side} {filled_qty:.6f} @ ${fill_price:,.2f} | "
            f"SL=${intent.stop_loss_price:,.2f}, TP1(50%)=${intent.take_profit_price:,.2f}, TP2(50%)=${intent.target_2r_price:,.2f}"
        )

        event_bus.publish(EVENT_POSITION_OPENED, active_pos)
        return active_pos

    def handle_market_tick(
        self,
        symbol: str,
        current_price: float,
        high_price: Optional[float] = None,
        low_price: Optional[float] = None,
    ) -> List[ExecutionReport]:
        """Processes fills from price movement and executes OCO mutual cancellation logic."""
        if not hasattr(self.exchange, "on_tick"):
            return []

        filled_reports: List[ExecutionReport] = self.exchange.on_tick(
            symbol, current_price, high_price, low_price
        )

        for report in filled_reports:
            event_bus.publish(EVENT_ORDER_FILLED, report)
            event_bus.publish(EVENT_EXECUTION_REPORT, report)

            # Find matching bracket
            matching_bracket_id = None
            for b_id, bracket in self.brackets.items():
                if report.order_id in (
                    bracket.parent_order_id,
                    bracket.stop_order_id,
                    bracket.tp1_order_id,
                    bracket.tp2_order_id,
                ):
                    matching_bracket_id = b_id
                    break

            if not matching_bracket_id:
                continue

            bracket = self.brackets[matching_bracket_id]

            # Case 1: Parent Order Filled
            if report.role == OrderRole.PARENT_ENTRY:
                logger.info(f"BracketManager: Parent Entry filled for bracket {matching_bracket_id}")
                intent = self.bracket_intents.get(matching_bracket_id)
                if intent:
                    self._on_parent_filled(matching_bracket_id, intent, report)

            # Case 2: Stop Loss Filled -> OCO triggers, cancel TP1 and TP2
            elif report.role == OrderRole.STOP_LOSS:
                bracket.stop_status = OrderStatus.FILLED
                bracket.is_oco_active = False
                logger.warning(
                    f"BracketManager: STOP LOSS triggered at ${report.fill_price:,.2f}! Cancelling TP targets..."
                )
                if bracket.tp1_order_id and bracket.tp1_status == OrderStatus.OPEN:
                    self.exchange.cancel_order(bracket.tp1_order_id, symbol)
                    bracket.tp1_status = OrderStatus.CANCELLED
                if bracket.tp2_order_id and bracket.tp2_status == OrderStatus.OPEN:
                    self.exchange.cancel_order(bracket.tp2_order_id, symbol)
                    bracket.tp2_status = OrderStatus.CANCELLED

                # Close position
                pos = self._find_position_by_bracket(bracket)
                if pos:
                    pos.quantity = 0.0
                    if pos.position_id in self.positions:
                        self.closed_positions[pos.position_id] = self.positions.pop(pos.position_id)
                    event_bus.publish(EVENT_POSITION_CLOSED, pos)

            # Case 3: Take Profit 1 (1.5R) Filled -> Scale out 50%, move SL to Breakeven
            elif report.role == OrderRole.TAKE_PROFIT_1:
                bracket.tp1_status = OrderStatus.FILLED
                pos = self._find_position_by_bracket(bracket)
                if pos and not pos.is_scale_out_executed:
                    pos.is_scale_out_executed = True
                    pos.is_breakeven_active = True
                    pos.quantity = round(pos.quantity - report.filled_qty, 6)
                    # Calculate cushioned stop price locking in +20% of gained distance:
                    gain_distance = abs(report.fill_price - pos.entry_price)
                    cushion = gain_distance * 0.20
                    cushioned_stop = round(pos.entry_price + cushion if pos.side == "LONG" else pos.entry_price - cushion, 2)

                    logger.info(
                        f"BracketManager: TP1 FILLED @ ${report.fill_price:,.2f}! Scaled out 50%. "
                        f"Ratcheting Stop Loss to Cushioned Profit Lock (${cushioned_stop:,.2f})."
                    )

                    # Update resting Stop Loss to cushioned price with reduced quantity
                    if bracket.stop_order_id:
                        try:
                            self.exchange.cancel_order(bracket.stop_order_id, symbol)
                        except Exception:
                            pass
                        # Re-place Stop at Cushioned Profit Price
                        opp_side = "SELL" if pos.side == "LONG" else "BUY"
                        new_sl = self.exchange.create_order(
                            symbol=symbol,
                            order_type="STOP_MARKET",
                            side=opp_side,
                            amount=pos.quantity,
                            price=cushioned_stop,
                            role=OrderRole.STOP_LOSS,
                            params={"stopPrice": cushioned_stop},
                        )
                        bracket.stop_order_id = new_sl.order_id
                        pos.stop_loss_price = cushioned_stop

            # Case 4: Take Profit 2 (2.5R Runner) Filled -> Cancel remaining Stop Loss
            elif report.role == OrderRole.TAKE_PROFIT_2:
                bracket.tp2_status = OrderStatus.FILLED
                bracket.is_oco_active = False
                logger.info(
                    f"BracketManager: TP2 (2.5R RUNNER) FILLED @ ${report.fill_price:,.2f}! Full target achieved. Cancelling remaining SL."
                )
                if bracket.stop_order_id and bracket.stop_status == OrderStatus.OPEN:
                    try:
                        self.exchange.cancel_order(bracket.stop_order_id, symbol)
                        bracket.stop_status = OrderStatus.CANCELLED
                    except Exception:
                        pass

                pos = self._find_position_by_bracket(bracket)
                if pos:
                    pos.quantity = 0.0
                    if pos.position_id in self.positions:
                        self.closed_positions[pos.position_id] = self.positions.pop(pos.position_id)
                    event_bus.publish(EVENT_POSITION_CLOSED, pos)

        return filled_reports

    def cancel_on_invalidation(self, symbol: str, current_price: float, invalidation_price: float) -> List[str]:
        """Scans all open resting Parent Entry limit orders and cancels any that have crossed invalidation."""
        cancelled_ids = []
        for bracket_id, bracket in list(self.brackets.items()):
            if bracket.symbol == symbol and bracket.parent_status == OrderStatus.OPEN:
                intent = self.bracket_intents.get(bracket_id)
                side = intent.side if intent else "BUY"
                violates = (side == "BUY" and current_price <= invalidation_price) or (
                    side == "SELL" and current_price >= invalidation_price
                )
                if violates:
                    logger.warning(
                        f"BracketManager: Cancelling open entry {bracket.parent_order_id} due to invalidation trigger "
                        f"(Price: ${current_price:,.2f}, P_inv: ${invalidation_price:,.2f})"
                    )
                    self.exchange.cancel_order(bracket.parent_order_id, symbol)
                    bracket.parent_status = OrderStatus.CANCELLED
                    cancelled_ids.append(bracket.parent_order_id)
        return cancelled_ids

    def emergency_flatten(self, symbol: Optional[str] = None) -> List[ExecutionReport]:
        """Emergency circuit breaker: cancels all open orders and liquidates active positions at market price."""
        logger.critical("BracketManager: EMERGENCY FLATTEN INITIATED! Liquidating all open inventory.")
        reports: List[ExecutionReport] = []

        # 1. Cancel all open orders
        open_orders = getattr(self.exchange, "fetch_open_orders", lambda s: [])(symbol)
        for o in open_orders:
            o_id = o.get("order_id") or o.get("id")
            o_sym = o.get("symbol", symbol or "BTC/USDT")
            if o_id:
                try:
                    c_report = self.exchange.cancel_order(o_id, o_sym)
                    if isinstance(c_report, ExecutionReport):
                        reports.append(c_report)
                    logger.info(f"BracketManager: Cancelled order {o_id} on emergency flatten.")
                except Exception as e:
                    logger.error(f"Error cancelling order {o_id}: {e}")

        # 2. Liquidate open positions — if notional > $5000, split into 3 tranches to reduce market impact
        for pos_id, pos in list(self.positions.items()):
            if (symbol is None or pos.symbol == symbol) and pos.quantity > 0:
                opp_side = "SELL" if pos.side == "LONG" else "BUY"
                notional = pos.quantity * pos.current_mark_price if pos.current_mark_price > 0 else pos.notional_usd

                if notional > 5000.0:
                    tranche_qty = pos.quantity / 3.0
                    for tranche_idx in range(3):
                        qty_step = tranche_qty if tranche_idx < 2 else (pos.quantity - tranche_qty * 2)
                        try:
                            liq_report = self.exchange.create_order(
                                symbol=pos.symbol,
                                order_type="MARKET",
                                side=opp_side,
                                amount=qty_step,
                                role=OrderRole.EMERGENCY_FLATTEN,
                                params={"client_order_id": f"strat1-flatten-{pos_id}-t{tranche_idx+1}"},
                            )
                            reports.append(liq_report)
                        except Exception as e:
                            logger.critical(f"FATAL: Tranche {tranche_idx+1} market flatten error for {pos_id}: {e}")
                    pos.quantity = 0.0
                    event_bus.publish(EVENT_POSITION_CLOSED, pos)
                    logger.critical(f"BracketManager: Position {pos_id} TWAP FLATTENED in 3 tranches (${notional:,.2f}).")
                else:
                    qty_to_liquidate = pos.quantity
                    try:
                        liq_report = self.exchange.create_order(
                            symbol=pos.symbol,
                            order_type="MARKET",
                            side=opp_side,
                            amount=qty_to_liquidate,
                            role=OrderRole.EMERGENCY_FLATTEN,
                            params={"client_order_id": f"strat1-flatten-{pos_id}"},
                        )
                        reports.append(liq_report)
                        pos.quantity = 0.0
                        event_bus.publish(EVENT_POSITION_CLOSED, pos)
                        logger.critical(
                            f"BracketManager: Position {pos_id} FLATTENED at market. {qty_to_liquidate:.6f} liquidated."
                        )
                    except Exception as e:
                        logger.critical(f"FATAL: Failed to market flatten position {pos_id}: {e}")

        return reports

    def force_close_position(self, position_id: str, current_price: float) -> Optional[ExecutionReport]:
        """Liquidates an individual open position at market price (e.g. max hold time exceeded)."""
        pos = self.positions.get(position_id)
        if not pos or pos.quantity <= 0:
            return None

        # 1. Cancel resting SL and TP orders for this position
        for bracket in self.brackets.values():
            if bracket.parent_order_id == pos.parent_order_id:
                for o_id in (bracket.stop_order_id, bracket.tp1_order_id, bracket.tp2_order_id):
                    if o_id:
                        try:
                            self.exchange.cancel_order(o_id, pos.symbol)
                        except Exception:
                            pass
                bracket.stop_status = OrderStatus.CANCELLED
                bracket.tp1_status = OrderStatus.CANCELLED
                bracket.tp2_status = OrderStatus.CANCELLED
                bracket.is_oco_active = False
                break

        # 2. Market close position
        opp_side = "SELL" if pos.side == "LONG" else "BUY"
        qty = pos.quantity
        try:
            report = self.exchange.create_order(
                symbol=pos.symbol,
                order_type="MARKET",
                side=opp_side,
                amount=qty,
                price=current_price,
                role=OrderRole.EMERGENCY_FLATTEN,
                params={"client_order_id": f"strat1-timeout-{position_id}"},
            )
            pos.quantity = 0.0
            event_bus.publish(EVENT_POSITION_CLOSED, pos)
            logger.warning(
                f"BracketManager: Position {position_id} FORCE CLOSED due to timeout at ${current_price:,.2f}"
            )
            return report
        except Exception as e:
            logger.error(f"Failed to force close position {position_id}: {e}")
            return None

    def _find_position_by_bracket(self, bracket: BracketOrderGroup) -> Optional[ActivePosition]:
        for pos in self.positions.values():
            if pos.parent_order_id == bracket.parent_order_id:
                return pos
        for pos in self.closed_positions.values():
            if pos.parent_order_id == bracket.parent_order_id:
                return pos
        return None
