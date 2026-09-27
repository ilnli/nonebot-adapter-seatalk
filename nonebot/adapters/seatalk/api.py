import asyncio
import json as jsonlib
from collections.abc import Awaitable, Callable
from time import time
from typing import Any
from urllib.parse import unquote, urlsplit

from nonebot.drivers import Request, Response

from .config import BotConfig
from .exception import ActionFailed, NetworkError
from .message import Message, serialize_message
from .models import Destination, SendResult


class APIClient:
    def __init__(
        self,
        config: BotConfig,
        request: Callable[[Request], Awaitable[Response]],
        *,
        timeout: float | None,
    ):
        self.config = config
        self._request = request
        self.timeout = timeout
        self._token = ""
        self._refresh_at = 0.0
        self._lock = asyncio.Lock()

    def _url(self, path: str) -> str:
        parsed = urlsplit(path)
        decoded = unquote(path)
        if (
            not path.startswith("/")
            or decoded.startswith("//")
            or parsed.scheme
            or parsed.netloc
            or parsed.fragment
            or "\\" in decoded
            or any(ord(c) < 32 for c in decoded)
        ):
            raise ValueError(
                "API path must be origin-relative without authority, fragment or controls"
            )
        return self.config.api_base.rstrip("/") + path

    async def _perform(self, request: Request, api: str) -> dict[str, Any]:
        try:
            response = await self._request(request)
        except Exception as error:
            raise NetworkError("SeaTalk HTTP transport failed") from error
        status = response.status_code
        if status == 401:
            raise ActionFailed(100, "HTTP authentication rejected", api=api)
        if status == 429:
            raise ActionFailed(
                101,
                "HTTP rate limit",
                api=api,
                retry_after=response.headers.get("Retry-After"),
                request_id=response.headers.get("X-Request-ID"),
            )
        if status != 200:
            raise NetworkError(f"SeaTalk HTTP response status {status}")
        try:
            body = jsonlib.loads(response.content or "")
        except (ValueError, TypeError) as error:
            raise NetworkError("SeaTalk HTTP response is not JSON") from error
        if not isinstance(body, dict) or type(body.get("code")) is not int:
            raise NetworkError("SeaTalk HTTP response has no integer code")
        if body["code"]:
            raise ActionFailed(
                body["code"],
                str(body.get("message", "")),
                api=api,
                request_id=response.headers.get("X-Request-ID"),
                retry_after=response.headers.get("Retry-After"),
            )
        return body

    async def _access_token(self) -> str:
        if self._token and time() < self._refresh_at:
            return self._token
        async with self._lock:
            if self._token and time() < self._refresh_at:
                return self._token
            path = "/auth/app_access_token"
            body = await self._perform(
                Request(
                    "POST",
                    self._url(path),
                    json={
                        "app_id": self.config.app_id,
                        "app_secret": self.config.app_secret.get_secret_value(),
                    },
                    headers={"Content-Type": "application/json"},
                    timeout=self.timeout,
                ),
                path,
            )
            token, expiry, now = body.get("app_access_token"), body.get("expire"), time()
            if not isinstance(token, str) or not token or type(expiry) is not int or expiry <= now:
                raise NetworkError("SeaTalk returned invalid token metadata")
            self._token = token
            self._refresh_at = expiry - min(60.0, (expiry - now) / 10)
            return token

    async def request_api(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        url = self._url(path)  # Validate origin before obtaining credentials.
        token = await self._access_token()
        try:
            return await self._perform(
                Request(
                    method,
                    url,
                    params=params,
                    json=json,
                    headers={
                        "Authorization": f"Bearer {token}",
                        "Content-Type": "application/json",
                    },
                    timeout=self.timeout,
                ),
                path,
            )
        except ActionFailed as error:
            if error.code == 100 and self._token == token:
                self._token, self._refresh_at = "", 0.0
            raise

    async def send_message(
        self, destination: Destination, message: Message, *, quote_id: str | None = None
    ) -> SendResult:
        body = serialize_message(message, destination, quote_id=quote_id)
        path = "/messaging/v2/" + ("group_chat" if destination.kind == "group" else "single_chat")
        response = await self.request_api("POST", path, json=body)
        identity = response.get("message_id")
        if identity is not None and not isinstance(identity, str):
            raise NetworkError("SeaTalk returned an invalid message ID")
        return SendResult(identity or None, destination, destination.thread_id, response)
