import asyncio

import pytest
from fakes import FakeWebSocket

from nonebot.adapters.seatalk import transport
from nonebot.adapters.seatalk.config import BotConfig
from nonebot.adapters.seatalk.exception import NetworkError
from nonebot.adapters.seatalk.transport import RegistrationRejected, SessionKicked, WebSocketSession


@pytest.fixture
def peer():
    return FakeWebSocket()


@pytest.fixture
def session(peer):
    return WebSocketSession(
        peer, BotConfig(app_id="app-a", app_secret="secret", api_base="https://api.example")
    )


def registration(**settings):
    return {
        "cmd": "register",
        "header": {"app_id": "app-a", "token": "ws-token", "sid": "sid-a"},
        "data": settings,
    }


async def test_register_then_ack(session, peer):
    peer.push(registration(heartbeat_interval=15, heartbeat_timeout=30))
    result = await session.register()
    await asyncio.gather(session.ack("cb-a"), session.ack("cb-b"))
    assert result.heartbeat_interval == 15
    assert result.heartbeat_timeout == 30
    assert peer.sent[0]["header"]["app_id"] == "app-a"
    assert peer.sent[-1]["header"]["token"] == "ws-token"
    assert {frame["header"]["callback_id"] for frame in peer.sent[1:]} == {"cb-a", "cb-b"}
    assert all(frame["header"]["rid"] for frame in peer.sent)
    await session.close()
    with pytest.raises(NetworkError):
        await session.ack("after-close")


async def test_registration_defaults(session, peer):
    peer.push(registration())
    result = await session.register()
    assert (result.heartbeat_interval, result.heartbeat_timeout) == (15, 30)
    await session.close()


@pytest.mark.parametrize(
    "bad",
    [
        {"cmd": "register", "code": 1, "message": "denied"},
        {"cmd": "register", "header": {"token": ""}},
        {"cmd": "register", "header": {"token": "x", "app_id": "other"}},
    ],
)
async def test_bad_registration_is_terminal(session, peer, bad):
    peer.push(bad)
    with pytest.raises(RegistrationRejected):
        await session.register()
    assert peer.closed


async def test_registration_deadline(session, peer, monkeypatch):
    monkeypatch.setattr(transport, "REGISTER_TIMEOUT", 0.01)
    with pytest.raises(NetworkError):
        await session.register()
    assert peer.closed


async def test_malformed_frame_does_not_hide_event(session, peer):
    peer.push(registration())
    await session.register()
    peer.incoming.put_nowait("{broken")
    peer.push({"cmd": "future"})
    event = {"cmd": "event", "header": {"callback_id": "cb"}, "data": {"event_type": "future"}}
    peer.push(event)
    peer.push({"cmd": "kick", "message": "session replaced"})
    received = []

    async def on_event(envelope):
        received.append(envelope)

    with pytest.raises(SessionKicked):
        await session.run(on_event)
    assert received == [event]
    assert not any(frame["cmd"] == "ack" for frame in peer.sent)
    assert peer.closed


async def test_missing_pong_is_not_postponed_by_more_pings(session, peer):
    peer.push(registration(heartbeat_interval=0.01, heartbeat_timeout=0.04))
    await session.register()

    async def on_event(envelope):
        pass

    with pytest.raises(NetworkError, match="heartbeat"):
        await asyncio.wait_for(session.run(on_event), 0.5)
    assert len([f for f in peer.sent if f["cmd"] == "ping"]) >= 2
    assert peer.closed


async def test_pong_and_cancellation_cleanup(session, peer):
    peer.push(registration(heartbeat_interval=0.01, heartbeat_timeout=0.04))
    await session.register()

    async def on_event(envelope):
        pass

    runner = asyncio.create_task(session.run(on_event))
    await peer.wait_sent("ping")
    peer.push({"cmd": "pong"})
    await session.ack("cb")
    runner.cancel()
    with pytest.raises(asyncio.CancelledError):
        await runner
    assert peer.closed
