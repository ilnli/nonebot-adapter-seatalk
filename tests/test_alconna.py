from importlib.metadata import PackageNotFoundError, entry_points, version

import pytest
from fakes import FakeDriver, FakeHTTP
from test_api import response

from nonebot.adapters.seatalk import Adapter, Bot, Message, MessageSegment
from nonebot.adapters.seatalk.config import BotConfig
from nonebot.adapters.seatalk.event import parse_event
from nonebot.adapters.seatalk.exception import UnsupportedMessage

try:
    version("nonebot-plugin-alconna")
except PackageNotFoundError:
    pytest.skip("Alconna extra is not installed", allow_module_level=True)


@pytest.fixture
def alc(app):
    from nonebot import get_driver, require

    # Register on a driver with the required mixins before plugin import.
    driver = FakeDriver([])
    driver.register_adapter(Adapter)
    assert "SeaTalk" in get_driver()._adapters
    require("nonebot_plugin_alconna")
    import nonebot_plugin_alconna as module

    return module


@pytest.fixture
def alc_bot(case):
    config = BotConfig(app_id="app-a", app_secret="dummy-secret", api_base="https://api.example")
    driver = FakeDriver([config])
    http = FakeHTTP(
        response(case("http/token")["response"]), response({"code": 0, "message_id": "sent-a"})
    )
    driver.request = http.request
    return Bot(Adapter(driver), config), http


def test_installed_loader_and_conversion(alc):
    loader = entry_points(group="n-p-alc.uniseg.adapters", name="seatalk")["seatalk"].load()()
    assert loader.get_adapter().value == "SeaTalk"
    native = (
        Message("hi") + MessageSegment.at("123", id_type="seatalk_id") + MessageSegment.reply("q")
    )
    converted = alc.UniMessage.of(native, adapter="SeaTalk")
    assert [s.type for s in converted] == ["text", "at", "reply"]
    assert converted[1].target == "seatalk:123"
    with pytest.raises(NotImplementedError):
        loader.get_fetcher()


@pytest.mark.parametrize("kind", ["image", "file", "video", "card", "forward", "raw"])
def test_incoming_media_and_opaque(alc, kind):
    from nonebot.adapters.seatalk.message import parse_message

    tag = {"card": "interactive_message", "forward": "combined_forwarded_chat_history"}.get(
        kind, kind
    )
    message = parse_message(
        {"tag": tag, tag: {"content": "https://api.example/file/a", "filename": "a.txt"}},
        group=True,
    )
    universal = alc.UniMessage.of(message, adapter="SeaTalk")
    if kind in {"image", "file", "video"}:
        assert universal[0].url == "https://api.example/file/a"
    else:
        assert universal[0].type == "other"


@pytest.mark.parametrize(
    "private,thread", [(True, None), (False, None), (False, "root-a"), (True, "root-a")]
)
async def test_unimessage_sends_to_target(alc, alc_bot, private, thread):
    from nonebot_plugin_alconna.uniseg import Target

    bot, http = alc_bot
    receipt = await alc.UniMessage.text("hello").send(
        target=Target(
            "employee-a" if private else "group-a",
            private=private,
            adapter="SeaTalk",
            extra={"thread_id": thread},
        ),
        bot=bot,
    )
    body = http.requests[-1].json
    assert body["message"]["text"] == {"format": 2, "content": "hello"}
    assert body["message"].get("thread_id") == thread
    assert body["employee_code" if private else "group_id"] == (
        "employee-a" if private else "group-a"
    )
    assert receipt.get_reply(0).id == "sent-a"
    assert not receipt.recallable and not receipt.editable


@pytest.mark.parametrize("kind", ["image", "file", "at", "role", "other"])
async def test_unsupported_fails_even_with_fallback(alc, alc_bot, kind):
    from nonebot_plugin_alconna.uniseg import At, File, Image, Other

    bot, http = alc_bot
    segments = {
        "image": Image(url="https://media.example/a"),
        "file": File(url="https://media.example/a"),
        "at": At("user", "employee-a"),
        "role": At("role", "seatalk:123"),
        "other": Other(MessageSegment.card({})),
    }
    with pytest.raises(UnsupportedMessage):
        await alc.UniMessage([segments[kind]]).export(bot=bot, fallback=True)
    assert http.requests == []


async def test_text_at_reply_export(alc, alc_bot):
    from nonebot_plugin_alconna.uniseg import At, Reply, Text

    bot, _ = alc_bot
    native = await alc.UniMessage([Text("hi"), At("user", "seatalk:123"), Reply("q")]).export(
        bot=bot
    )
    assert native == Message("hi") + MessageSegment.at(
        "123", id_type="seatalk_id"
    ) + MessageSegment.reply("q")


async def test_no_phantom_reply_or_private_target(alc, alc_bot, case):
    from nonebot_plugin_alconna.uniseg import Target
    from nonebot_plugin_alconna.uniseg.constraint import SerializeFailed

    bot, http = alc_bot
    http.responses[-1] = response({"code": 0})
    receipt = await alc.UniMessage.text("hi").send(
        target=Target("employee-a", private=True, adapter="SeaTalk"), bot=bot
    )
    with pytest.raises(SerializeFailed):
        receipt.get_reply(0)
    event = parse_event(case("events/private"), app_id="app-a")
    event.employee_code = None
    with pytest.raises(SerializeFailed):
        receipt.exporter.get_target(event, bot)


async def test_alconna_command_reply(alc, alc_bot, app, case):
    from arclet.alconna import Alconna, Args

    bot, http = alc_bot
    event = parse_event(case("events/thread"), app_id="app-a")
    matcher = alc.on_alconna(Alconna("echo", Args["text", str]), use_cmd_start=True, block=True)
    calls = []

    @matcher.handle()
    async def handle():
        calls.append(await alc.UniMessage.text("hello").send(target=event, bot=bot))

    async with app.test_matcher(matcher) as ctx:
        ctx.receive_event(bot, event)
        ctx.should_pass_rule()
    assert len(calls) == 1
    assert http.requests[-1].json["message"]["thread_id"] == event.thread_id
