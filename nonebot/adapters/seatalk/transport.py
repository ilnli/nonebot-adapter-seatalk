import asyncio
import json
import math
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from time import monotonic
from typing import Any
from uuid import uuid4

from nonebot.drivers import WebSocket
from nonebot.utils import logger_wrapper

from .config import BotConfig
from .exception import NetworkError, SeaTalkAdapterException

log = logger_wrapper("SeaTalk")
REGISTER_TIMEOUT = 15.0
WRITE_TIMEOUT = 10.0


class RegistrationRejected(SeaTalkAdapterException):
    pass


class SessionKicked(SeaTalkAdapterException):
    pass


@dataclass(frozen=True)
class Registration:
    app_id: str
    sid: str
    heartbeat_interval: float
    heartbeat_timeout: float


def _positive(value: Any, fallback: float) -> float:
    try:
        number = float(value)
    except (ValueError, TypeError):
        return fallback
    return number if math.isfinite(number) and number > 0 else fallback


class WebSocketSession:
    def __init__(self, ws: WebSocket, config: BotConfig) -> None:
        self.ws = ws
        self.config = config
        self._token = ""
        self._write_lock = asyncio.Lock()
        self._registration: Registration | None = None
        self._pending_ping: float | None = None

    async def _send(self, command: str, **header: str) -> None:
        frame = {"cmd": command, "header": {"rid": uuid4().hex, **header}}
        try:
            async with self._write_lock:
                await asyncio.wait_for(self.ws.send(json.dumps(frame)), WRITE_TIMEOUT)
        except Exception as exc:
            raise NetworkError(f"WebSocket {command} failed") from exc

    async def register(self) -> Registration:
        async def handshake() -> Registration:
            await self._send(
                "register",
                app_id=self.config.app_id,
                app_secret=self.config.app_secret.get_secret_value(),
            )
            frame = json.loads(await self.ws.receive())
            if not isinstance(frame, dict) or frame.get("cmd") != "register":
                raise RegistrationRejected("Expected a registration response")
            header = frame.get("header") or {}
            if not isinstance(header, dict):
                raise RegistrationRejected("Invalid registration header")
            if frame.get("code", 0) != 0:
                raise RegistrationRejected(f"Registration rejected: {frame.get('message', '')}")
            token = header.get("token")
            if not isinstance(token, str) or not token:
                raise RegistrationRejected("Registration returned an empty token")
            if header.get("app_id") and str(header["app_id"]) != self.config.app_id:
                raise RegistrationRejected("Registration application ID mismatch")
            settings = frame.get("data") or {}
            if not isinstance(settings, dict):
                raise RegistrationRejected("Invalid registration settings")
            interval = _positive(settings.get("heartbeat_interval"), 15.0)
            timeout = _positive(settings.get("heartbeat_timeout"), 2 * interval)
            self._token = token
            self._registration = Registration(
                self.config.app_id, str(header.get("sid", "")), interval, timeout
            )
            return self._registration

        try:
            return await asyncio.wait_for(handshake(), REGISTER_TIMEOUT)
        except BaseException as exc:
            await self.close()
            if isinstance(exc, (asyncio.CancelledError, RegistrationRejected)):
                raise
            raise NetworkError("WebSocket registration failed") from exc

    async def ack(self, callback_id: str) -> None:
        if not self._token:
            raise NetworkError("WebSocket session is not registered")
        if not callback_id:
            raise ValueError("callback_id must not be empty")
        await self._send("ack", token=self._token, callback_id=callback_id)

    async def _heartbeat(self) -> None:
        assert self._registration is not None
        interval = self._registration.heartbeat_interval
        timeout = self._registration.heartbeat_timeout
        next_ping = monotonic() + interval
        while True:
            now = monotonic()
            deadline = self._pending_ping + timeout if self._pending_ping is not None else next_ping
            await asyncio.sleep(max(0, min(next_ping, deadline) - now))
            now = monotonic()
            if self._pending_ping is not None and now >= self._pending_ping + timeout:
                raise NetworkError("WebSocket heartbeat timed out")
            if now >= next_ping:
                if self._pending_ping is None:
                    self._pending_ping = now
                await self._send("ping", token=self._token)
                next_ping = monotonic() + interval

    async def _receive(self, on_event: Callable[[dict[str, Any]], Awaitable[None]]) -> None:
        while True:
            try:
                raw = await self.ws.receive()
            except Exception as exc:
                raise NetworkError("WebSocket connection closed") from exc
            try:
                envelope = json.loads(raw)
                if not isinstance(envelope, dict) or not isinstance(envelope.get("cmd"), str):
                    raise ValueError("Missing command")
            except (ValueError, TypeError):
                log("WARNING", f"Invalid WebSocket envelope for app {self.config.app_id}")
                continue
            command = envelope["cmd"]
            if command == "pong":
                self._pending_ping = None
            elif command == "kick":
                raise SessionKicked(str(envelope.get("message", "Session kicked")))
            elif command == "event":
                await on_event(envelope)

    async def run(self, on_event: Callable[[dict[str, Any]], Awaitable[None]]) -> None:
        if self._registration is None or not self._token:
            raise NetworkError("WebSocket session is not registered")
        tasks = [
            asyncio.create_task(self._receive(on_event)),
            asyncio.create_task(self._heartbeat()),
        ]
        try:
            done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            for task in done:
                task.result()
        finally:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            await self.close()

    async def close(self) -> None:
        self._token = ""
        self._pending_ping = None
        self._registration = None
        if not self.ws.closed:
            try:
                await asyncio.wait_for(self.ws.close(), WRITE_TIMEOUT)
            except Exception:
                log("WARNING", f"WebSocket close failed for app {self.config.app_id}")
