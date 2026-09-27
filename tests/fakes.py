import asyncio
import json
from contextlib import asynccontextmanager

from nonebot.config import Config, Env
from nonebot.drivers import HTTPClientMixin, Request, WebSocket, WebSocketClientMixin
from nonebot.drivers.none import Driver
from nonebot.exception import WebSocketClosed


class FakeWebSocket(WebSocket):
    def __init__(self):
        super().__init__(request=Request("GET", "wss://ws.example"))
        self.incoming = asyncio.Queue()
        self.sent = []
        self._closed = False
        self.changed = asyncio.Event()
        self.fail_next_send = None
        self.writing = False

    @property
    def closed(self):
        return self._closed

    async def accept(self):
        pass

    async def close(self, code=1000, reason=""):
        self._closed = True
        self.incoming.put_nowait(WebSocketClosed(code, reason))

    def push(self, envelope):
        self.incoming.put_nowait(json.dumps(envelope))

    async def receive(self):
        value = await self.incoming.get()
        if isinstance(value, Exception):
            raise value
        return value

    async def receive_text(self):
        return await self.receive()

    async def receive_bytes(self):
        return (await self.receive()).encode()

    async def send(self, data):
        assert not self.writing, "concurrent websocket writes"
        self.writing = True
        try:
            await asyncio.sleep(0)
            if self.fail_next_send:
                error, self.fail_next_send = self.fail_next_send, None
                raise error
            self.sent.append(json.loads(data))
            self.changed.set()
        finally:
            self.writing = False

    async def send_text(self, data):
        await self.send(data)

    async def send_bytes(self, data):
        await self.send(data)

    async def wait_sent(self, command):
        async def wait():
            while True:
                self.changed.clear()
                for frame in reversed(self.sent):
                    if frame["cmd"] == command:
                        return frame
                await self.changed.wait()

        return await asyncio.wait_for(wait(), 1)


class FakeDriver(Driver, HTTPClientMixin, WebSocketClientMixin):
    def __init__(self, bots):
        super().__init__(Env(), Config(_env_file=None, seatalk_bots=bots, nickname={"bot"}))
        self.peers = asyncio.Queue()
        self.connections = []
        self.notifications = []
        self.http_requests = []

    @asynccontextmanager
    async def websocket(self, setup):
        self.connections.append(setup)
        peer = await self.peers.get()
        if isinstance(peer, Exception):
            raise peer
        try:
            yield peer
        finally:
            await peer.close()

    async def request(self, setup):
        self.http_requests.append(setup)
        raise AssertionError("Unexpected HTTP request")

    async def stream_request(self, setup, *, chunk_size=1024):
        raise AssertionError("Unexpected streaming request")
        yield

    def get_session(self, *args, **kwargs):
        raise AssertionError("Unexpected HTTP session")

    def _bot_connect(self, bot):
        super()._bot_connect(bot)
        self.notifications.append(("connected", bot.self_id))

    def _bot_disconnect(self, bot):
        super()._bot_disconnect(bot)
        self.notifications.append(("disconnected", bot.self_id))
