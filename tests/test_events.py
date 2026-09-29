"""Tests for EventBus pub/sub messaging."""

import asyncio
import pytest
from core.events import EventBus


def test_event_bus_publish_subscribe():
    bus = EventBus()
    received = []

    def handler(data):
        received.append(data)

    bus.subscribe("test.topic", handler)
    bus.publish("test.topic", {"hello": "world"})

    assert len(received) == 1
    assert received[0] == {"hello": "world"}

    # Unsubscribe
    bus.unsubscribe("test.topic", handler)
    bus.publish("test.topic", {"another": "event"})
    assert len(received) == 1


@pytest.mark.asyncio
async def test_event_bus_async_handler():
    bus = EventBus()
    received = []

    async def async_handler(data):
        await asyncio.sleep(0.01)
        received.append(data)

    bus.subscribe("test.async", async_handler)
    await bus.publish_async("test.async", 42)

    assert len(received) == 1
    assert received[0] == 42


def test_event_bus_history():
    bus = EventBus(history_limit=10)
    bus.publish("test.event1", {"id": 1})
    bus.publish("test.event2", {"id": 2})

    history = bus.get_history()
    assert len(history) == 2
    assert history[0]["event"] == "test.event1"
    assert history[1]["event"] == "test.event2"
