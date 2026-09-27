from nonebot import logger, on_message, on_notice
from nonebot.adapters.seatalk.event import Event

messages = on_message()
notices = on_notice()


@messages.handle()
@notices.handle()
async def observe(event: Event) -> None:
    logger.info("SeaTalk event type={} id={}", event.event_type, event.event_id)
