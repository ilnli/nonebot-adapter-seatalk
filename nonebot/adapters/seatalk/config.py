from typing import Literal
from urllib.parse import urlsplit

from nonebot.compat import PYDANTIC_V2
from pydantic import BaseModel, Field, SecretStr

if PYDANTIC_V2:
    from pydantic import field_validator
else:
    from pydantic import validator as field_validator

DEFAULT_WS_URL = "wss://ws-openapi.haiserve.com/ws/bot"


class BotConfig(BaseModel):
    app_id: str = Field(min_length=1)
    app_secret: SecretStr
    api_base: str = "https://openapi.seatalk.io"
    ws_url: str = DEFAULT_WS_URL
    bot_seatalk_id: str | None = None
    reply_mode: Literal["thread", "quote"] = "thread"

    @field_validator("app_id")
    @classmethod
    def nonempty_id(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("app_id must not be blank")
        return value

    @field_validator("app_secret")
    @classmethod
    def nonempty_secret(cls, value: SecretStr) -> SecretStr:
        if not value.get_secret_value():
            raise ValueError("app_secret must not be empty")
        return value

    @field_validator("api_base")
    @classmethod
    def https_base(cls, value: str) -> str:
        url = urlsplit(value)
        if url.scheme != "https" or not url.hostname or url.username or url.query or url.fragment:
            raise ValueError("api_base must be an HTTPS URL without credentials, query or fragment")
        return value.rstrip("/")

    @field_validator("ws_url")
    @classmethod
    def websocket_url(cls, value: str) -> str:
        url = urlsplit(value)
        if url.scheme not in {"ws", "wss"} or not url.hostname or url.username or url.fragment:
            raise ValueError("ws_url must be a ws/wss URL without credentials or fragment")
        return value


class Config(BaseModel):
    seatalk_bots: list[BotConfig] = Field(default_factory=list)

    @field_validator("seatalk_bots")
    @classmethod
    def unique_app_ids(cls, value: list[BotConfig]) -> list[BotConfig]:
        if len({bot.app_id for bot in value}) != len(value):
            raise ValueError("seatalk_bots contains duplicate app_id values")
        return value
