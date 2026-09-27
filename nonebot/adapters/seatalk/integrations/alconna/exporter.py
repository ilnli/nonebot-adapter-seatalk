import re
from collections.abc import Sequence
from typing import Any

from nonebot_plugin_alconna.uniseg.constraint import SerializeFailed
from nonebot_plugin_alconna.uniseg.exporter import MessageExporter
from nonebot_plugin_alconna.uniseg.exporter import export as export_segment
from nonebot_plugin_alconna.uniseg.fallback import FallbackStrategy
from nonebot_plugin_alconna.uniseg.segment import At, Reply, Segment, Text
from nonebot_plugin_alconna.uniseg.target import Target

from ...bot import Bot, resolve_destination
from ...event import Event
from ...exception import InvalidEvent, UnsupportedMessage
from ...message import Message, MessageSegment
from ...models import SendResult
from . import SeaTalkAdapter


class SeaTalkMessageExporter(MessageExporter[Message]):
    @classmethod
    def get_adapter(cls):
        return SeaTalkAdapter.seatalk

    def get_message_type(self):
        return Message

    def get_message_id(self, event: Event) -> str:
        if not event.message_id:
            raise SerializeFailed("SeaTalk event has no message ID")
        return event.message_id

    def get_target(self, event: Event, bot: Bot | None = None) -> Target:
        try:
            destination = resolve_destination(event)
        except InvalidEvent as error:
            raise SerializeFailed(str(error)) from error
        return Target(
            destination.id,
            private=destination.kind == "private",
            adapter="SeaTalk",
            self_id=bot.self_id if bot else None,
            extra={"thread_id": destination.thread_id},
        )

    async def export(
        self, source: Sequence[Segment], bot: Bot | None, fallback: bool | FallbackStrategy
    ) -> Message:
        # UniMessage.export catches SerializeFailed and stringifies the entire
        # message with fallback enabled. Native UnsupportedMessage must escape it.
        for segment in source:
            if type(segment) not in {Text, At, Reply} or segment.children:
                raise UnsupportedMessage(f"cannot export universal {segment.type} to SeaTalk text")
            if isinstance(segment, At) and (
                segment.flag != "user"
                or not re.fullmatch(r"seatalk:[0-9]+", segment.target)
                or int(segment.target.split(":")[1]) == 0
            ):
                raise UnsupportedMessage("mentions require a seatalk:<numeric-id> user")
        return await super().export(source, bot, fallback)

    @export_segment
    async def text(self, seg: Text, bot: Bot | None) -> MessageSegment:
        return MessageSegment.text(seg.text)

    @export_segment
    async def at(self, seg: At, bot: Bot | None) -> MessageSegment:
        return MessageSegment.at(seg.target.removeprefix("seatalk:"), id_type="seatalk_id")

    @export_segment
    async def reply(self, seg: Reply, bot: Bot | None) -> MessageSegment:
        return MessageSegment.reply(seg.id)

    async def send_to(
        self, target: Target | Event, bot: Bot, message: Message, **kwargs: Any
    ) -> SendResult:
        if not isinstance(message, Message):
            raise UnsupportedMessage("SeaTalk requires a native message, not a fallback message")
        if isinstance(target, Event):
            return await bot.send(target, message, **kwargs)
        if target.channel or target.parent_id:
            raise UnsupportedMessage("SeaTalk does not support channel targets")
        if target.extra.get("adapter", "SeaTalk") != "SeaTalk" or (
            target.self_id and target.self_id != bot.self_id
        ):
            raise UnsupportedMessage("target does not match this SeaTalk bot")
        if target.private and target.id.startswith("seatalk:"):
            raise UnsupportedMessage("private targets require employee codes")
        thread = target.extra.get("thread_id")
        if "thread_id" in kwargs:
            raise TypeError("put thread_id in Target.extra")
        send = bot.send_private_message if target.private else bot.send_group_message
        return await send(target.id, message, thread_id=thread, **kwargs)

    def get_reply(self, result: SendResult) -> Reply:
        if not result.message_id:
            raise SerializeFailed("SeaTalk did not return a message ID")
        return Reply(result.message_id)
