"""Resolve outgoing images without sharing API credentials with media servers."""

import asyncio
import base64
import binascii
import re
from collections.abc import Awaitable, Callable
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import url2pathname

from nonebot.drivers import Request, Response

from .exception import NetworkError, UnsupportedMessage
from .message import MessageSegment

# Official API: maximum 5 MB after base64 encoding; use decimal MB conservatively.
MAX_IMAGE_BASE64_SIZE = 5_000_000
MAX_IMAGE_BYTES = (MAX_IMAGE_BASE64_SIZE // 4) * 3


def _validate(raw: bytes) -> str:
    if not raw or len(raw) > MAX_IMAGE_BYTES:
        raise UnsupportedMessage("image base64 content must be nonempty and at most 5 MB")
    if not (
        raw.startswith(b"\x89PNG\r\n\x1a\n")
        or raw.startswith(b"\xff\xd8\xff")
        or raw.startswith((b"GIF87a", b"GIF89a"))
    ):
        raise UnsupportedMessage("images must contain PNG, JPEG or GIF data")
    encoded = base64.b64encode(raw).decode("ascii")
    if len(encoded) > MAX_IMAGE_BASE64_SIZE:
        raise UnsupportedMessage("image base64 content must be at most 5 MB (5,000,000 bytes)")
    return encoded


def _read_file(path: Path) -> bytes:
    try:
        with path.open("rb") as stream:
            return stream.read(MAX_IMAGE_BYTES + 1)
    except OSError as error:
        raise UnsupportedMessage("image file could not be read") from error


async def encode_image(
    segment: MessageSegment,
    request: Callable[[Request], Awaitable[Response]],
    timeout: float | None,
) -> str:
    if segment.data.get("requires_auth"):
        raise UnsupportedMessage(
            "forwarding authenticated SeaTalk media URLs is unsupported; provide image bytes"
        )
    source = segment.data.get("url", segment.data.get("content"))
    if isinstance(source, bytes):
        return _validate(source)
    if isinstance(source, Path):
        return _validate(await asyncio.to_thread(_read_file, source))
    if not isinstance(source, str) or not source:
        raise UnsupportedMessage("image requires bytes, a local path, base64 or an HTTP URL")
    if source.startswith(("base64://", "data:")):
        if source.startswith("base64://"):
            encoded = source[len("base64://") :]
        else:
            match = re.fullmatch(r"data:image/(?:png|jpeg|gif);base64,(.*)", source, re.DOTALL)
            if not match:
                raise UnsupportedMessage("image data URI must use PNG, JPEG or GIF base64")
            encoded = match[1]
        if len(encoded) > MAX_IMAGE_BASE64_SIZE:
            raise UnsupportedMessage("image base64 content must be at most 5 MB (5,000,000 bytes)")
        try:
            raw = base64.b64decode(encoded, validate=True)
        except (binascii.Error, ValueError) as error:
            raise UnsupportedMessage("invalid image base64 content") from error
        return _validate(raw)
    parsed = urlsplit(source)
    if parsed.scheme in {"http", "https"}:
        if not parsed.hostname or parsed.username or parsed.password:
            raise UnsupportedMessage("image URL must have a host and no embedded credentials")
        try:
            response = await request(Request("GET", source, timeout=timeout))
        except Exception as error:
            raise NetworkError("image download failed") from error
        if response.status_code != 200:
            raise NetworkError(f"image download returned HTTP {response.status_code}")
        if not isinstance(response.content, bytes):
            raise UnsupportedMessage("image download did not return binary image data")
        return _validate(response.content)
    if parsed.scheme == "file":
        if parsed.netloc not in {"", "localhost"} or parsed.query or parsed.fragment:
            raise UnsupportedMessage("image file URI must refer to a local file")
        source = url2pathname(parsed.path)
    elif parsed.scheme and not re.match(r"^[a-zA-Z]:[\\/]", source):
        raise UnsupportedMessage("unsupported image source scheme")
    return _validate(await asyncio.to_thread(_read_file, Path(source)))
