"""Lightweight asynchronous event bus for decoupled agent communication."""

import asyncio
import inspect
from collections import defaultdict, deque
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional
from loguru import logger


# Predefined event types
EVENT_DATA_QUALITY_REPORT = "data.quality.report"
EVENT_DATA_QUALITY_HALT = "data.quality.halt"
EVENT_DATA_QUALITY_ANOMALY = "data.quality.anomaly"
EVENT_TECHNICAL_REPORT = "technical.analysis.report"
EVENT_TECHNICAL_SIGNAL = "technical.analysis.signal"
EVENT_MARKET_INTELLIGENCE_REPORT = "market.intelligence.report"
EVENT_MARKET_INTELLIGENCE_ALERT = "market.intelligence.alert"
EVENT_VOLATILITY_REPORT = "volatility.forecast.report"
EVENT_VOLATILITY_REGIME_CHANGE = "volatility.regime.change"
EVENT_STRATEGY_POPULATION_EVOLVED = "strategy.population.evolved"
EVENT_STRATEGY_CHAMPION_SELECTED = "strategy.champion.selected"
EVENT_TRADE_PROPOSAL = "strategy.trade.proposal"
EVENT_RISK_ASSESSMENT = "risk.assessment.report"
EVENT_CIRCUIT_BREAKER_TRIPPED = "risk.circuit_breaker.tripped"
EVENT_EMERGENCY_FLATTEN = "portfolio.emergency.flatten"
EVENT_MONEY_DECISION = "money.management.decision"
EVENT_TRADE_DECISION = "trade.decider.decision"
EVENT_ORDER_INTENT = "order.execution.intent"

# Sprint 9: Trade Execution Events
EVENT_ORDER_SUBMITTED = "order.execution.submitted"
EVENT_ORDER_FILLED = "order.execution.filled"
EVENT_ORDER_CANCELLED = "order.execution.cancelled"
EVENT_POSITION_OPENED = "portfolio.position.opened"
EVENT_POSITION_CLOSED = "portfolio.position.closed"
EVENT_EXECUTION_REPORT = "order.execution.report"

# Sprint 11: Real-Time Streaming & WebSocket Events
EVENT_MARKET_TICK = "market.tick.update"
EVENT_CANDLE_CLOSED = "candle.15m.closed"



class EventBus:
    """Publish-Subscribe event bus supporting both sync and async handlers with audit logging."""

    def __init__(self, history_limit: int = 100) -> None:
        self._subscribers: Dict[str, List[Callable[[Any], Any]]] = defaultdict(list)
        self._history: deque = deque(maxlen=history_limit)

    def subscribe(self, event_name: str, handler: Callable[[Any], Any]) -> None:
        """Subscribe a callback handler to an event topic."""
        if handler not in self._subscribers[event_name]:
            self._subscribers[event_name].append(handler)
            logger.debug(f"Subscribed {handler.__name__} to event: {event_name}")

    def unsubscribe(self, event_name: str, handler: Callable[[Any], Any]) -> None:
        """Unsubscribe a callback handler from an event topic."""
        if handler in self._subscribers[event_name]:
            self._subscribers[event_name].remove(handler)
            logger.debug(f"Unsubscribed {handler.__name__} from event: {event_name}")

    def _record_history(self, event_name: str, data: Any) -> None:
        self._history.append({
            "timestamp": datetime.now(timezone.utc),
            "event": event_name,
            "data_type": type(data).__name__,
        })

    def get_history(self, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """Returns the in-memory circular history of recent events."""
        items = list(self._history)
        if limit:
            return items[-limit:]
        return items

    async def publish_async(self, event_name: str, data: Any) -> None:
        """Publish an event and await all async handlers."""
        self._record_history(event_name, data)
        handlers = list(self._subscribers.get(event_name, []))
        for handler in handlers:
            try:
                if inspect.iscoroutinefunction(handler):
                    await handler(data)
                else:
                    handler(data)
            except Exception as e:
                logger.error(f"Error executing handler {handler.__name__} for event '{event_name}': {e}")

    def publish(self, event_name: str, data: Any) -> None:
        """Publish an event synchronously (fires background task if inside event loop)."""
        self._record_history(event_name, data)
        handlers = list(self._subscribers.get(event_name, []))
        for handler in handlers:
            try:
                if inspect.iscoroutinefunction(handler):
                    try:
                        loop = asyncio.get_running_loop()
                        loop.create_task(handler(data))
                    except RuntimeError:
                        asyncio.run(handler(data))
                else:
                    handler(data)
            except Exception as e:
                logger.error(f"Error in handler {handler.__name__} on event '{event_name}': {e}")

    def clear(self) -> None:
        """Clear all active subscriptions and history."""
        self._subscribers.clear()
        self._history.clear()


# Global event bus singleton instance
event_bus = EventBus()
