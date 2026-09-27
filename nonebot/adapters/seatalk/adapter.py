import asyncio
from collections import OrderedDict
from dataclasses import dataclass, field
from time import monotonic
from typing import Any

from nonebot.compat import model_dump, type_validate_python
from nonebot.drivers import Driver, HTTPClientMixin, Request, WebSocketClientMixin
from nonebot.utils import escape_tag, logger_wrapper

from nonebot.adapters import Adapter as BaseAdapter

from .bot import Bot
from .config import Config
from .event import Event, parse_event
from .exception import ApiNotAvailable, EventCapacityExceeded, InvalidEvent
from .transport import RegistrationRejected, SessionKicked, WebSocketSession

log = logger_wrapper("SeaTalk")
RECONNECT_INITIAL = 1.0
RECONNECT_MAX = 30.0
RECONNECT_RESET = 60.0
SHUTDOWN_GRACE = 10.0
ADMISSION_LIMIT = 128
DEDUP_LIMIT = 4096
DEDUP_TTL = 600.0


@dataclass
class _BotState:
    tasks: set[asyncio.Task[None]] = field(default_factory=set)
    pending: set[str] = field(default_factory=set)
    completed: OrderedDict[str, float] = field(default_factory=OrderedDict)


class Adapter(BaseAdapter):
    def __init__(self, driver: Driver, **kwargs: Any) -> None:
        super().__init__(driver, **kwargs)
        if not isinstance(driver, WebSocketClientMixin) or not isinstance(driver, HTTPClientMixin):
            raise RuntimeError("SeaTalk requires WebSocketClientMixin and HTTPClientMixin drivers")
        self.seatalk_config = type_validate_python(Config, model_dump(self.config))
        self._states: dict[str, _BotState] = {}
        self._supervisors: set[asyncio.Task[None]] = set()
        self._stopping = False
        driver.on_startup(self._startup)
        driver.on_shutdown(self._shutdown)

    @classmethod
    def get_name(cls) -> str:
        return "SeaTalk"

    async def _startup(self) -> None:
        self._stopping = False
        for config in self.seatalk_config.seatalk_bots:
            bot = Bot(self, config)
            self._supervisors.add(asyncio.create_task(self._supervise(bot)))

    async def _supervise(self, bot: Bot) -> None:
        delay = RECONNECT_INITIAL
        while not self._stopping:
            connected_at: float | None = None
            session: WebSocketSession | None = None
            connected = False
            try:
                async with self.websocket(Request("GET", bot.bot_config.ws_url, timeout=15)) as ws:
                    if self._stopping:
                        return
                    session = WebSocketSession(ws, bot.bot_config)
                    await session.register()
                    # Python 3.10 wait_for may finish the handshake concurrently
                    # with cancellation. Never start receiving after shutdown.
                    if self._stopping:
                        return
                    self.bot_connect(bot)
                    connected = True
                    connected_at = monotonic()

                    async def receive(envelope: dict[str, Any]) -> None:
                        assert session is not None
                        await self._on_envelope(bot, session, envelope)

                    await session.run(receive)
            except (RegistrationRejected, SessionKicked) as exc:
                log("ERROR", f"Bot {escape_tag(bot.self_id)} stopped: {escape_tag(str(exc))}")
                return
            except Exception as exc:
                log(
                    "WARNING",
                    f"Bot {escape_tag(bot.self_id)} reconnecting after {type(exc).__name__}",
                )
            finally:
                if session is not None:
                    await session.close()
                if connected:
                    self.bot_disconnect(bot)
            if connected_at is not None and monotonic() - connected_at >= RECONNECT_RESET:
                delay = RECONNECT_INITIAL
            if not self._stopping:
                await asyncio.sleep(delay)
                delay = min(delay * 2, RECONNECT_MAX)

    async def _on_envelope(
        self, bot: Bot, session: WebSocketSession, envelope: dict[str, Any]
    ) -> None:
        header = envelope.get("header") or {}
        try:
            if not isinstance(header, dict):
                raise InvalidEvent("header must be an object")
            if header.get("app_id") and str(header["app_id"]) != bot.self_id:
                raise InvalidEvent("header.app_id does not match the configured application")
            callback_id = str(header.get("callback_id") or "")
            event = parse_event(envelope.get("data"), app_id=bot.self_id, callback_id=callback_id)
        except InvalidEvent as exc:
            log(
                "WARNING",
                f"Rejected event for app {escape_tag(bot.self_id)}: {escape_tag(str(exc))}",
            )
            return
        if self._admit_event(bot, event) and event.callback_id:
            await session.ack(event.callback_id)

    def _admit_event(self, bot: Bot, event: Event) -> bool:
        if self._stopping:
            return False
        state = self._states.setdefault(bot.self_id, _BotState())
        key = event.event_id or event.callback_id
        now = monotonic()
        while state.completed and now - next(iter(state.completed.values())) >= DEDUP_TTL:
            state.completed.popitem(last=False)
        if key and (key in state.pending or key in state.completed):
            return True
        if len(state.tasks) >= ADMISSION_LIMIT:
            raise EventCapacityExceeded("Event admission capacity exceeded")
        if key:
            state.pending.add(key)
        task = asyncio.create_task(bot.handle_event(event))
        state.tasks.add(task)

        def completed(task: asyncio.Task[None]) -> None:
            state.tasks.discard(task)
            if key:
                state.pending.discard(key)
                state.completed[key] = monotonic()
                while len(state.completed) > DEDUP_LIMIT:
                    state.completed.popitem(last=False)
            if not task.cancelled() and (error := task.exception()) is not None:
                log(
                    "ERROR",
                    f"Event {escape_tag(event.event_id)} for app {escape_tag(bot.self_id)} "
                    f"failed: {type(error).__name__}",
                )

        task.add_done_callback(completed)
        return True

    async def _shutdown(self) -> None:
        self._stopping = True
        for task in self._supervisors:
            task.cancel()
        await asyncio.gather(*self._supervisors, return_exceptions=True)
        pending = {task for state in self._states.values() for task in state.tasks}
        if pending:
            _, remaining = await asyncio.wait(pending, timeout=SHUTDOWN_GRACE)
            for task in remaining:
                task.cancel()
            await asyncio.gather(*remaining, return_exceptions=True)

    async def _call_api(self, bot: Bot, api: str, **data: Any) -> Any:
        raise ApiNotAvailable(f"SeaTalk API {api} is not available")
