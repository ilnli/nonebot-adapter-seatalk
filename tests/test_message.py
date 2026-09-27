import pytest
from nonebot.compat import type_validate_python

from nonebot.adapters.seatalk.config import BotConfig, Config
from nonebot.adapters.seatalk.message import Message, MessageSegment, parse_message


def test_text_extraction_excludes_media():
    message = Message("hello") + MessageSegment.image("https://media.example/x")
    assert message.extract_plain_text() == "hello"
    assert not message[1].is_text()
    assert str(message[1]) == "[image]"


@pytest.mark.parametrize(
    "tag",
    ["image", "file", "video", "interactive_message", "combined_forwarded_chat_history", "future"],
)
def test_incoming_nontext_preserves_payload(tag):
    content = {"content": "https://media.example/x", "filename": "file.txt", "extra": 42}
    message = parse_message({"tag": tag, tag: content, "quoted_message_id": "quote-1"}, group=True)
    assert message[0].type == "reply"
    assert message[0].data["message_id"] == "quote-1"
    assert (
        message[-1].data["payload"] == content
        if tag != "future"
        else message[-1].data["payload"][tag] == content
    )
    assert message.extract_plain_text() == ""


def test_mentions_remain_lossless_until_offsets_are_verified():
    mentions = [
        {"location": 0, "length": 3, "seatalk_id": "a"},
        {"location": 2, "length": 2, "seatalk_id": "b"},
    ]
    message = parse_message(
        {"tag": "text", "text": {"plain_text": "@A@B hi", "mentioned_list": mentions}}, group=True
    )
    assert message.extract_plain_text() == "@A@B hi"
    assert message[0].data["mentions"] == mentions


def test_private_and_group_text_fields():
    assert (
        parse_message(
            {"tag": "text", "text": {"content": "private"}}, group=False
        ).extract_plain_text()
        == "private"
    )
    assert (
        parse_message(
            {"tag": "text", "text": {"plain_text": "group"}}, group=True
        ).extract_plain_text()
        == "group"
    )


def test_config_defaults_and_redacts_secret():
    config = type_validate_python(
        BotConfig,
        {"app_id": "app-a", "app_secret": "dummy-secret", "api_base": "https://api.example"},
    )
    assert config.ws_url == "wss://ws-openapi.haiserve.com/ws/bot"
    assert "dummy-secret" not in repr(config)
    with pytest.raises(ValueError):
        type_validate_python(Config, {"seatalk_bots": [config, config]})


@pytest.mark.parametrize(
    "data",
    [
        {"app_id": "a", "app_secret": "secret"},
        {"app_id": "", "app_secret": "secret", "api_base": "https://api.example"},
        {"app_id": "a", "app_secret": "", "api_base": "https://api.example"},
        {"app_id": "a", "app_secret": "secret", "api_base": "http://api.example"},
    ],
)
def test_config_rejects_missing_identity_or_invalid_api_base(data):
    with pytest.raises(ValueError):
        type_validate_python(BotConfig, data)
