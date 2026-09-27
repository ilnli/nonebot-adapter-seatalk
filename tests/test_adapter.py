import asyncio

import pytest
from fakes import FakeDriver, FakeWebSocket

from nonebot.adapters.seatalk import Adapter, Bot
from nonebot.adapters.seatalk import adapter as module
from nonebot.adapters.seatalk.config import BotConfig
from nonebot.adapters.seatalk.exception import EventCapacityExceeded, NetworkError
from nonebot.adapters.seatalk.transport import WebSocketSession


@pytest.fixture
async def setup_adapter(monkeypatch):
    config = BotConfig(app_id="app-a", app_secret="secret", api_base="https://api.example")
    driver = FakeDriver([config])
    adapter = Adapter(driver)
    bot = Bot(adapter, config)
    peer = FakeWebSocket()
    peer.push({"cmd": "register", "header": {"token": "ws-token"}})
    session = WebSocketSession(peer, config)
    await session.register()
    calls = []
    gate = asyncio.Event()

    async def handle(self, event):
        calls.append((self.self_id, event.event_id))
        await gate.wait()

    monkeypatch.setattr(Bot, "handle_event", handle)

    async def deliver(event_id="event-a", callback_id="cb-a", app_id="app-a", body=None):
        payload = (
            body
            if body is not None
            else {"event_type": "future", "event_id": event_id, "app_id": app_id, "event": {}}
        )
        await adapter._on_envelope(
            bot, session, {"cmd": "event", "header": {"callback_id": callback_id}, "data": payload}
        )

    yield adapter, bot, session, peer, calls, gate, deliver
    gate.set()
    await adapter._shutdown()
    await session.close()


async def test_duplicate_acks_new_callback(setup_adapter):
    _, _, _, peer, calls, _, deliver = setup_adapter
    await deliver(callback_id="cb-1")
    await deliver(callback_id="cb-2")
    assert calls == [("app-a", "event-a")]
    assert [f["header"]["callback_id"] for f in peer.sent if f["cmd"] == "ack"] == ["cb-1", "cb-2"]


async def test_cross_app_and_malformed_known_events_are_not_admitted(setup_adapter):
    _, _, _, peer, calls, _, deliver = setup_adapter
    await deliver(app_id="other")
    await deliver(body={"event_type": "message_from_bot_subscriber", "event": {"message": []}})
    assert calls == []
    assert [f for f in peer.sent if f["cmd"] == "ack"] == []


async def test_full_capacity_still_acks_duplicates(setup_adapter):
    _, _, _, peer, calls, _, deliver = setup_adapter
    for number in range(128):
        await deliver(str(number), str(number))
    await deliver("0", "duplicate")
    with pytest.raises(EventCapacityExceeded):
        await deliver("overflow", "overflow")
    assert len(calls) == 128
    assert peer.sent[-1]["header"]["callback_id"] == "duplicate"


async def test_ack_failure_retains_admitted_key(setup_adapter):
    _, _, _, peer, calls, _, deliver = setup_adapter
    peer.fail_next_send = OSError("connection lost")
    with pytest.raises(NetworkError):
        await deliver()
    await deliver(callback_id="redelivery")
    assert calls == [("app-a", "event-a")]
    assert peer.sent[-1]["header"]["callback_id"] == "redelivery"


async def test_callback_fallback_and_missing_ids(setup_adapter):
    _, _, _, _, calls, _, deliver = setup_adapter
    await deliver("", "same")
    await deliver("", "same")
    await deliver("", "")
    await deliver("", "")
    await asyncio.sleep(0)
    assert len(calls) == 3


async def test_cache_expires_but_pending_keys_do_not(setup_adapter, monkeypatch):
    adapter, _, _, _, calls, gate, deliver = setup_adapter
    now = [0.0]
    monkeypatch.setattr(module, "monotonic", lambda: now[0])
    await deliver()
    now[0] = 601
    await deliver()
    assert len(calls) == 1
    gate.set()
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    now[0] = 1202
    await deliver()
    assert len(calls) == 2
    await adapter._shutdown()


async def test_completed_cache_evicts_oldest(setup_adapter):
    adapter, _, _, _, calls, gate, deliver = setup_adapter
    gate.set()
    for number in range(4097):
        await deliver(str(number), str(number))
    await asyncio.gather(*(task for state in adapter._states.values() for task in state.tasks))
    await asyncio.sleep(0)  # Run completion callbacks before testing the completed-key cache.
    await deliver("0", "again")
    assert len(calls) == 4098


async def test_multiple_bots_do_not_share_deduplication(setup_adapter):
    adapter, _, session, _, calls, _, deliver = setup_adapter
    await deliver()
    config = BotConfig(app_id="app-b", app_secret="other", api_base="https://api.example")
    second = Bot(adapter, config)
    await adapter._on_envelope(
        second,
        session,
        {
            "header": {"callback_id": "b"},
            "data": {"event_id": "event-a", "event_type": "future", "event": {}},
        },
    )
    assert calls == [("app-a", "event-a"), ("app-b", "event-a")]


async def test_registration_lifecycle_and_terminal_kick(setup_adapter):
    adapter, _, _, _, _, _, _ = setup_adapter
    peer = FakeWebSocket()
    peer.push({"cmd": "register", "header": {"token": "registered"}})
    peer.push({"cmd": "kick", "message": "replaced"})
    adapter.driver.peers.put_nowait(peer)
    await adapter._startup()
    await asyncio.wait_for(asyncio.gather(*adapter._supervisors), 1)
    assert adapter.driver.notifications == [("connected", "app-a"), ("disconnected", "app-a")]
    assert adapter.driver.http_requests == []
    assert len(adapter.driver.connections) == 1


async def test_reconnect_and_shutdown_during_backoff(setup_adapter, monkeypatch):
    adapter, _, _, _, _, _, _ = setup_adapter
    monkeypatch.setattr(module, "RECONNECT_INITIAL", 0.01)
    adapter.driver.peers.put_nowait(OSError("unavailable"))
    peer = FakeWebSocket()
    peer.push({"cmd": "register", "header": {"token": "registered"}})
    adapter.driver.peers.put_nowait(peer)
    await adapter._startup()
    await peer.wait_sent("register")
    await asyncio.wait_for(adapter._shutdown(), 0.5)
    assert len(adapter.driver.connections) == 2
    assert all(t.done() for t in adapter._supervisors)


async def test_shutdown_cancels_stuck_handlers(setup_adapter, monkeypatch):
    adapter, _, _, _, calls, _, deliver = setup_adapter
    monkeypatch.setattr(module, "SHUTDOWN_GRACE", 0.01)
    await deliver()
    await asyncio.wait_for(adapter._shutdown(), 0.5)
    assert calls == [("app-a", "event-a")]
    assert all(not state.tasks for state in adapter._states.values())


async def test_malformed_tag_does_not_interrupt_next_callback(setup_adapter, case):
    _, _, _, peer, calls, _, deliver = setup_adapter
    payload = case("events/private")
    payload["event"]["message"]["tag"] = []
    await deliver(callback_id="malformed", body=payload)
    await deliver("valid", "valid")
    assert not peer.closed
    assert calls == [("app-a", "valid")]
    assert [f["header"]["callback_id"] for f in peer.sent if f["cmd"] == "ack"] == ["valid"]
