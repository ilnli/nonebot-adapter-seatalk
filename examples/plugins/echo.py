from nonebot.params import CommandArg

from nonebot import on_command
from nonebot.adapters.seatalk import Bot, Message
from nonebot.adapters.seatalk.event import MessageEvent

echo = on_command("echo", block=True)


@echo.handle()
async def handle_echo(bot: Bot, event: MessageEvent, args: Message = CommandArg()):
    await bot.send(event, args if args else "hello")
