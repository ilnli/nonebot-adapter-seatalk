from dataclasses import dataclass
from typing import Any, Literal


@dataclass(frozen=True)
class Destination:
    kind: Literal["private", "group"]
    id: str
    thread_id: str | None = None


@dataclass(frozen=True)
class SendResult:
    message_id: str | None
    destination: Destination
    thread_id: str | None
    raw_response: dict[str, Any]
