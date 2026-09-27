# NoneBot2 SeaTalk adapter

SeaTalk application-bot adapter for NoneBot2, with WebSocket reception, HTTP text
replies, and an optional Alconna integration. Python 3.10+ and NoneBot 2.4+ are
supported; the Alconna extra requires NoneBot 2.5+. **Not live-verified.**

The supplied SDK is used as a protocol reference. No SDK source is redistributed
or required at runtime. See the [verified contracts](docs/references/seatalk-contracts.md).

## Install and configure

Build and install locally (this package has not been published):

```sh
uv build
python -m pip install dist/nonebot_adapter_seatalk-0.1.0-py3-none-any.whl 'nonebot2[httpx,websockets]>=2.4,<3'
```

Copy `examples/.env.example` to `.env`, replace the placeholders, then run
`python examples/bot.py` from the repository root. Send `/echo hello` privately,
mention the bot before the command in a group, or use a thread the bot follows.
The example sends a text reply. Keep `.env` out of version control.

The driver must support HTTP and WebSocket clients; no public callback server is
required. `SEATALK_BOTS` is a JSON list of applications:

| Setting | Meaning |
| --- | --- |
| `app_id` | Application ID, also the NoneBot bot ID; unique per configuration |
| `app_secret` | Application secret |
| `ws_url` | Default SDK endpoint: `wss://ws-openapi.haiserve.com/ws/bot` |
| `api_base` | Required matching HTTPS REST base; public docs use `https://openapi.seatalk.io` |
| `bot_seatalk_id` | Optional bot account ID from App → Bot → SeaTalk ID; distinct from `app_id` |

Confirm that your REST origin and WebSocket endpoint use the same app environment.
The public REST origin and supplied SDK's haiserve endpoint have not been tested
as a pair. Configure both explicitly when your environment requires different URLs.

Enable Bot capability, set the app Online, and grant **Send Message to Bot User**
and/or **Send Message to Group Chat**, with the applicable service scope. The bot
must belong to the destination group. Subscribe to private messages, mentioned
group messages, and thread messages as needed. Start the process, then select
WebSocket under Event Callback and use Re-verify while connected. Thread callbacks
require a thread the bot follows, for example after it is mentioned there.

## Messages and replies

```python
from nonebot.adapters.seatalk import Message, MessageSegment

# Reply in the event's private chat, group, or thread:
result = await bot.send(event, "hello")
# Quote a message in the same group/thread (opt-in):
await bot.send(event, "reply", quote_id=event.message_id)
# Proactive sends:
await bot.send_private_message("employee-code", "hello")
await bot.send_group_message("group-id", "hello", thread_id="root-message-id")
# Group mentions require a numeric SeaTalk ID, not an employee code:
await bot.send_group_message(
    "group-id", Message("Hello ") + MessageSegment.at("12345", id_type="seatalk_id")
)
```

Private threads and group threads are supported. Quoting is supported only in
groups; the private API does not document it. Quotes and thread roots must be
within seven days and quotes must belong to the same feed/thread. Private targets
require an employee code; an event without one is not redirected elsewhere.

| Content | Receive | Send |
| --- | --- | --- |
| Text | Native text | One 1–4096-character text body; plain format by default |
| Mention | Unique, nonoverlapping `@username` mapping; ambiguous text retained | Specific numeric SeaTalk user ID in a group |
| Reply | Native reply and event metadata | At most one group quote |
| Image / file / video | Typed segments preserving protected media URLs | Unsupported |
| Card / forwarded / unknown | Preserved payloads | Unsupported |

Mention offset units are undocumented. The adapter uses only unambiguous literal
username mappings, never guesses offsets. It removes recognized leading bot
mentions/nicknames from the working command message; `original_message` is kept.
Media URLs need authentication and expire after seven days; no automatic download
occurs. Edits, recalls, membership changes, and interactive clicks are notices.

Unsupported/mixed media messages raise `UnsupportedMessage` before any HTTP call.
No splitting or send retry occurs. `SendResult.message_id` can be `None`, especially
for private text sends. A token rejection invalidates the HTTP token for the next
call without replaying the failed send. `ActionFailed` carries code, API path, and
request ID / Retry-After when supplied. Code 100 means token rejection, 101 rate
limit, 103 missing permission. Raw JSON APIs use `bot.request_api(method, path, ...)`
with an origin-relative path; they cannot select another host or override headers.

## Optional Alconna

```sh
python -m pip install 'dist/nonebot_adapter_seatalk-0.1.0-py3-none-any.whl[alconna]'
```

Register the adapter before loading Alconna:

```python
import nonebot
from nonebot.adapters.seatalk import Adapter

nonebot.init()
nonebot.get_driver().register_adapter(Adapter)
nonebot.require("nonebot_plugin_alconna")
```

The `n-p-alc.uniseg.adapters` entry point loads SeaTalk support automatically.
Alconna 0.62.1 is tested; the dependency range is `>=0.62.1,<0.63`.

```python
from nonebot_plugin_alconna import UniMessage
from nonebot_plugin_alconna.uniseg import Target

await UniMessage.text("hello").send(
    target=Target("group-id", adapter="SeaTalk", extra={"thread_id": "root-id"}),
    bot=bot,
)
# Private Target IDs are employee codes:
await UniMessage.text("hello").send(
    target=Target("employee-code", private=True, adapter="SeaTalk"), bot=bot
)
```

Incoming text, user mentions, replies, and media convert to universal segments;
opaque content becomes `Other`. Outgoing text, `At("user", "seatalk:12345")`, and
group `Reply` are supported. Text styles are sent as plain text. Employee codes
cannot be exported as mentions; `at_sender=True` may therefore be unsupported.
Unsupported media/mentions raise the adapter's `UnsupportedMessage` even with
fallback enabled. Missing receipt IDs raise `SerializeFailed` when requesting a
reply reference. Recall, edit, target enumeration, scopes, and persisted
`Target.dump` → `Target.load` round trips are unsupported. The base package and
entry-point loader import without Alconna installed.

## Delivery and diagnostics

Acknowledgement means the event was accepted by this running adapter. Up to 128
unfinished handlers are admitted per bot. Duplicates are suppressed while pending,
then for ten minutes in a 4,096-entry cache. Caches survive reconnects, not process
restarts. A crash after acknowledgement can lose unfinished work; plugin failures
are not replayed. Capacity exhaustion closes the connection without acknowledging
the new event. Server redelivery and exactly-once processing are not guaranteed.

Network failures reconnect with delays from one to thirty seconds. Registration
rejection or a kick stops the bot until configuration is corrected and the process
restarted. Adapter logs report application/event IDs and exception categories;
NoneBot and plugins control their own logging.

## Development and verification

```sh
uv sync --group dev --extra alconna
uv run --extra alconna pytest -q
uv run ruff check nonebot tests examples
uv run ruff format --check nonebot tests examples
uv build
SEATALK_TEST_WHEEL=dist/nonebot_adapter_seatalk-0.1.0-py3-none-any.whl uv run pytest tests/test_distribution.py -q
```

CI tests installed wheels outside the source tree on Python 3.10 / NoneBot 2.4 /
Pydantic 1, Python 3.14 / NoneBot 2.5 / Pydantic 2, and Python 3.12 / NoneBot 2.5 /
Alconna 0.62.1. Source tests extend NoneBot's adapter namespace; installed checks
set `SEATALK_TEST_INSTALLED=1` to disable that hook.

Live acceptance remains open: private reply, mentioned group reply, thread reply,
and reconnect against a designated test app. Automated tests do not establish
production endpoint pairing or server redelivery behavior.
