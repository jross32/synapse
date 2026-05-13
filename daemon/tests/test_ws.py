"""Contract #5 — WebSocket event bus + replay protocol."""

from __future__ import annotations

import asyncio

import pytest

from synapse_daemon.ws import RING_BUFFER_SIZE, Event, EventBus


@pytest.mark.asyncio
async def test_event_ids_are_monotonic() -> None:
    bus = EventBus()
    e1 = await bus.publish("v1.project.launched", {"id": "wbscrper"})
    e2 = await bus.publish("v1.project.stopped", {"id": "wbscrper"})
    assert e1.id == 1
    assert e2.id == 2
    assert bus.last_event_id == 2


@pytest.mark.asyncio
async def test_replay_since_returns_only_newer_events() -> None:
    bus = EventBus()
    for i in range(5):
        await bus.publish("v1.tick", {"i": i})
    assert [e.payload["i"] for e in bus.replay_since(0)] == [0, 1, 2, 3, 4]
    assert [e.payload["i"] for e in bus.replay_since(2)] == [2, 3, 4]
    assert bus.replay_since(5) == []


@pytest.mark.asyncio
async def test_ring_buffer_drops_oldest_events() -> None:
    bus = EventBus(buffer_size=3)
    for i in range(5):
        await bus.publish("v1.tick", {"i": i})
    # Buffer holds last 3 events; ids 3, 4, 5.
    assert bus.buffer_size() == 3
    assert bus.buffer_min_id == 3
    assert bus.last_event_id == 5
    assert [e.id for e in bus.replay_since(0)] == [3, 4, 5]


@pytest.mark.asyncio
async def test_replay_window_exceeded_only_when_since_is_below_min() -> None:
    bus = EventBus(buffer_size=3)
    for _ in range(5):
        await bus.publish("v1.tick")
    # buffer_min_id == 3
    assert bus.replay_window_exceeded(0) is False  # first-connect case
    assert bus.replay_window_exceeded(2) is True   # client too far behind
    assert bus.replay_window_exceeded(3) is False  # exactly at the window
    assert bus.replay_window_exceeded(99) is False  # client ahead of us; not an error


@pytest.mark.asyncio
async def test_subscribers_receive_published_events() -> None:
    bus = EventBus()
    received: list[Event] = []

    async def handler(event: Event) -> None:
        received.append(event)

    await bus.subscribe(handler)
    await bus.publish("v1.project.launched", {"id": "x"})
    await bus.publish("v1.project.stopped", {"id": "x"})
    assert len(received) == 2
    assert received[0].name == "v1.project.launched"
    assert received[1].payload == {"id": "x"}


@pytest.mark.asyncio
async def test_unsubscribed_handler_stops_receiving() -> None:
    bus = EventBus()
    received: list[Event] = []

    async def handler(event: Event) -> None:
        received.append(event)

    await bus.subscribe(handler)
    await bus.publish("v1.first")
    await bus.unsubscribe(handler)
    await bus.publish("v1.second")
    assert [e.name for e in received] == ["v1.first"]


@pytest.mark.asyncio
async def test_buffer_size_default_matches_contract() -> None:
    assert RING_BUFFER_SIZE == 1000


@pytest.mark.asyncio
async def test_failing_subscriber_does_not_break_bus() -> None:
    bus = EventBus()

    async def broken(event: Event) -> None:
        raise RuntimeError("bad subscriber")

    received: list[Event] = []

    async def good(event: Event) -> None:
        received.append(event)

    await bus.subscribe(broken)
    await bus.subscribe(good)
    await bus.publish("v1.tick")
    assert len(received) == 1


@pytest.mark.asyncio
async def test_concurrent_publishers_assign_unique_ids() -> None:
    bus = EventBus()

    async def publish_n(n: int) -> None:
        for _ in range(n):
            await bus.publish("v1.tick")

    await asyncio.gather(publish_n(20), publish_n(20), publish_n(20))
    ids = sorted(e.id for e in bus.replay_since(0))
    assert ids == list(range(1, 61))
