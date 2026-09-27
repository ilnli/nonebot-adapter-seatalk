import asyncio
import json

import pytest
from fakes import FakeHTTP
from nonebot.drivers import Response

from nonebot.adapters.seatalk import api as module
from nonebot.adapters.seatalk.api import APIClient
from nonebot.adapters.seatalk.config import BotConfig
from nonebot.adapters.seatalk.exception import ActionFailed, NetworkError, UnsupportedMessage
from nonebot.adapters.seatalk.message import Message, MessageSegment, serialize_message
from nonebot.adapters.seatalk.models import Destination


def response(body, status=200, **headers):
    return Response(status, content=json.dumps(body), headers=headers)


def client_for(http):
    return APIClient(
        BotConfig(app_id="app-a", app_secret="dummy-secret", api_base="https://api.example"),
        http.request,
        timeout=10,
    )


@pytest.mark.parametrize(
    "name,destination,quote",
    [
        ("private_send", Destination("private", "employee-a"), None),
        ("group_send", Destination("group", "group-a"), None),
        ("thread_send", Destination("group", "group-a", "root-a"), None),
        ("quote_send", Destination("group", "group-a"), "quote-a"),
    ],
)
async def test_verified_requests(case, name, destination, quote):
    token, expected = case("http/token"), case("http/" + name)
    http = FakeHTTP(response(token["response"]), response(expected["response"]))
    result = await client_for(http).send_message(
        destination, Message("hel") + MessageSegment.text("lo"), quote_id=quote
    )
    assert http.requests[0].json == token["request"]
    assert http.requests[0].url.path == token["path"]
    assert http.requests[1].url.path == expected["path"]
    assert http.requests[1].json == expected["request"]
    assert http.requests[1].headers["Authorization"] == "Bearer http-token"
    assert result.message_id == expected["response"].get("message_id")
    assert result.thread_id == destination.thread_id


@pytest.mark.parametrize(
    "message,destination,quote",
    [
        (
            Message("hello") + MessageSegment.image("https://media.example/x"),
            Destination("group", "g"),
            None,
        ),
        (Message(""), Destination("group", "g"), None),
        (Message("x" * 4097), Destination("group", "g"), None),
        (Message("x") + MessageSegment.reply("a"), Destination("group", "g"), "b"),
        (Message("x"), Destination("private", "e"), "q"),
        (MessageSegment.at("e"), Destination("group", "g"), None),
        (MessageSegment.at("123", id_type="seatalk_id"), Destination("private", "e"), None),
        (MessageSegment.at("0", id_type="seatalk_id"), Destination("group", "g", "t"), None),
    ],
)
async def test_unsupported_before_token(message, destination, quote):
    http = FakeHTTP()
    with pytest.raises(UnsupportedMessage):
        await client_for(http).send_message(destination, Message(message), quote_id=quote)
    assert http.requests == []


def test_mentions_escape_plain_text_and_private_threads():
    msg = Message("**hello** <tag> ") + MessageSegment.at("12345", id_type="seatalk_id")
    body = serialize_message(msg, Destination("group", "g"))
    assert body["message"]["text"] == {
        "format": 1,
        "content": r'\*\*hello\*\* \<tag\> <mention-tag target="seatalk://user?id=12345"/>',
    }
    assert (
        serialize_message(Message("x"), Destination("private", "e", "t"))["message"]["thread_id"]
        == "t"
    )


async def test_raw_api_cannot_override_origin():
    http = FakeHTTP()
    client = client_for(http)
    for path in (
        "https://other.example/x",
        "//other.example/x",
        "/\\evil",
        "relative",
        "/a#fragment",
        "/a\nheader",
        "/%2f%2fevil",
    ):
        with pytest.raises(ValueError):
            await client.request_api("GET", path)
    assert http.requests == []


async def test_single_refresh_at_documented_expiry(monkeypatch):
    now = [1000.0]
    monkeypatch.setattr(module, "time", lambda: now[0])
    http = FakeHTTP(
        response({"code": 0, "app_access_token": "old", "expire": 1100}),
        response({"code": 0}),
        response({"code": 0, "app_access_token": "new", "expire": 2000}),
        response({"code": 0}),
        response({"code": 0}),
    )
    client = client_for(http)
    await client.request_api("GET", "/test")
    now[0] = 1100
    await asyncio.gather(client.request_api("GET", "/test"), client.request_api("GET", "/test"))
    assert len(http.requests) == 5
    assert [r.headers.get("Authorization") for r in http.requests] == [
        None,
        "Bearer old",
        None,
        "Bearer new",
        "Bearer new",
    ]


@pytest.mark.parametrize(
    "bad",
    [
        Response(200, content="not-json"),
        response([]),
        response({}),
        response({"code": False}),
        response({"code": 0}, 302),
        TimeoutError("sensitive transport data"),
    ],
)
async def test_safe_http_failures_no_retries(case, bad):
    http = FakeHTTP(response(case("http/token")["response"]), bad)
    with pytest.raises(NetworkError) as error:
        await client_for(http).request_api("GET", "/test")
    assert len(http.requests) == 2
    assert "sensitive" not in str(error.value)
    assert "http-token" not in str(error.value)


async def test_auth_rejection_invalidates_without_replay(case):
    token = response(case("http/token")["response"])
    http = FakeHTTP(token, response({"code": 100}), token, response({"code": 0}))
    client = client_for(http)
    with pytest.raises(ActionFailed) as error:
        await client.request_api("POST", "/test")
    assert error.value.code == 100
    assert len(http.requests) == 2
    await client.request_api("POST", "/test")
    assert len(http.requests) == 4


async def test_platform_error_and_rate_metadata(case):
    http = FakeHTTP(
        response(case("http/token")["response"]),
        response({"code": 101}, 429, **{"Retry-After": "5", "X-Request-ID": "req-a"}),
    )
    with pytest.raises(ActionFailed) as error:
        await client_for(http).request_api("POST", "/test")
    assert (error.value.code, error.value.retry_after, error.value.request_id) == (
        101,
        "5",
        "req-a",
    )
