import base64
from io import BytesIO

import pytest
import test_alconna as alconna_tests
from fakes import FakeHTTP
from nonebot.drivers import Response
from test_api import client_for, response

from nonebot.adapters.seatalk import Message, MessageSegment
from nonebot.adapters.seatalk.exception import ActionFailed, NetworkError, UnsupportedMessage
from nonebot.adapters.seatalk.models import Destination, SendResult

alc = alconna_tests.alc
alc_bot = alconna_tests.alc_bot


PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aS1sAAAAASUVORK5CYII="
)


async def test_universal_raw_image_reaches_group_api(alc, alc_bot):
    from nonebot_plugin_alconna.uniseg import Image, Target

    bot, http = alc_bot
    receipt = await alc.UniMessage(Image(raw=PNG)).send(
        Target("group-a", adapter="SeaTalk", extra={"thread_id": "root-a"}),
        bot,
        fallback=False,
    )
    assert http.requests[-1].json == {
        "group_id": "group-a",
        "message": {
            "tag": "image",
            "image": {"content": base64.b64encode(PNG).decode()},
            "thread_id": "root-a",
        },
    }
    assert receipt.get_reply(0).id == "sent-a"


@pytest.mark.parametrize("private", [False, True])
@pytest.mark.parametrize("source", ["raw", "buffer", "path", "url"])
async def test_universal_image_sources(alc, alc_bot, tmp_path, source, private):
    from nonebot_plugin_alconna.uniseg import Image, Target

    bot, http = alc_bot
    file = tmp_path / "image.png"
    file.write_bytes(PNG)
    values = {
        "raw": {"raw": PNG},
        "buffer": {"raw": BytesIO(PNG)},
        "path": {"path": file},
        "url": {"url": "https://media.example/image"},
    }
    if source == "url":
        http.responses.insert(0, Response(200, content=PNG))
    await alc.UniMessage(Image(**values[source])).send(
        Target("employee-a" if private else "group-a", private=private, adapter="SeaTalk"), bot
    )
    assert http.requests[-1].json["message"]["image"]["content"] == base64.b64encode(PNG).decode()
    assert http.requests[-1].url.path.endswith("single_chat" if private else "group_chat")
    if source == "url":
        assert not http.requests[0].headers.get("Authorization")


@pytest.mark.parametrize("source", ["bytes", "path", "stringpath", "fileuri", "base64", "data"])
async def test_native_image_sources(case, tmp_path, source):
    file = tmp_path / "image with spaces.png"
    file.write_bytes(PNG)
    encoded = base64.b64encode(PNG).decode()
    values = {
        "bytes": PNG,
        "path": file,
        "stringpath": str(file),
        "fileuri": file.as_uri(),
        "base64": "base64://" + encoded,
        "data": "data:image/png;base64," + encoded,
    }
    http = FakeHTTP(response(case("http/token")["response"]), response({"code": 0}))
    result = await client_for(http).send_message(
        Destination("private", "employee-a"), Message(MessageSegment.image(values[source]))
    )
    assert isinstance(result, SendResult)
    assert result.message_id is None
    assert http.requests[-1].json["message"]["image"]["content"] == encoded


@pytest.mark.parametrize("private", [False, True])
async def test_mixed_images_split_in_order_with_real_receipts(alc, alc_bot, private):
    from nonebot_plugin_alconna.uniseg import Image, Reply, Target, Text

    bot, http = alc_bot
    http.responses.extend(response({"code": 0, "message_id": f"sent-{n}"}) for n in range(1, 4))
    parts = [Text("before"), Image(raw=PNG), Image(raw=PNG), Text("after")]
    if not private:
        parts.insert(0, Reply("quote-a"))
    receipt = await alc.UniMessage(parts).send(
        Target(
            "employee-a" if private else "group-a",
            private=private,
            adapter="SeaTalk",
            extra={"thread_id": "root-a"},
        ),
        bot,
    )
    bodies = [r.json["message"] for r in http.requests[1:]]
    assert [b["tag"] for b in bodies] == ["text", "image", "image", "text"]
    assert bodies[0]["text"]["content"] == "before"
    assert bodies[3]["text"]["content"] == "after"
    assert all(b["thread_id"] == "root-a" for b in bodies)
    assert all(b.get("quoted_message_id") == (None if private else "quote-a") for b in bodies)
    assert [receipt.get_reply(n).id for n in range(4)] == ["sent-a", "sent-1", "sent-2", "sent-3"]


async def test_image_batch_failure_stops_without_replay(case):
    http = FakeHTTP(
        response(case("http/token")["response"]),
        response({"code": 0, "message_id": "sent-a"}),
        response({"code": 101}),
    )
    with pytest.raises(ActionFailed):
        await client_for(http).send_message(
            Destination("group", "group-a"),
            Message("before") + MessageSegment.image(PNG) + "after",
        )
    assert len(http.requests) == 3


@pytest.mark.parametrize(
    "payload", [b"not an image", b"", "base64://!invalid!", "data:text/plain;base64,YQ=="]
)
async def test_bad_image_rejected_before_any_send(payload):
    http = FakeHTTP()
    with pytest.raises(UnsupportedMessage):
        await client_for(http).send_message(
            Destination("group", "group-a"), Message("before") + MessageSegment.image(payload)
        )
    assert http.requests == []


@pytest.mark.parametrize("status", [401, 404, 500])
async def test_external_image_http_errors_are_safe(status):
    http = FakeHTTP(Response(status, content=b"secret server content"))
    with pytest.raises(NetworkError) as error:
        await client_for(http).send_message(
            Destination("group", "group-a"),
            Message(MessageSegment.image("https://media.example/a")),
        )
    assert "secret" not in str(error.value)
    assert len(http.requests) == 1
    assert not http.requests[0].headers.get("Authorization")


async def test_received_media_not_downloaded_with_bot_credentials(alc, alc_bot):
    from nonebot_plugin_alconna.uniseg import Target

    from nonebot.adapters.seatalk.message import parse_message

    bot, http = alc_bot
    native = parse_message(
        {"tag": "image", "image": {"content": "https://api.example/media/a"}}, group=True
    )
    with pytest.raises(UnsupportedMessage, match="authenticated"):
        await alc.UniMessage.of(native, adapter="SeaTalk").send(
            Target("group-a", adapter="SeaTalk"), bot, fallback=True
        )
    assert http.requests == []


@pytest.mark.parametrize("mode", ["thread", "quote"])
@pytest.mark.parametrize("derived", [False, True])
async def test_mixed_reply_policy_and_receipt_reply(alc, alc_bot, case, mode, derived):
    from nonebot_plugin_alconna.uniseg import Image, Text, get_target

    from nonebot.adapters.seatalk.config import BotConfig
    from nonebot.adapters.seatalk.event import parse_event

    bot, http = alc_bot
    bot.bot_config = BotConfig(app_id="app-a", app_secret="secret", reply_mode=mode)
    event = parse_event(case("events/group_mentioned"), app_id="app-a")
    target = get_target(event, bot) if derived else event
    http.responses.extend(
        [
            response({"code": 0, "message_id": "sent-image"}),
            response({"code": 0, "message_id": "sent-reply"}),
        ]
    )
    receipt = await alc.UniMessage([Text("caption"), Image(raw=PNG)]).send(target, bot)
    for req in http.requests[1:]:
        assert req.json["message"].get("thread_id") == ("msg-group" if mode == "thread" else None)
        assert req.json["message"].get("quoted_message_id") == (
            "msg-group" if mode == "quote" else None
        )
    assert receipt.get_reply(1).id == "sent-image"
    await receipt.reply("next", index=1)
    assert http.requests[-1].json["message"]["quoted_message_id"] == "sent-image"
    assert http.requests[-1].json["message"].get("thread_id") == (
        "msg-group" if mode == "thread" else None
    )
    assert event.thread_id is None


async def test_size_limit_and_input_not_mutated(case):
    from nonebot.adapters.seatalk.media import MAX_IMAGE_BYTES

    http = FakeHTTP()
    with pytest.raises(UnsupportedMessage, match="5 MB"):
        await client_for(http).send_message(
            Destination("group", "group-a"),
            Message(MessageSegment.image(PNG + b"0" * MAX_IMAGE_BYTES)),
        )
    assert http.requests == []
    http.responses.extend([response(case("http/token")["response"]), response({"code": 0})])
    msg = Message(MessageSegment.image(PNG))
    await client_for(http).send_message(Destination("group", "group-a"), msg)
    assert msg[0].data == {"url": PNG}


async def test_all_chunks_validated_before_partial_send():
    http = FakeHTTP()
    with pytest.raises(UnsupportedMessage):
        await client_for(http).send_message(
            Destination("group", "group-a"),
            Message("before")
            + MessageSegment.image(PNG)
            + MessageSegment.video("https://media.example/a"),
        )
    assert http.requests == []


async def test_encoded_size_limit_is_inclusive_and_not_raw_size(case):
    from nonebot.adapters.seatalk.media import MAX_IMAGE_BASE64_SIZE, MAX_IMAGE_BYTES

    http = FakeHTTP(response(case("http/token")["response"]), response({"code": 0}))
    client = client_for(http)
    image = PNG + b"0" * (MAX_IMAGE_BYTES - len(PNG))
    await client.send_message(Destination("group", "g"), Message(MessageSegment.image(image)))
    assert len(http.requests[-1].json["message"]["image"]["content"]) == MAX_IMAGE_BASE64_SIZE
    with pytest.raises(UnsupportedMessage, match="5 MB"):
        await client.send_message(
            Destination("group", "g"), Message(MessageSegment.image(image + b"0"))
        )
    assert len(http.requests) == 2
