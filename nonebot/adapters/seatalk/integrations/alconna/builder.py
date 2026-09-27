from nonebot_plugin_alconna.uniseg.builder import MessageBuilder, build
from nonebot_plugin_alconna.uniseg.segment import At, File, Image, Reply, Video

from ...event import MessageEvent
from ...message import MessageSegment
from . import SeaTalkAdapter


class SeaTalkMessageBuilder(MessageBuilder[MessageSegment]):
    @classmethod
    def get_adapter(cls):
        return SeaTalkAdapter.seatalk

    @build("at")
    def at(self, seg: MessageSegment):
        identity = seg.data["user_id"]
        if seg.data["id_type"] == "seatalk_id":
            identity = "seatalk:" + identity
        return At("user", identity, display=seg.data.get("display"))

    @build("reply")
    def reply(self, seg: MessageSegment):
        return Reply(seg.data["message_id"])

    @build("image", "file", "video")
    def media(self, seg: MessageSegment):
        factory = {"image": Image, "file": File, "video": Video}[seg.type]
        data = {"url": seg.data.get("url") or seg.data.get("content")}
        if seg.data.get("name"):
            data["name"] = seg.data["name"]
        return factory(**data)

    async def extract_reply(self, event, bot):
        if isinstance(event, MessageEvent) and event.quoted_message_id:
            return Reply(event.quoted_message_id)
        return None
