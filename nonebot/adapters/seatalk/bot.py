import re
from typing import TYPE_CHECKING, Any

from nonebot.message import handle_event

from nonebot.adapters import Bot as BaseBot

from .config import BotConfig
from .event import Event, MessageEvent
from .exception import ApiNotAvailable
from .message import Message, MessageSegment
from .models import SendResult

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
        raise ApiNotAvailable("HTTP sending awaits verified SeaTalk API contracts")
