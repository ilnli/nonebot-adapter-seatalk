# NoneBot2 SeaTalk adapter

Development implementation of a SeaTalk application-bot adapter for NoneBot2.

**Current status: receiving core implemented; sending and Alconna integration are not complete.**

The adapter implements the WebSocket protocol described by the supplied SDK, using
NoneBot's asynchronous drivers. It does not require or redistribute that SDK.

## Implemented

- Application registration, heartbeat/pong handling, reconnection, and shutdown.
- Private, group, mentioned-group, and thread events, plus typed notices.
- NoneBot message/event interfaces, isolated sessions, command matching, and nickname handling.
- Bounded event admission and duplicate callback suppression.
- Preservation of incoming images, files, video, cards, forwarded content, and unknown payloads.

SeaTalk's HTTP documentation could not be retrieved without authentication.
The [contract evidence](docs/references/seatalk-contracts.md) lists the facts still
needed before token management and sending can be implemented. `Bot.send` and
API calls currently raise `ApiNotAvailable`. Incoming mention metadata is preserved
without guessing its offset units. Alconna is not yet an advertised capability.

## Try receiving events

Python 3.10+ is targeted. Install a built wheel together with NoneBot's client drivers:

```sh
uv build
python -m pip install dist/nonebot_adapter_seatalk-0.1.0-py3-none-any.whl 'nonebot2[httpx,websockets]>=2.4,<3'
```

Copy `examples/.env.example` to `.env`, replace the placeholders for your test app,
and run `python examples/bot.py` from the repository root. The example logs event
identifiers; it does not attempt replies. Never commit your `.env`.

The driver must support both HTTP and WebSocket clients. No public callback server
is required. `seatalk_bots` is a JSON list of applications:

| Setting | Meaning |
| --- | --- |
| `app_id` | Application ID; also the NoneBot bot ID |
| `app_secret` | Application secret |
| `ws_url` | Defaults to the SDK endpoint `wss://ws-openapi.haiserve.com/ws/bot` |
| `api_base` | Required HTTPS URL for the matching HTTP environment; not yet used for sending |
| `bot_seatalk_id` | Optional SeaTalk identity for self-message and mention detection; distinct from `app_id` |

Enable the appropriate event subscriptions and permissions for your test app in
SeaTalk. The HTTP/WS environment pairing and exact platform permission names still
require verification. The two service URLs are separately configurable.

## Message behavior and delivery

Private messages and explicit mentioned-group events are addressed to the bot.
Recognized leading nicknames/native self-mention segments are removed from the
working message for command parsing; `original_message` remains available.
Platform mention spans currently stay as text and metadata until their encoding is
verified. Edits, recalls, membership changes, and interactive clicks are notices,
so they do not rerun normal message commands.

Nontext messages remain typed segments. Media content is preserved as received;
the adapter does not download, upload, or send media. Unknown events and payloads
remain accessible through `raw_event` and raw segments.

The adapter acknowledges an event when it accepts it for local processing. It
allows 128 unfinished event tasks per bot. Duplicates are suppressed while pending,
then for up to ten minutes in a 4,096-entry cache. Caches survive connection
replacement but not a process restart. A crash after acknowledgement can lose
unfinished work, and plugin failures are not automatically replayed. Capacity
exhaustion closes the connection without acknowledging the new event; server
redelivery is not guaranteed by this implementation.

Network failures reconnect with a delay from one to thirty seconds. An explicit
registration rejection or kick stops that bot until an operator corrects the
configuration and restarts. Logs identify applications and event IDs; adapter event
descriptions avoid message content. NoneBot and plugins control their own logging.

## Development and verification

```sh
uv sync --group dev
uv run pytest -q
uv run ruff check nonebot tests examples
uv run ruff format --check nonebot tests examples
```

Like other NoneBot adapters, source tests extend the adapter search path because
NoneBot itself is a regular package. Set `SEATALK_TEST_INSTALLED=1` to disable that
hook for clean installed-wheel tests. Set `SEATALK_TEST_WHEEL` to a built wheel path
to enable artifact-content checks.

This implementation has not been live-verified against a SeaTalk application.
See the [design](docs/superpowers/specs/2026-09-27-seatalk-adapter-design.md) and
[implementation plan](docs/superpowers/plans/2026-09-27-seatalk-adapter.md) for the
remaining sending, Unicode mention, Alconna, and release acceptance work.
