from collections.abc import Iterable
from copy import deepcopy
from typing import Any, Literal

from nonebot.adapters import Message as BaseMessage
from nonebot.adapters import MessageSegment as BaseMessageSegment

from .exception import InvalidEvent


class MessageSegment(BaseMessageSegment["Message"]):
    @classmethod
    def get_message_class(cls) -> type["Message"]:
        return Message

    def __str__(self) -> str:
        return self.data["text"] if self.is_text() else f"[{self.type}]"

    def is_text(self) -> bool:
        return self.type == "text"

    @staticmethod
    def text(text: str) -> "MessageSegment":
        return MessageSegment("text", {"text": text})

    @staticmethod
    def at(
        user_id: str,
        *,
        id_type: Literal["employee_code", "seatalk_id"] = "employee_code",
        display: str | None = None,
    ) -> "MessageSegment":
        return MessageSegment("at", {"user_id": user_id, "id_type": id_type, "display": display})

    @staticmethod
    def reply(message_id: str) -> "MessageSegment":
        return MessageSegment("reply", {"message_id": message_id})

    @staticmethod
    def image(url: str) -> "MessageSegment":
        return MessageSegment("image", {"url": url})

    @staticmethod
    def file(url: str, name: str | None = None) -> "MessageSegment":
        return MessageSegment("file", {"url": url, "name": name})

    @staticmethod
    def video(url: str) -> "MessageSegment":
        return MessageSegment("video", {"url": url})

    @staticmethod
    def card(payload: dict[str, Any]) -> "MessageSegment":
        return MessageSegment("card", {"payload": deepcopy(payload)})

    @staticmethod
    def forward(payload: dict[str, Any]) -> "MessageSegment":
        return MessageSegment("forward", {"payload": deepcopy(payload)})

    @staticmethod
    def raw(tag: str, payload: dict[str, Any]) -> "MessageSegment":
        return MessageSegment("raw", {"tag": tag, "payload": deepcopy(payload)})


class Message(BaseMessage[MessageSegment]):
    @classmethod
    def get_segment_class(cls) -> type[MessageSegment]:
        return MessageSegment

    @staticmethod
    def _construct(msg: str) -> Iterable[MessageSegment]:
        yield MessageSegment.text(msg)


def parse_message(payload: dict[str, Any], *, group: bool) -> Message:
    tag = payload.get("tag")
    if not isinstance(tag, str) or not tag:
        raise InvalidEvent("message.tag must be a nonempty string")
    message = Message()
    if quoted := payload.get("quoted_message_id"):
        message.append(MessageSegment.reply(str(quoted)))
    body = payload.get(tag)
    if tag == "text":
        field = "plain_text" if group else "content"
        if not isinstance(body, dict) or not isinstance(body.get(field), str):
            raise InvalidEvent(f"message.text.{field} must be a string")
        segment = MessageSegment.text(body[field])
        if group and body.get("mentioned_list"):
            mentions = body["mentioned_list"]
            converted = _mapped_mentions(body[field], mentions)
            if converted is not None:
                message.extend(converted)
                return message
            segment.data["mentions"] = deepcopy(mentions)
    elif tag in {
        "image",
        "file",
        "video",
        "interactive_message",
        "combined_forwarded_chat_history",
    }:
        if not isinstance(body, dict):
            raise InvalidEvent(f"message.{tag} must be an object")
        kind = {"interactive_message": "card", "combined_forwarded_chat_history": "forward"}.get(
            tag, tag
        )
        segment = MessageSegment(kind, {"payload": deepcopy(body)})
        if tag in {"image", "file", "video"}:
            segment.data.update(content=body.get("content", ""), name=body.get("filename"))
    else:
        segment = MessageSegment.raw(tag, payload)
    message.append(segment)
    return message


def _mapped_mentions(text: str, mentions: Any) -> Message | None:
    # The official contract maps names, not offsets. Only unique literal spans
    # can be resolved without guessing UTF-8/UTF-16 units or which occurrence.
    if not isinstance(mentions, list):
        return None
    spans = []
    for actor in mentions:
        if not isinstance(actor, dict):
            return None
        name, identity = actor.get("username"), actor.get("seatalk_id")
        if not isinstance(name, str) or not name or not isinstance(identity, str) or not identity:
            return None
        literal = "@" + name
        if text.count(literal) != 1:
            return None
        start = text.index(literal)
        spans.append((start, start + len(literal), identity, name, actor))
    spans.sort(key=lambda span: span[0])
    result, end = Message(), 0
    for start, stop, identity, name, actor in spans:
        if start < end:
            return None
        if start > end:
            result.append(MessageSegment.text(text[end:start]))
        segment = MessageSegment.at(identity, id_type="seatalk_id", display=name)
        segment.data["mention"] = deepcopy(actor)
        result.append(segment)
        end = stop
    if end < len(text):
        result.append(MessageSegment.text(text[end:]))
    return result
