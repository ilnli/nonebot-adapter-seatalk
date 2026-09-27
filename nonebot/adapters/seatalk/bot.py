import re
from typing import TYPE_CHECKING, Any

from nonebot.message import handle_event

from nonebot.adapters import Bot as BaseBot

from .config import BotConfig
from .event import Event, MessageEvent
from .exception import InvalidEvent
from .message import Message, MessageSegment
from .models import Destination, SendResult

if TYPE_CHECKING:
    from .adapter import Adapter


class Bot(BaseBot):
    def __init__(self, adapter: "Adapter", config: BotConfig) -> None:
        super().__init__(adapter, config.app_id)
        self.bot_config = config

    async def handle_event(self, event: Event) -> None:
        if isinstance(event, MessageEvent):
            identity = self.bot_config.bot_seatalk_id
            if identity and event.seatalk_id == identity:
                return
            message = event.message
            if message and message[0].type == "reply":
                del message[0]
            start = 0
            for segment in message:
                if (
                    identity
                    and segment.type == "at"
                    and segment.data.get("id_type") == "seatalk_id"
                    and segment.data.get("user_id") == identity
                ):
                    event.to_me = True
                if identity and segment.type == "text":
                    mentions = segment.data.get("mentions", [])
                    if isinstance(mentions, list) and any(
                        isinstance(actor, dict) and str(actor.get("seatalk_id", "")) == identity
                        for actor in mentions
                    ):
                        event.to_me = True
            if start < len(message):
                first = message[start]
                if (
                    identity
                    and first.type == "at"
                    and first.data.get("id_type") == "seatalk_id"
                    and first.data.get("user_id") == identity
                ):
                    del message[start]
                    if start < len(message) and message[start].is_text():
                        message[start].data["text"] = message[start].data["text"].lstrip()
                elif first.is_text():
                    nicknames = sorted(self.config.nickname, key=len, reverse=True)
                    for nickname in nicknames:
                        if not nickname:
                            continue
                        match = re.match(
                            rf"^{re.escape(nickname)}(?:[\s,，:：]+|$)", first.data["text"], re.I
                        )
                        if match:
                            first.data["text"] = first.data["text"][match.end() :]
                            event.to_me = True
                            break
        await handle_event(self, event)

    async def send(
        self, event: Event, message: str | Message | MessageSegment, **kwargs: Any
    ) -> SendResult:
        if kwargs.keys() - {"quote_id"}:
            raise TypeError(
                "send accepts only quote_id; use an explicit send method for other targets"
            )
        destination = resolve_destination(event)
        if destination.kind == "group":
            return await self.send_group_message(
                destination.id, message, thread_id=destination.thread_id, **kwargs
            )
        return await self.send_private_message(
            destination.id, message, thread_id=destination.thread_id, **kwargs
        )

    async def send_private_message(
        self,
        employee_code: str,
        message: str | Message | MessageSegment,
        *,
        thread_id: str | None = None,
        quote_id: str | None = None,
    ) -> SendResult:
        return await self.call_api(
            "send_private_message",
            employee_code=employee_code,
            message=Message(message),
            thread_id=thread_id,
            quote_id=quote_id,
        )

    async def send_group_message(
        self,
        group_id: str,
        message: str | Message | MessageSegment,
        *,
        thread_id: str | None = None,
        quote_id: str | None = None,
    ) -> SendResult:
        return await self.call_api(
            "send_group_message",
            group_id=group_id,
            message=Message(message),
            thread_id=thread_id,
            quote_id=quote_id,
        )

    async def request_api(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return await self.call_api(
            "request_api", method=method, path=path, params=params, json=json
        )


def resolve_destination(event: Event) -> Destination:
    if event.group_id:
        return Destination("group", event.group_id, event.thread_id)
    if event.employee_code:
        return Destination("private", event.employee_code, event.thread_id)
    raise InvalidEvent("event has no group ID or private employee code")
