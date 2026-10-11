import json

import pytest

from nonebot.adapters.seatalk.event import ThreadMessageEvent, parse_event
from nonebot.adapters.seatalk.exception import InvalidEvent


@pytest.mark.parametrize("fixture", ["private", "group_mentioned", "thread"])
def test_message_description_keeps_original_body_and_context(case, fixture, seatalk_logs):
    from nonebot.adapters.seatalk.adapter import log

    payload = case(f"events/{fixture}")
    message = payload["event"]["message"]
    actor = payload["event"] if fixture == "private" else message["sender"]
    actor["username"] = "Alice <red>"
    field = "content" if fixture == "private" else "plain_text"
    message["text"][field] = "<red>Hello</red> <unknown> 中文 \\ <green>!"
    payload["token"] = "dummy-token"
    payload["app_secret"] = "dummy-secret"
    event = parse_event(payload, app_id="app-a")
    event.message.clear()
    description = event.get_event_description()
    assert "\\<red>Hello\\</red> \\<unknown> 中文" in description
    assert "sender=emp-a" in description and "seatalk_id=user-a" in description
    assert "username=Alice \\<red>" in description
    assert "private" in description if fixture == "private" else "group=group-a" in description
    if fixture == "thread":
        assert "thread=thread-a" in description
    assert f"message={message['message_id']}" in description
    assert f"event={payload['event_id']}" in description
    log("INFO", description)
    rendered = str(seatalk_logs[-1])
    assert "<red>Hello</red> <unknown> 中文" in rendered
    assert "dummy-secret" not in rendered and "dummy-token" not in rendered


@pytest.mark.parametrize("username, expected", [(None, ""), (123, ""), ("Alice", "Alice")])
@pytest.mark.parametrize("fixture", ["private", "thread"])
def test_username_uses_only_available_actor_name(case, fixture, username, expected):
    payload = case(f"events/{fixture}")
    actor = payload["event"] if fixture == "private" else payload["event"]["message"]["sender"]
    if username is not None:
        actor["username"] = username
    event = parse_event(payload, app_id="app-a")
    assert event.username == expected
    if not expected:
        assert "username=" not in event.get_event_description()


@pytest.mark.parametrize(
    "tag, summary",
    [
        ("image", "[image]"),
        ("file", "[file]"),
        ("video", "[video]"),
        ("interactive_message", "[card]"),
        ("combined_forwarded_chat_history", "[forward]"),
        ("future", "[raw]"),
    ],
)
def test_nontext_description_never_dumps_authenticated_payload(case, tag, summary):
    payload = case("events/thread")
    message = payload["event"]["message"]
    message["tag"] = tag
    message[tag] = {
        "content": "https://media.example/file?token=dummy-media-token",
        "Authorization": "Bearer dummy-token",
        "app_secret": "dummy-secret",
        "filename": "private-name.txt",
    }
    event = parse_event(payload, app_id="app-a")
    description = event.get_event_description()
    assert summary in description
    for sensitive in ("https://media.example", "dummy-", "Authorization", "private-name"):
        assert sensitive not in description


def test_notice_description_does_not_turn_mutation_payload_into_body(case):
    payload = case("events/thread")
    payload["event"]["message"]["tag"] = "edit"
    payload["event"]["message"]["edit"] = {"text": "secret edited text"}
    event = parse_event(payload, app_id="app-a")
    assert event.get_type() == "notice"
    assert "secret edited text" not in event.get_event_description()


def test_thread_session_isolates_sender_and_conversation(case):
    event = parse_event(case("events/thread"), app_id="app-a", callback_id="cb-a")
    assert isinstance(event, ThreadMessageEvent)
    assert json.loads(event.get_session_id()) == ["app-a", "group", "group-a", "thread-a", "emp-a"]
    assert event.get_user_id() == "emp-a"
    assert event.callback_id == "cb-a"


def test_private_event_keeps_original_message(case):
    event = parse_event(case("events/private"), app_id="app-a")
    event.message.clear()
    assert event.original_message.extract_plain_text() == "/echo hello"
    assert event.is_tome()
    assert json.loads(event.get_session_id()) == ["app-a", "private", "emp-a", ""]
    assert "/echo hello" in event.get_event_description()


@pytest.mark.parametrize("tag", ["edit", "recall_msgs", "change_members", "group_removed"])
def test_message_mutations_are_not_commands(case, tag):
    payload = case("events/thread")
    payload["event"]["message"]["tag"] = tag
    payload["event"]["message"][tag] = {"unknown": "preserved"}
    event = parse_event(payload, app_id="app-a")
    assert event.get_type() == "notice"
    assert event.raw_event["event"]["message"][tag] == {"unknown": "preserved"}
    with pytest.raises(ValueError):
        event.get_message()


@pytest.mark.parametrize(
    "name",
    [
        "user_enter_chatroom_with_bot",
        "bot_added_to_group_chat",
        "bot_removed_from_group_chat",
        "group_chat_converted_to_external_group",
        "interactive_message_click",
        "new_future_event",
    ],
)
def test_notices_preserve_original_payload(name):
    payload = {
        "event_type": name,
        "event_id": "e",
        "timestamp": 1,
        "event": {"value": "button", "future_field": 17},
    }
    event = parse_event(payload, app_id="app-a")
    assert event.get_type() == "notice"
    assert name in event.get_event_name()
    assert event.raw_event == payload
    with pytest.raises(ValueError):
        event.get_user_id()


def test_actor_fallback_and_unknown_message(case):
    payload = case("events/private")
    payload["event"].pop("employee_code")
    payload["event"]["message"] = {"tag": "future", "future": {"value": "x"}}
    event = parse_event(payload, app_id="app-a")
    assert event.get_user_id() == "seatalk:user-a"
    assert event.get_message()[0].type == "raw"


@pytest.mark.parametrize("mutation", ["wrong_app", "missing_group", "bad_message", "bad_timestamp"])
def test_invalid_known_events_are_rejected(case, mutation):
    payload = case("events/thread")
    if mutation == "wrong_app":
        payload["app_id"] = "other"
    elif mutation == "missing_group":
        payload["event"].pop("group_id")
    elif mutation == "bad_message":
        payload["event"]["message"] = []
    else:
        payload["timestamp"] = "not-a-time"
    with pytest.raises(InvalidEvent):
        parse_event(payload, app_id="app-a")


def test_thread_requires_thread_id(case):
    payload = case("events/thread")
    payload["event"]["message"].pop("thread_id")
    with pytest.raises(InvalidEvent, match="thread_id"):
        parse_event(payload, app_id="app-a")


def test_group_conversion_uses_operator_identity():
    payload = {
        "event_type": "group_chat_converted_to_external_group",
        "event_id": "conversion",
        "timestamp": 1,
        "event": {
            "group_id": "group-a",
            "operator": {"employee_code": "operator-a", "seatalk_id": "seatalk-a"},
        },
    }
    event = parse_event(payload, app_id="app-a")
    assert event.get_user_id() == "operator-a"
    assert json.loads(event.get_session_id()) == ["app-a", "group", "group-a", "", "operator-a"]
