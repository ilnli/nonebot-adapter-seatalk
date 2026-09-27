import json
from copy import deepcopy
from typing import Any

from nonebot.adapters import Event as BaseEvent

from .exception import InvalidEvent
from .message import Message, parse_message


class Event(BaseEvent):
    app_id: str
    event_id: str = ""
    event_type: str
    timestamp: int = 0
    callback_id: str = ""
    raw_event: dict[str, Any]
    employee_code: str = ""
    seatalk_id: str = ""
    group_id: str | None = None
    thread_id: str | None = None
    message_id: str | None = None
    to_me: bool = False

    def get_type(self) -> str:
        return "notice"

    def get_event_name(self) -> str:
        return f"{self.get_type()}.{self.event_type}"

    def get_event_description(self) -> str:
        return f"app={self.app_id} event={self.event_id} message={self.message_id or ''}"

    def get_user_id(self) -> str:
        if self.employee_code:
            return self.employee_code
        if self.seatalk_id:
            return f"seatalk:{self.seatalk_id}"
        raise ValueError("This event has no actor")

    def get_session_id(self) -> str:
        user_id = self.get_user_id()
        parts = (
            [self.app_id, "group", self.group_id, self.thread_id or "", user_id]
            if self.group_id
            else [self.app_id, "private", user_id, self.thread_id or ""]
        )
        return json.dumps(parts, ensure_ascii=False, separators=(",", ":"))

    def get_message(self) -> Message:
        raise ValueError("This event has no message")

    def is_tome(self) -> bool:
        return self.to_me


class MessageEvent(Event):
    message: Message
    original_message: Message
    quoted_message_id: str | None = None
    explicit_mention: bool = False

    def get_type(self) -> str:
        return "message"

    def get_message(self) -> Message:
        return self.message


class PrivateMessageEvent(MessageEvent):
    pass


class GroupMessageEvent(MessageEvent):
    pass


class ThreadMessageEvent(GroupMessageEvent):
    pass


class NoticeEvent(Event):
    pass


class InteractiveMessageClickEvent(NoticeEvent):
    value: str = ""


class ChatEntryNoticeEvent(NoticeEvent):
    pass


class BotAddedNoticeEvent(NoticeEvent):
    pass


class BotRemovedNoticeEvent(NoticeEvent):
    pass


class GroupConvertedNoticeEvent(NoticeEvent):
    pass


class MessageEditedNoticeEvent(NoticeEvent):
    pass


class MessageRecalledNoticeEvent(NoticeEvent):
    pass


class GroupMembersChangedNoticeEvent(NoticeEvent):
    pass


class GroupRemovedNoticeEvent(NoticeEvent):
    pass


_MESSAGES = {
    "message_from_bot_subscriber": PrivateMessageEvent,
    "new_message_received_from_group_chat": GroupMessageEvent,
    "new_mentioned_message_received_from_group_chat": GroupMessageEvent,
    "new_message_received_from_thread": ThreadMessageEvent,
}
_NOTICES = {
    "user_enter_chatroom_with_bot": ChatEntryNoticeEvent,
    "bot_added_to_group_chat": BotAddedNoticeEvent,
    "bot_removed_from_group_chat": BotRemovedNoticeEvent,
    "group_chat_converted_to_external_group": GroupConvertedNoticeEvent,
    "interactive_message_click": InteractiveMessageClickEvent,
}
_MUTATIONS = {
    "edit": MessageEditedNoticeEvent,
    "recall_msgs": MessageRecalledNoticeEvent,
    "change_members": GroupMembersChangedNoticeEvent,
    "group_removed": GroupRemovedNoticeEvent,
}


def _object(value: Any, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise InvalidEvent(f"{field} must be an object")
    return value


def _identifier(value: Any) -> str:
    return "" if value is None else str(value)


def parse_event(data: dict[str, Any], *, app_id: str, callback_id: str = "") -> Event:
    data = _object(data, "event envelope")
    name = data.get("event_type")
    if not isinstance(name, str) or not name:
        raise InvalidEvent("event_type must be a nonempty string")
    if data.get("app_id") and str(data["app_id"]) != app_id:
        raise InvalidEvent("event.app_id does not match the configured application")
    detail = _object(data.get("event"), "event")
    fields: dict[str, Any] = dict(
        app_id=app_id,
        event_id=_identifier(data.get("event_id")),
        event_type=name,
        callback_id=callback_id,
        raw_event=deepcopy(data),
        timestamp=data.get("timestamp", 0),
    )
    if name in _MESSAGES:
        kind = _MESSAGES[name]
        private = kind is PrivateMessageEvent
        payload = _object(detail.get("message"), "event.message")
        actor = detail if private else _object(payload.get("sender", {}), "message.sender")
        fields.update(
            employee_code=_identifier(actor.get("employee_code")),
            seatalk_id=_identifier(actor.get("seatalk_id")),
            group_id=None if private else _identifier(detail.get("group_id")),
            thread_id=_identifier(payload.get("thread_id")) or None,
            message_id=_identifier(payload.get("message_id")) or None,
        )
        if not private and not fields["group_id"]:
            raise InvalidEvent("group message requires group_id")
        if kind is ThreadMessageEvent and not fields["thread_id"]:
            raise InvalidEvent("thread message requires thread_id")
        tag = payload.get("tag")
        if not isinstance(tag, str) or not tag:
            raise InvalidEvent("message.tag must be a nonempty string")
        if tag in _MUTATIONS:
            kind = _MUTATIONS[tag]
        else:
            message = parse_message(payload, group=not private)
            explicit = name == "new_mentioned_message_received_from_group_chat"
            fields.update(
                message=message,
                original_message=message.copy(),
                quoted_message_id=_identifier(payload.get("quoted_message_id")) or None,
                explicit_mention=explicit,
                to_me=private or explicit,
            )
    else:
        kind = _NOTICES.get(name, NoticeEvent)
        actor = detail
        if name == "bot_added_to_group_chat":
            actor = _object(detail.get("inviter", {}), "event.inviter")
        elif name == "bot_removed_from_group_chat":
            actor = _object(detail.get("remover", {}), "event.remover")
        elif name == "group_chat_converted_to_external_group":
            actor = _object(detail.get("operator", {}), "event.operator")
        group = detail.get("group", {})
        fields.update(
            employee_code=_identifier(actor.get("employee_code")),
            seatalk_id=_identifier(actor.get("seatalk_id")),
            group_id=_identifier(
                detail.get("group_id")
                or (group.get("group_id") if isinstance(group, dict) else None)
            )
            or None,
            thread_id=_identifier(detail.get("thread_id")) or None,
            message_id=_identifier(detail.get("message_id")) or None,
        )
        if kind is InteractiveMessageClickEvent:
            fields["value"] = _identifier(detail.get("value"))
    try:
        return kind(**fields)
    except (ValueError, TypeError) as exc:
        raise InvalidEvent(f"Invalid fields for event type {name}") from exc
