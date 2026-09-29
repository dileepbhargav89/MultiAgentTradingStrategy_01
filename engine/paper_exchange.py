"""High-fidelity Paper Trading Exchange engine for zero-capital simulated execution."""

import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import numpy as np
from loguru import logger

from core.types import ExecutionMode, ExecutionReport, OrderRole, OrderStatus


class PaperExchange:
    """Emulates Binance order matching, book crossing, bracket triggers, and fee deductions."""

    def __init__(
        self,
        initial_balance_usd: float = 10000.0,
        maker_fee_rate: float = 0.0002,      # 0.02% maker fee
        taker_fee_rate: float = 0.0004,      # 0.04% taker fee
        slippage_std_bps: float = 1.0,       # Standard deviation of slippage in bps
    ) -> None:
        self.initial_balance = initial_balance_usd
        self.balance_usd = initial_balance_usd
        self.asset_balances: Dict[str, float] = {}

        self.maker_fee_rate = maker_fee_rate
        self.taker_fee_rate = taker_fee_rate
        self.slippage_std_bps = slippage_std_bps

        self.orders: Dict[str, Dict[str, Any]] = {}
        self.execution_history: List[ExecutionReport] = []
        self._current_prices: Dict[str, float] = {}

    def set_current_price(self, symbol: str, price: float) -> None:
        """Updates the current mark price for a symbol."""
        self._current_prices[symbol] = float(price)

    def get_current_price(self, symbol: str) -> float:
        """Returns the current mark price for a symbol."""
        return self._current_prices.get(symbol, 65000.0)

    def get_bid_ask(self, symbol: str) -> tuple[float, float]:
        """Calculates synthetic bid/ask spread around mark price (0.01% spread)."""
        mid = self.get_current_price(symbol)
        half_spread = mid * 0.00005
        return round(mid - half_spread, 2), round(mid + half_spread, 2)

    def create_order(
        self,
        symbol: str,
        order_type: str,
        side: str,
        amount: float,
        price: Optional[float] = None,
        role: OrderRole = OrderRole.PARENT_ENTRY,
        params: Optional[Dict[str, Any]] = None,
        intent_id: str = "",
    ) -> ExecutionReport:
        """Simulates placing an order with realistic filling, post-only validation, and fees."""
        params = params or {}
        order_id = f"sim-{uuid.uuid4().hex[:10]}"
        client_order_id = params.get("client_order_id", f"strat1-{order_id}")
        side_upper = side.upper()
        type_upper = order_type.upper()

        bid, ask = self.get_bid_ask(symbol)
        start_time = time.perf_counter()

        # Handle Post-Only check for LIMIT orders
        is_post_only = params.get("post_only", False) or params.get("timeInForce") in ("POX", "GTX")

        if type_upper == "LIMIT":
            if price is None:
                raise ValueError("Limit order requires price.")

            # If Post-Only would immediately take liquidity, reject order
            if is_post_only:
                if side_upper == "BUY" and price >= ask:
                    report = ExecutionReport(
                        order_id=order_id,
                        client_order_id=client_order_id,
                        intent_id=intent_id,
                        symbol=symbol,
                        side=side_upper,
                        order_type=type_upper,
                        role=role,
                        status=OrderStatus.REJECTED,
                        requested_price=price,
                        fill_price=0.0,
                        requested_qty=amount,
                        filled_qty=0.0,
                        fee_paid_usd=0.0,
                        slippage_bps=0.0,
                        latency_ms=(time.perf_counter() - start_time) * 1000.0,
                        execution_mode=ExecutionMode.PAPER,
                    )
                    logger.warning(f"PaperExchange: Post-only order {order_id} rejected (Buy @ ${price} >= Ask @ ${ask})")
                    self.orders[order_id] = report.to_dict()
                    return report

                if side_upper == "SELL" and price <= bid:
                    report = ExecutionReport(
                        order_id=order_id,
                        client_order_id=client_order_id,
                        intent_id=intent_id,
                        symbol=symbol,
                        side=side_upper,
                        order_type=type_upper,
                        role=role,
                        status=OrderStatus.REJECTED,
                        requested_price=price,
                        fill_price=0.0,
                        requested_qty=amount,
                        filled_qty=0.0,
                        fee_paid_usd=0.0,
                        slippage_bps=0.0,
                        latency_ms=(time.perf_counter() - start_time) * 1000.0,
                        execution_mode=ExecutionMode.PAPER,
                    )
                    logger.warning(f"PaperExchange: Post-only order {order_id} rejected (Sell @ ${price} <= Bid @ ${bid})")
                    self.orders[order_id] = report.to_dict()
                    return report

            # Store resting limit order
            order_data = {
                "order_id": order_id,
                "client_order_id": client_order_id,
                "intent_id": intent_id,
                "symbol": symbol,
                "side": side_upper,
                "order_type": type_upper,
                "role": role,
                "status": OrderStatus.OPEN,
                "price": price,
                "amount": amount,
                "filled_qty": 0.0,
                "params": params,
                "created_at": datetime.now(timezone.utc),
            }
            self.orders[order_id] = order_data

            report = ExecutionReport(
                order_id=order_id,
                client_order_id=client_order_id,
                intent_id=intent_id,
                symbol=symbol,
                side=side_upper,
                order_type=type_upper,
                role=role,
                status=OrderStatus.OPEN,
                requested_price=price,
                fill_price=0.0,
                requested_qty=amount,
                filled_qty=0.0,
                fee_paid_usd=0.0,
                slippage_bps=0.0,
                latency_ms=(time.perf_counter() - start_time) * 1000.0,
                execution_mode=ExecutionMode.PAPER,
            )
            return report

        elif type_upper == "MARKET":
            # Market order crosses the spread immediately with stochastic slippage
            slippage_bps = abs(np.random.normal(0.5, self.slippage_std_bps))
            slippage_factor = slippage_bps / 10000.0

            if side_upper == "BUY":
                exec_price = ask * (1.0 + slippage_factor)
                cost_usd = exec_price * amount
                fee_usd = cost_usd * self.taker_fee_rate
                self.balance_usd -= (cost_usd + fee_usd)
                self.asset_balances[symbol] = self.asset_balances.get(symbol, 0.0) + amount
            else:
                exec_price = bid * (1.0 - slippage_factor)
                proceeds_usd = exec_price * amount
                fee_usd = proceeds_usd * self.taker_fee_rate
                self.balance_usd += (proceeds_usd - fee_usd)
                self.asset_balances[symbol] = self.asset_balances.get(symbol, 0.0) - amount

            report = ExecutionReport(
                order_id=order_id,
                client_order_id=client_order_id,
                intent_id=intent_id,
                symbol=symbol,
                side=side_upper,
                order_type=type_upper,
                role=role,
                status=OrderStatus.FILLED,
                requested_price=self.get_current_price(symbol),
                fill_price=round(exec_price, 2),
                requested_qty=amount,
                filled_qty=amount,
                fee_paid_usd=round(fee_usd, 4),
                slippage_bps=round(slippage_bps, 2),
                latency_ms=(time.perf_counter() - start_time) * 1000.0,
                execution_mode=ExecutionMode.PAPER,
            )
            self.orders[order_id] = report.to_dict()
            self.execution_history.append(report)
            return report

        elif type_upper in ("STOP_LOSS", "STOP_MARKET", "TAKE_PROFIT", "TAKE_PROFIT_MARKET"):
            stop_price = params.get("stopPrice", price)
            if stop_price is None:
                raise ValueError(f"{type_upper} order requires stopPrice.")

            order_data = {
                "order_id": order_id,
                "client_order_id": client_order_id,
                "intent_id": intent_id,
                "symbol": symbol,
                "side": side_upper,
                "order_type": type_upper,
                "role": role,
                "status": OrderStatus.OPEN,
                "price": price,
                "stop_price": stop_price,
                "amount": amount,
                "filled_qty": 0.0,
                "params": params,
                "created_at": datetime.now(timezone.utc),
            }
            self.orders[order_id] = order_data

            report = ExecutionReport(
                order_id=order_id,
                client_order_id=client_order_id,
                intent_id=intent_id,
                symbol=symbol,
                side=side_upper,
                order_type=type_upper,
                role=role,
                status=OrderStatus.OPEN,
                requested_price=stop_price,
                fill_price=0.0,
                requested_qty=amount,
                filled_qty=0.0,
                fee_paid_usd=0.0,
                slippage_bps=0.0,
                latency_ms=(time.perf_counter() - start_time) * 1000.0,
                execution_mode=ExecutionMode.PAPER,
            )
            return report

        else:
            raise ValueError(f"Unsupported order type: {order_type}")

    def on_tick(
        self,
        symbol: str,
        current_price: float,
        high_price: Optional[float] = None,
        low_price: Optional[float] = None,
    ) -> List[ExecutionReport]:
        """Evaluates resting limit and stop/take-profit orders against new price action."""
        self.set_current_price(symbol, current_price)
        high = high_price if high_price is not None else current_price
        low = low_price if low_price is not None else current_price

        filled_reports: List[ExecutionReport] = []

        for order_id, order in list(self.orders.items()):
            if not isinstance(order, dict) or order.get("status") != OrderStatus.OPEN:
                continue
            if order.get("symbol") != symbol:
                continue

            side = order["side"]
            order_type = order["order_type"]
            amount = order["amount"]
            role = order["role"]
            intent_id = order.get("intent_id", "")
            client_order_id = order.get("client_order_id", f"strat1-{order_id}")

            is_filled = False
            fill_price = 0.0
            is_maker = True

            # 1. Standard Limit Orders
            if order_type == "LIMIT":
                limit_price = order["price"]
                if side == "BUY" and low <= limit_price:
                    is_filled = True
                    fill_price = limit_price
                elif side == "SELL" and high >= limit_price:
                    is_filled = True
                    fill_price = limit_price

            # 2. Stop Loss Orders
            elif order_type in ("STOP_LOSS", "STOP_MARKET"):
                stop_price = order["stop_price"]
                if side == "SELL" and low <= stop_price:
                    is_filled = True
                    fill_price = stop_price * (1.0 - 0.0001)  # 1 bp slippage on stop
                    is_maker = False
                elif side == "BUY" and high >= stop_price:
                    is_filled = True
                    fill_price = stop_price * (1.0 + 0.0001)
                    is_maker = False

            # 3. Take Profit Orders
            elif order_type in ("TAKE_PROFIT", "TAKE_PROFIT_MARKET"):
                tp_price = order["stop_price"]
                if side == "SELL" and high >= tp_price:
                    is_filled = True
                    fill_price = tp_price
                    is_maker = True
                elif side == "BUY" and low <= tp_price:
                    is_filled = True
                    fill_price = tp_price
                    is_maker = True

            if is_filled:
                fee_rate = self.maker_fee_rate if is_maker else self.taker_fee_rate
                notional = fill_price * amount
                fee_usd = notional * fee_rate

                if side == "BUY":
                    self.balance_usd -= (notional + fee_usd)
                    self.asset_balances[symbol] = self.asset_balances.get(symbol, 0.0) + amount
                else:
                    self.balance_usd += (notional - fee_usd)
                    self.asset_balances[symbol] = self.asset_balances.get(symbol, 0.0) - amount

                report = ExecutionReport(
                    order_id=order_id,
                    client_order_id=client_order_id,
                    intent_id=intent_id,
                    symbol=symbol,
                    side=side,
                    order_type=order_type,
                    role=role,
                    status=OrderStatus.FILLED,
                    requested_price=order.get("price") or order.get("stop_price", fill_price),
                    fill_price=round(fill_price, 2),
                    requested_qty=amount,
                    filled_qty=amount,
                    fee_paid_usd=round(fee_usd, 4),
                    slippage_bps=0.0 if is_maker else 1.0,
                    latency_ms=1.5,
                    execution_mode=ExecutionMode.PAPER,
                )

                order["status"] = OrderStatus.FILLED
                order["fill_price"] = fill_price
                order["fee_paid_usd"] = fee_usd
                self.orders[order_id] = report.to_dict()
                self.execution_history.append(report)
                filled_reports.append(report)
                logger.info(
                    f"PaperExchange: Order FILLED [{order_id}] {role.value} {side} {amount:.6f} @ ${fill_price:,.2f}"
                )

        return filled_reports

    def cancel_order(self, order_id: str, symbol: str) -> ExecutionReport:
        """Cancels an open order."""
        if order_id not in self.orders:
            raise KeyError(f"Order {order_id} not found in PaperExchange.")

        order = self.orders[order_id]
        if isinstance(order, dict):
            order["status"] = OrderStatus.CANCELLED
            report = ExecutionReport(
                order_id=order_id,
                client_order_id=order.get("client_order_id", f"strat1-{order_id}"),
                intent_id=order.get("intent_id", ""),
                symbol=symbol,
                side=order.get("side", "BUY"),
                order_type=order.get("order_type", "LIMIT"),
                role=order.get("role", OrderRole.PARENT_ENTRY),
                status=OrderStatus.CANCELLED,
                requested_price=order.get("price", 0.0),
                fill_price=0.0,
                requested_qty=order.get("amount", 0.0),
                filled_qty=0.0,
                fee_paid_usd=0.0,
                slippage_bps=0.0,
                latency_ms=1.0,
                execution_mode=ExecutionMode.PAPER,
            )
            self.orders[order_id] = report.to_dict()
            return report

        raise ValueError(f"Invalid order structure for {order_id}")

    def fetch_open_orders(self, symbol: Optional[str] = None) -> List[Dict[str, Any]]:
        """Returns all open orders."""
        open_list = []
        for o in self.orders.values():
            if isinstance(o, dict) and o.get("status") == OrderStatus.OPEN:
                if symbol is None or o.get("symbol") == symbol:
                    open_list.append(o)
        return open_list

    def fetch_balance(self) -> Dict[str, Any]:
        """Returns account balance summary."""
        return {
            "USDT": {"free": round(self.balance_usd, 2), "total": round(self.balance_usd, 2)},
            "assets": self.asset_balances,
        }
