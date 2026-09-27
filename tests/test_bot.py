import pytest
from fakes import FakeDriver
from nonebot.rule import to_me

from nonebot import on_command
from nonebot.adapters.seatalk import Adapter, Bot, Message, MessageSegment
from nonebot.adapters.seatalk import bot as module
from nonebot.adapters.seatalk.config import BotConfig
from nonebot.adapters.seatalk.event import parse_event


@pytest.fixture
def bot():
    config = BotConfig(
        app_id="app-a", app_secret="secret", api_base="https://api.example", bot_seatalk_id="self-a"
    )
    return Bot(Adapter(FakeDriver([config])), config)


@pytest.mark.parametrize(
    "prefix, addressed, remaining",
    [
        (MessageSegment.at("self-a", id_type="seatalk_id"), True, "/echo hi"),
        (MessageSegment.at("someone", id_type="seatalk_id"), False, "/echo hi"),
        (MessageSegment.text("bot "), True, "/echo hi"),
        (MessageSegment.text("botany "), False, "botany /echo hi"),
    ],
)
async def test_preprocess_only_recognized_self_prefix(
    bot, case, monkeypatch, prefix, addressed, remaining
):
    event = parse_event(case("events/thread"), app_id="app-a")
    event.message = Message(prefix) + MessageSegment.text("/echo hi")
    event.original_message = event.message.copy()
    original = event.original_message.copy()
    calls = []

    async def handle(bot, event):
        calls.append(event)

    monkeypatch.setattr(module, "handle_event", handle)
    await bot.handle_event(event)
    assert calls == [event]
    assert event.is_tome() is addressed
    assert event.message.extract_plain_text() == remaining
    assert event.original_message == original
    if prefix.type == "at" and not addressed:
        assert event.message[0] == prefix


async def test_unidentified_mentions_remain_text(bot, case, monkeypatch):
    payload = case("events/group_mentioned")
    payload["event"]["message"]["text"] = {"plain_text": "@unknown /echo hi", "mentioned_list": []}
    event = parse_event(payload, app_id="app-a")

    async def handle(bot, event):
        pass

    monkeypatch.setattr(module, "handle_event", handle)
    await bot.handle_event(event)
    assert event.message.extract_plain_text() == "@unknown /echo hi"
    assert event.is_tome()


async def test_ignore_only_configured_self_sender(bot, case, monkeypatch):
    calls = []

    async def handle(bot, event):
        calls.append(event.seatalk_id)

    monkeypatch.setattr(module, "handle_event", handle)
    event = parse_event(case("events/thread"), app_id="app-a")
    event.seatalk_id = "self-a"
    await bot.handle_event(event)
    event.seatalk_id = "another-bot"
    await bot.handle_event(event)
    assert calls == ["another-bot"]


@pytest.mark.parametrize("fixture", ["private", "group_mentioned", "thread"])
async def test_command_matches_normalized_event(app, bot, case, fixture):
    event = parse_event(case(f"events/{fixture}"), app_id="app-a")
    event.to_me = True
    matcher = on_command("echo", rule=to_me(), block=True)
    calls = []

    @matcher.handle()
    async def handle():
        calls.append("called")

    async with app.test_matcher(matcher) as ctx:
        ctx.receive_event(bot, event)
        ctx.should_pass_rule()
    assert calls == ["called"]


async def test_quoted_command_matches_after_preprocessing(app, bot, case, monkeypatch):
    payload = case("events/private")
    payload["event"]["message"]["quoted_message_id"] = "quoted-message"
    event = parse_event(payload, app_id="app-a")

    async def defer_dispatch(bot, event):
        pass

    monkeypatch.setattr(module, "handle_event", defer_dispatch)
    await bot.handle_event(event)
    matcher = on_command("echo", rule=to_me(), block=True)
    calls = []

    @matcher.handle()
    async def handle():
        calls.append("called")

    async with app.test_matcher(matcher) as ctx:
        ctx.receive_event(bot, event)
        ctx.should_pass_rule()
    assert calls == ["called"]
    assert event.quoted_message_id == "quoted-message"
    assert event.original_message[0].type == "reply"
