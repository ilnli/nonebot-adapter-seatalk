# NoneBot2 SeaTalk Adapter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Deliver an installable SeaTalk adapter that receives WebSocket events, runs NoneBot text commands, replies through HTTP, and optionally supports Alconna.

**Architecture:** Implement the supplied SDK's protocol through NoneBot's async drivers, with per-application connections and admission state. Keep event/message conversion separate from HTTP authentication and sending. Load the optional Alconna builder/exporter through its package entry point.

**Tech Stack:** Python 3.10+, NoneBot2, Pydantic through `nonebot.compat`, Hatchling, uv, pytest/pytest-asyncio, NoneBug, Ruff; optional nonebot-plugin-alconna.

**Spec:** [Approved SeaTalk adapter design](../specs/2026-09-27-seatalk-adapter-design.md).

## Global Constraints

- Package: `nonebot-adapter-seatalk`; import: `nonebot.adapters.seatalk`; adapter name: `SeaTalk`.
- “Use the supplied SDK as the source of truth for the available WebSocket protocol.” No runtime SDK dependency or copied socket implementation.
- “Target Python 3.10+ and NoneBot2 2.4.x through the current 2.x series”; use `nonebot.compat` for Pydantic compatibility.
- “Require both `WebSocketClientMixin` and `HTTPClientMixin`.” No inbound server requirement.
- “Each `Bot.self_id` is its configured `app_id`”; keep that separate from the bot's SeaTalk user ID.
- Configuration: `seatalk_bots`; required `app_id`, secret `app_secret`, HTTPS `api_base`; default `ws_url` is `wss://ws-openapi.haiserve.com/ws/bot`; optional `bot_seatalk_id`.
- Registration timeout: 15 seconds; fallback heartbeat interval: 15 seconds; reconnect delay: 1 second doubling to 30 seconds, reset after 60 registered seconds; shutdown grace period: 10 seconds.
- Admission limit: 128 unfinished tasks per bot; completed deduplication cache: 4,096 entries, 10-minute retention; pending keys survive until completion.
- “Acknowledgement means **accepted by the running adapter**, not that every plugin completed successfully.” No persistence or exactly-once guarantee.
- “The base adapter must import and run without Alconna installed.” Entry-point group: `n-p-alc.uniseg.adapters`.
- No outgoing media/card support, webhook reception, automatic send retries, silent message dropping, target enumeration, or runtime patches to Alconna enums.
- Do not include the supplied SDK in distributions; keep it intact and outside implementation commits. Do not publish, push, or send live messages as part of automated tests.

## Review Focus

1. A Unicode mention uses non-Python offsets, or overlaps another mention: preserve text unless the verified offset conversion is valid (Task 2).
2. An event claims a different application, or repeats an event ID with a new callback ID: never dispatch to the wrong bot; acknowledge the current duplicate callback (Task 5).
3. A raw API path overrides the configured host: reject it before requesting or attaching an application token (Task 6).
4. Concurrent requests see an expiring token: use the documented expiry units and perform only one refresh (Task 6).
5. Alconna is asked to send an image with fallback enabled: fail explicitly before HTTP rather than sending an image marker as text (Task 7).

---

## Execution status — 2026-09-27

- Tasks 1–8: implementation and automated acceptance complete. Authenticated official docs unblocked HTTP sending and Alconna.
- Task 2 adjustment: official docs omit offset units; convert unique literal username mappings, preserving ambiguous text/metadata.
- Task 7 adjustment: UnsupportedMessage escapes Alconna's outer fallback handler; SerializeFailed would silently stringify unsupported media.
- Installed wheels: Python 3.10 / NoneBot 2.4 / Pydantic 1: 98 passed, optional Alconna module skipped. Python 3.14 / NoneBot 2.5 / Pydantic 2: same, with pytest-asyncio deprecation warnings. Python 3.12 / NoneBot 2.5 / Alconna 0.62.1: 117 passed.
- Receiving core was independently reviewed earlier; remaining implementation awaits final review. Live acceptance remains open.

## Execution context and dependency decisions

The repository currently contains only the committed design and an untracked `seatalk-oapi/` reference directory. There is no Python project or installed NoneBot environment yet. Initialize an isolated worktree at execution time using the worktree skill; the original SDK remains readable at `/root/projects/nonebot-adapter-seatalk/seatalk-oapi/` even if absent from that worktree. Do not copy it into Git merely to make a worktree self-contained.

PyPI metadata and release wheels were inspected on 2026-09-27, without installing product dependencies:

- [NoneBot2 2.5.0](https://pypi.org/project/nonebot2/2.5.0/) exposes the required driver interfaces. Base dependency target: `nonebot2>=2.4.0,<3`.
- [Alconna 0.62.1](https://pypi.org/project/nonebot-plugin-alconna/0.62.1/) includes external loader discovery and requires `nonebot2>=2.5.0`. Use `nonebot-plugin-alconna>=0.62.1,<0.63` in the optional extra; test exactly 0.62.1 initially. This is a source-inspected candidate range, not a passing compatibility claim.
- [NoneBug 0.4.4](https://pypi.org/project/nonebug/0.4.4/) supports NoneBot >=2.3. Use `nonebug>=0.4.4,<0.5`, `pytest>=8,<9`, `pytest-asyncio>=0.24,<1`, and Ruff in the development group; lock the resolved versions during Task 2.

Keep the base minimum at 2.4.0 if its test lane passes. A necessary increase must be explained against the spec before changing the declared floor. The optional extra may require NoneBot 2.5.0 without increasing the base minimum.

Task order: 1 → 2 → 3 → 4 → 5 → 6 → 7 → 8. If Task 1 lacks HTTP evidence, proceed only with SDK-backed portions of Tasks 2–5; leave the dependent mention conversion, HTTP sending, and Alconna sending steps unchecked. Do not call the adapter complete while that evidence is missing.

## File structure

All paths below are relative to the execution worktree.

| Files | Responsibility |
| --- | --- |
| `pyproject.toml`, `uv.lock`, `.gitignore` | Build/dependencies, developer checks, excludes for secrets/build artifacts/local SDK |
| `nonebot/adapters/seatalk/__init__.py`, `py.typed` | Public exports and typing marker; no top-level `nonebot/__init__.py` |
| `nonebot/adapters/seatalk/config.py` | Bot and adapter settings |
| `nonebot/adapters/seatalk/models.py` | Shared immutable `Destination` and `SendResult` value objects |
| `nonebot/adapters/seatalk/exception.py` | Adapter exceptions |
| `nonebot/adapters/seatalk/message.py` | Segments, incoming conversion, outgoing request serialization |
| `nonebot/adapters/seatalk/event.py` | Event parsing, classifications, actor/session identities |
| `nonebot/adapters/seatalk/transport.py` | A single registered WebSocket session and heartbeat |
| `nonebot/adapters/seatalk/adapter.py` | Supervisors, admission/deduplication, shutdown, API dispatch |
| `nonebot/adapters/seatalk/bot.py` | NoneBot preprocessing, destination resolution, send conveniences |
| `nonebot/adapters/seatalk/api.py` | HTTP token cache, errors, raw requests, send requests |
| `nonebot/adapters/seatalk/integrations/__init__.py`, `integrations/alconna/{__init__,builder,exporter}.py` | Optional bridge; paths are under the adapter package |
| `tests/conftest.py`, `tests/fakes.py`, `tests/fixtures/` | NoneBug configuration, in-process driver/peer doubles, independently authored wire examples |
| `tests/test_{message,event,transport,adapter,api,bot,alconna,distribution}.py` | Behavior tests owned by tasks below |
| `docs/references/seatalk-contracts.md`, `README.md`, `examples/bot.py`, `examples/.env.example`, `examples/plugins/echo.py`, `.github/workflows/test.yml` | Contract evidence, usage example, and repeatable validation |

Do not create `utils.py` unless a helper is actually shared; keep logging local otherwise. `models.py` avoids circular imports between event routing, HTTP results, and Alconna.

## Task 1: Establish the external contracts and reference fixtures

**Files:** Create `docs/references/seatalk-contracts.md`, `tests/fixtures/http/{token,private_send,group_send,thread_send,quote_send,api_error,rate_limit}.json`, `tests/fixtures/events/{private,group_mentioned,thread,unicode_mentions}.json`.

**Interfaces:** Produces evidence and JSON fixtures, not runtime code. Each HTTP fixture has `method`, `path`, `request`, `status`, `response`, and `source` fields; event fixtures contain the unwrapped platform event body. Later tasks use `case(name: str) -> dict[str, Any]`, a test-only loader defined in Task 2.

- [x] **Step 1: Record verified contracts.** Read the SDK protocol/registration implementation and the applicable official SeaTalk documents, using authorized documentation access or user-provided sanitized examples if necessary. Record source/date, HTTP token path and expiry units, private/group recipients, thread/quote semantics, plain-text and mention encoding, size limits, success/error fields, and the pairing of HTTP/WS environments. Do not infer token interchangeability. If docs remain inaccessible, record the precise missing facts and request that information while continuing only independent work.
- [x] **Step 2: Author minimal fixtures.** Use invented IDs and dummy secrets, preserving the verified wire shapes. Include a supplementary Unicode character before a mention, a thread reply distinct from its root message, and a response with no message ID if that is legal. Record quote support per destination explicitly. Use the local SDK as a schema reference without copying unlicensed sample content. Pairing of real environment credentials remains a live-verification item if only protocol documentation is available.
- [x] **Step 3: Verify the evidence artifact.** Run `python3 -m json.tool` against each newly written fixture; all must parse. Check each HTTP fixture against its cited source, including whether token expiry is an epoch or duration. If thread replies are unsupported, obtain a spec revision before implementing that path. Missing HTTP/offset evidence leaves this task incomplete.
- [x] **Step 4: Commit verified evidence only.** `git add docs/references/seatalk-contracts.md tests/fixtures` then `git commit -m "docs: record verified SeaTalk protocol contracts"`. Do not claim an automated test cycle for this documentation task.

## Task 2: Build the installable message and configuration model

**Files:** Create `pyproject.toml`, `uv.lock`, `.gitignore`, package `__init__.py`, `py.typed`, `config.py`, `models.py`, `exception.py`, `message.py`, `tests/conftest.py`, `tests/test_message.py`.

**Interfaces:**

- `BotConfig(app_id: str, app_secret: SecretStr, api_base: str, ws_url: str = SDK_DEFAULT, bot_seatalk_id: str | None = None)` and `Config(seatalk_bots: list[BotConfig])`.
- Frozen dataclasses `Destination(kind: Literal["private", "group"], id: str, thread_id: str | None = None)` and `SendResult(message_id: str | None, destination: Destination, thread_id: str | None, raw_response: dict[str, Any])`.
- `Message`/`MessageSegment` subclasses; factories `text(text: str)`, `at(user_id: str, *, id_type: Literal["employee_code", "seatalk_id"] = "employee_code", display: str | None = None)`, `reply(message_id: str)`, `image(url: str)`, `file(url: str, name: str | None = None)`, `video(url: str)`, `card(payload: dict[str, Any])`, `forward(payload: dict[str, Any])`, `raw(tag: str, payload: dict[str, Any])`, all returning `MessageSegment`.
- `parse_message(payload: dict[str, Any], *, group: bool) -> Message`. Preserve invalid mention metadata on the text segment as `mentions`; preserve unrecognized media/card fields in segment data.
- `SeaTalkAdapterException`, `NetworkError`, `ActionFailed(code: int | str, message: str, *, api: str, request_id: str | None = None, retry_after: str | None = None)`, `ApiNotAvailable`, `UnsupportedMessage`, `InvalidEvent`, and `EventCapacityExceeded`. Use NoneBot exception base classes where applicable and set adapter identity.
- Test fixture `case(name: str) -> dict[str, Any]` loads a fresh copy of `tests/fixtures/<name>.json`; it does not expose live credentials.

- [x] **Step 1: Set up the test/build environment for this deliverable.** Configure Hatchling to package only the adapter namespace and `py.typed`; development dependencies as above, pytest asyncio auto mode, Ruff for Python 3.10. Ignore `.env`, `.venv`, caches/build outputs, worktrees, and `/seatalk-oapi/`. Run `uv sync --group dev`; dependency installation belongs to execution, not plan review.
- [x] **Step 2: Write failing message/configuration tests.** Include the following assertions, plus factory round-trip preservation of image/file/video/card/forward/raw payloads in one parametrized test:

```python
def test_text_extraction_excludes_media():
    msg = Message("hello") + MessageSegment.image("https://media.example/x")
    assert msg.extract_plain_text() == "hello"
    assert not msg[1].is_text()

def test_unicode_mentions_follow_documented_offsets(case):
    payload = case("events/unicode_mentions")["event"]["message"]
    msg = parse_message(payload, group=True)
    assert [seg.type for seg in msg] == ["text", "at", "text"]
    assert msg[0].data["text"] == "😀你好 "
    assert msg[1].data["id_type"] == "seatalk_id"

def test_overlapping_mentions_preserve_text():
    payload = {"tag": "text", "text": {"plain_text": "@A@B hi", "mentioned_list": [
        {"location": 0, "length": 3, "seatalk_id": "a"},
        {"location": 2, "length": 2, "seatalk_id": "b"},
    ]}}
    msg = parse_message(payload, group=True)
    assert msg.extract_plain_text() == "@A@B hi"
    assert len(msg[0].data["mentions"]) == 2
```

Also assert duplicate app IDs are rejected, `api_base` is required and HTTPS, the SDK URL is the default, and a dummy secret does not appear in configuration repr. The Unicode fixture text is fixed above; its offsets come from Task 1, not Python string indexes assumed in advance.

- [x] **Step 3: Verify red.** Run `uv run pytest tests/test_message.py -q`; expect missing adapter model imports or unimplemented behavior, not a broken test environment.
- [x] **Step 4: Implement the declared model interfaces.** Keep the incoming converter small and lossless; validate mention spans as a set before replacing any text. Use `nonebot.compat` model validation and keep configuration validation limited to required fields/IDs/service URL schemes. Export `Message`, `MessageSegment`, and value types now; add `Adapter`/`Bot` when implemented.
- [x] **Step 5: Verify green.** Run `uv run pytest tests/test_message.py -q` and `uv run ruff check nonebot tests`; expect success. Add no tests for trivial dataclass field assignment.
- [x] **Step 6: Commit.** Stage only the files listed for this task, then `git commit -m "feat: add SeaTalk configuration and message models"`.

## Task 3: Map SDK events into NoneBot events

**Files:** Create `nonebot/adapters/seatalk/event.py`, `tests/test_event.py`; extend `tests/fixtures/events/` with independently authored SDK-shaped notice/mutation cases.

**Interfaces:** Consumes Task 2 `Message` and `parse_message`. Produces `parse_event(data: dict[str, Any], *, app_id: str, callback_id: str = "") -> Event`, raising `InvalidEvent` on invalid required structure or conflicting app identity. `Event` retains platform fields and `raw_event`; message events expose `message`, deep-copied `original_message`, `message_id`, `quoted_message_id`, `thread_id`, `employee_code`, `seatalk_id`, optional `group_id`, `explicit_mention`, and mutable `to_me`.

Classes: `Event`, `MessageEvent`, `PrivateMessageEvent`, `GroupMessageEvent`, `ThreadMessageEvent`, `NoticeEvent`, `InteractiveMessageClickEvent`, `ChatEntryNoticeEvent`, `BotAddedNoticeEvent`, `BotRemovedNoticeEvent`, `GroupConvertedNoticeEvent`, `MessageEditedNoticeEvent`, `MessageRecalledNoticeEvent`, `GroupMembersChangedNoticeEvent`, `GroupRemovedNoticeEvent`. Unknown events use `NoticeEvent` preserving the platform name.

- [x] **Step 1: Write failing event tests.** Use `json.loads` on session IDs to avoid prescribing whitespace; fixtures use app `app-a`, employee `emp-a`, group `group-a`, thread `thread-a`:

```python
def test_thread_session_isolates_sender_and_conversation(case):
    event = parse_event(case("events/thread"), app_id="app-a", callback_id="cb-a")
    assert isinstance(event, ThreadMessageEvent)
    assert json.loads(event.get_session_id()) == ["app-a", "group", "group-a", "thread-a", "emp-a"]
    assert event.get_user_id() == "emp-a"
    assert event.callback_id == "cb-a"

def test_private_event_keeps_original_message(case):
    event = parse_event(case("events/private"), app_id="app-a")
    event.message.clear()
    assert event.original_message.extract_plain_text() == "/echo hello"
    assert event.is_tome()
```

Parametrize SDK notice/mutation tags to assert `get_type() == "notice"`; unknown event/body fields remain in `raw_event`. Assert the fallback actor is `seatalk:<id>`, missing actors raise `ValueError`, and event descriptions contain IDs/types but not message content.

- [x] **Step 2: Verify red.** `uv run pytest tests/test_event.py -q` fails on absent event classes/parser.
- [x] **Step 3: Implement the event interfaces.** Use a straightforward event-name/tag dispatch table. Keep platform IDs as strings. Implement NoneBot's abstract methods; non-message `get_message()` raises `ValueError`. Session encoding follows spec section 8 exactly. Classify mutation tags before normal message construction. No contact lookups.
- [x] **Step 4: Verify green.** `uv run pytest tests/test_event.py tests/test_message.py -q` passes.
- [x] **Step 5: Commit.** Stage the event module/tests/fixtures, then `git commit -m "feat: map SeaTalk events to NoneBot conversations"`.

## Task 4: Implement a registered async WebSocket session

**Files:** Create `nonebot/adapters/seatalk/transport.py`, `tests/fakes.py`, `tests/test_transport.py`.

**Interfaces:** Consumes `BotConfig` and driver `WebSocket`. Produces `Registration(app_id: str, sid: str, heartbeat_interval: float, heartbeat_timeout: float)`; `WebSocketSession(ws: WebSocket, config: BotConfig)` with async `register() -> Registration`, `run(on_event: Callable[[dict[str, Any]], Awaitable[None]]) -> None`, `ack(callback_id: str) -> None`, `close() -> None`. `run` passes whole event envelopes to its callback; it does not acknowledge them itself. Session token stays private. `RegistrationRejected` and `SessionKicked` are terminal transport exceptions; transient errors use `NetworkError`.

Test double `FakeWebSocket` implements the driver's abstract WebSocket methods, with `push(envelope: dict[str, Any]) -> None`, `sent: list[dict[str, Any]]`, `closed: bool`, async `wait_sent(command: str) -> dict[str, Any]`, and one-shot `fail_next_send: Exception | None`. It uses asyncio queues/events, no real network or long sleeps.

- [x] **Step 1: Write failing session tests.** Construct the peer/session in test fixtures. The successful registration uses token `ws-token`, interval 15, timeout 30:

```python
async def test_register_then_ack(session, peer):
    peer.push({"cmd": "register", "header": {"app_id": "app-a", "token": "ws-token", "sid": "sid-a"},
               "data": {"heartbeat_interval": 15, "heartbeat_timeout": 30}})
    registration = await session.register()
    await session.ack("cb-a")
    assert registration.heartbeat_interval == 15
    assert peer.sent[-1]["header"]["token"] == "ws-token"
    assert peer.sent[-1]["header"]["callback_id"] == "cb-a"
    assert all(frame["header"]["rid"] for frame in peer.sent)
```

Add tests for default 15-second interval/30-second pong timeout, a registration deadline of 15 seconds, empty tokens/conflicting app IDs, terminal rejection/kick, and a missed pong deadline unaffected by later pings. Patch the module timing boundary or inject elapsed time in the test; do not spend real seconds per case. Simultaneous ping/ack writes must serialize. A malformed JSON frame logs a safe parsing error and does not hide a subsequent valid event.

- [x] **Step 2: Verify red.** `uv run pytest tests/test_transport.py -q` fails on absent session implementation.
- [x] **Step 3: Implement the session interfaces.** Use SDK envelope field names and UUID request IDs. Await registration with `asyncio.wait_for` for Python 3.10 compatibility. After registration run receive and heartbeat concurrently; close/cancel the sibling task on failure, and propagate cancellation. Clear credentials on close. Handle malformed known frames without crashing a healthy receive loop; ignore/log unknown commands without treating them as events. No reconnect loop here.
- [x] **Step 4: Verify green.** `uv run pytest tests/test_transport.py -q` passes with no unfinished task warnings.
- [x] **Step 5: Commit.** Stage transport/fakes/tests, then `git commit -m "feat: implement SeaTalk async WebSocket protocol"`.

## Task 5: Connect bots, admit events, and dispatch commands

**Files:** Create `nonebot/adapters/seatalk/adapter.py`, `bot.py`, `tests/test_adapter.py`, `tests/test_bot.py`; update package exports and `tests/{fakes,conftest}.py`.

**Interfaces:** Consumes `parse_event`, `WebSocketSession`, configuration, and message models. Produces `Adapter(driver: Driver, **kwargs: Any)` with `get_name() -> str`, async `_startup() -> None`, `_shutdown() -> None`, `_call_api(bot: Bot, api: str, **data: Any) -> Any`, `_on_envelope(bot: Bot, session: WebSocketSession, envelope: dict[str, Any]) -> None`, and synchronous `_admit_event(bot: Bot, event: Event) -> bool` (accepted or duplicate = true; capacity exhaustion raises `EventCapacityExceeded`). Produces `Bot(adapter: Adapter, config: BotConfig)` with `bot_config`, async `handle_event(event: Event) -> None`, and the standard async `send(event, message, **kwargs)` signature. Until Task 6, sending/API dispatch explicitly raises `ApiNotAvailable`.

Extend test doubles with a driver offering both client mixins and queued `FakeWebSocket` sessions. The fixture `running_adapter` owns startup/shutdown; expose sent frames, handler calls, and connection/disconnection notifications. Use a gated handler (`asyncio.Event`) to keep admissions pending without slow sleeps.

- [x] **Step 1: Write failing admission and lifecycle tests.** Test helper fixtures define `deliver(event_id, callback_id, *, app_id="app-a")`, `handler_calls`, and `acks` using the fake peer, with these central assertions:

```python
async def test_duplicate_uses_new_callback_without_second_dispatch(deliver, handler_calls, acks):
    await deliver("event-a", "cb-1")
    await deliver("event-a", "cb-2")
    assert handler_calls == ["event-a"]
    assert acks == ["cb-1", "cb-2"]

async def test_cross_app_payload_is_not_admitted(deliver, handler_calls, acks):
    await deliver("event-a", "cb-1", app_id="different-app")
    assert handler_calls == []
    assert acks == []
```

Exercise 128 pending admissions then a rejected 129th, a duplicate admitted at capacity, pending-key retention, completed-cache eviction at 4,096 and expiry after 600 seconds, and ack failure/redelivery without a second dispatch. Include the callback-ID fallback and missing-both-ID case. Assert malformed known events are unacknowledged and unknown valid events are admitted. For two bots, identical event IDs do not share state.

- [x] **Step 2: Verify red.** `uv run pytest tests/test_adapter.py -q` fails on missing lifecycle/admission implementation.
- [x] **Step 3: Implement lifecycle and admission.** Register driver startup/shutdown hooks, validate mixins without requiring ASGI, and create a supervisor per bot. Keep pending/completed state for the configured bot across socket replacements. Check and record keys before yielding; schedule tracked `Bot.handle_event` tasks and then ack. Use the spec's limits/backoff/shutdown values. Make `bot_connect`/`bot_disconnect` synchronous calls, matching NoneBot. Observe exceptions and let cancellation terminate reconnect sleeps.
- [x] **Step 4: Write command preprocessing tests.** Assert a leading verified self-mention/nickname is removed only from `message`, `original_message` stays intact, another user's mention remains, and an unidentifiable mention is not removed. Self messages are ignored only with a matching configured SeaTalk ID. With NoneBug, run `on_command("echo")` and `to_me()` against private/group/thread events and verify handler invocation. Test startup makes no HTTP call; disconnected sessions balance notifications; rejection/kick stops reconnecting; shutdown interrupts backoff and drains/cancels handlers within the 10-second policy.
- [x] **Step 5: Verify the added tests fail, then implement `Bot.handle_event`.** Run `uv run pytest tests/test_bot.py -q`, observe the expected failures, then preprocess and call `nonebot.message.handle_event`. Keep notice dispatch separate from text preprocessing.
- [x] **Step 6: Verify green.** `uv run pytest tests/test_adapter.py tests/test_bot.py tests/test_transport.py -q` passes, with no leaked tasks and no secrets in captured adapter logs.
- [x] **Step 7: Commit.** Stage this task's listed files, then `git commit -m "feat: dispatch SeaTalk events with bounded admission"`.

## Task 6: Add authenticated HTTP requests and text replies

**Files:** Create `nonebot/adapters/seatalk/api.py`, `tests/test_api.py`; update `message.py`, `bot.py`, `adapter.py`, `tests/{fakes,test_message,test_bot}.py`.

**Prerequisite:** Task 1 HTTP evidence is complete. Do not implement an endpoint path, expiry conversion, text limit, quote field, or thread field from memory.

**Interfaces:**

- `serialize_message(message: Message, destination: Destination, *, quote_id: str | None = None) -> dict[str, Any]` in `message.py` produces the complete verified send-request body, validating every segment before I/O.
- `APIClient(config: BotConfig, request: Callable[[Request], Awaitable[Response]], *, timeout: float | None)`; async `request_api(method: str, path: str, *, params: dict[str, Any] | None = None, json: dict[str, Any] | None = None) -> dict[str, Any]`, async `send_message(destination: Destination, message: Message, *, quote_id: str | None = None) -> SendResult`. Token refresh is private and per instance.
- `resolve_destination(event: Event) -> Destination` in `bot.py`; async Bot conveniences `send_private_message(employee_code: str, message: str | Message | MessageSegment, *, thread_id: str | None = None, quote_id: str | None = None) -> SendResult`, `send_group_message(group_id: str, message: str | Message | MessageSegment, *, thread_id: str | None = None, quote_id: str | None = None) -> SendResult`, and `request_api` with the same signature as the client.
- `Bot.send(event, message, **kwargs) -> SendResult` accepts `quote_id`; rejects conflicting destination/thread overrides. Explicit convenience methods route through `bot.call_api`; `_call_api` has an explicit three-name dispatch table and one `APIClient` per configured bot.
- Test `FakeHTTP` records `requests: list[Request]` and serves scripted `Response`/exception objects through async `request(Request) -> Response`; it asserts unexpected requests instead of reaching a real service.

- [x] **Step 1: Write failing HTTP and serialization tests.** Compare outgoing bodies and paths exactly to Task 1 fixtures. Include private, group, thread, quote, adjacent text, supported mention identity, empty/oversized text, conflicting quotes, and rejected mixed text+image before any token request. Assert missing employee codes do not trigger contact lookup or parent-group delivery. A success without a platform message ID produces `None`.

```python
async def test_no_partial_send_for_media(client, http):
    msg = Message("hello") + MessageSegment.image("https://media.example/x")
    with pytest.raises(UnsupportedMessage):
        await client.send_message(Destination("group", "group-a"), msg)
    assert http.requests == []

async def test_raw_api_cannot_override_origin(client, http):
    for path in ("https://other.example/x", "//other.example/x"):
        with pytest.raises(ValueError):
            await client.request_api("GET", path)
    assert http.requests == []
```

Add `test_single_refresh_at_documented_expiry`: issue two concurrent calls with a stale cached token, assert exactly one token request and two sends using the refreshed HTTP token, never `ws-token`. Assert malformed HTTP bodies and unexpected status codes become safe adapter errors, timeouts cause one send attempt, platform errors preserve code/request ID, authentication rejection invalidates cache without replay, and rate-limit metadata is exposed.

- [x] **Step 2: Verify red.** `uv run pytest tests/test_api.py tests/test_message.py -q` fails for absent HTTP/serializer behavior.
- [x] **Step 3: Implement `serialize_message` and `APIClient`.** Use verified contracts, an async refresh lock with a second expiry check, and a modest refresh margin bounded by token lifetime. Allow only origin-relative API paths; reject URL credentials/authority/backslashes before obtaining a token, and join paths without permitting a caller-selected host. Use the HTTP driver's public request interface without reaching into its underlying client. Validate status/JSON response shape, chain network errors without dumping bodies, and perform no send retries.
- [x] **Step 4: Implement Bot routing and API dispatch.** Resolve private recipients from employee fields, group/thread destinations from event fields, and click notices only when a destination exists. Validate unsupported private-thread or quote combinations according to Task 1. Route high-level `send` through the convenience methods and NoneBot API hooks. Keep the client's lifetime independent of WebSocket reconnects.
- [x] **Step 5: Verify end-to-end command replies.** Extend NoneBug tests so private/group/thread echo handlers call `Bot.send`; assert the observed HTTP request and return value, including opt-in quote and retained thread. Run `uv run pytest tests/test_api.py tests/test_bot.py tests/test_message.py tests/test_adapter.py -q`; expect success. No live API calls.
- [x] **Step 6: Commit.** Stage the listed files, then `git commit -m "feat: send SeaTalk text messages through authenticated HTTP"`.

## Task 7: Add the optional Alconna bridge

**Files:** Create `nonebot/adapters/seatalk/integrations/__init__.py`, `integrations/alconna/{__init__,builder,exporter}.py`, `tests/test_alconna.py`; update `pyproject.toml`, `uv.lock`.

**Interfaces:** Consumes public `Message`, `MessageSegment`, event classes, Bot send conveniences, `Destination`, and `SendResult`. Produces lazy `Loader` with `get_adapter()` returning a local string enum whose value is `SeaTalk`, `get_builder() -> SeaTalkMessageBuilder`, `get_exporter() -> SeaTalkMessageExporter`, and `get_fetcher()` raising `NotImplementedError`. Declare entry point `seatalk = "nonebot.adapters.seatalk.integrations.alconna:Loader"` in group `n-p-alc.uniseg.adapters`.

Builder subclasses `MessageBuilder[MessageSegment]` and maps native text/at/reply/image/file/video through `@build`. Exporter subclasses `MessageExporter[Message]`, with `get_adapter`, `get_message_type`, `get_target(event, bot=None) -> Target`, `get_message_id(event) -> str`, async `send_to(target: Target | Event, bot: Bot, message: Message, **kwargs: Any) -> SendResult`, and `get_reply(result: SendResult) -> Reply` (raises `SerializeFailed` if no message ID). Override async `export(source: Sequence[Segment], bot: Bot | None, fallback: bool | FallbackStrategy) -> Message` to reject unsupported segment classes, non-user mentions, and unsendable mention identities before calling the base exporter; its fallback handler otherwise catches serialization errors and may stringify unsupported content.

- [x] **Step 1: Install the optional test dependency and write failing bridge tests.** Add the extra range selected above, run `uv sync --group dev --extra alconna`, and initialize/register the SeaTalk adapter before importing/loading Alconna in tests. Assert entry-point discovery through the installed package, not a manually populated mapping. Use exact 0.62.1 in the pinned CI lane.

```python
async def test_unimessage_text_sends_to_thread(bot, http):
    target = Target("group-a", adapter="SeaTalk", extra={"thread_id": "thread-a"})
    receipt = await UniMessage.text("hello").send(target=target, bot=bot)
    assert http.requests[-1].json == expected_thread_body
    assert receipt is not None

async def test_media_fails_even_with_fallback(bot, http):
    with pytest.raises(SerializeFailed):
        await UniMessage.image(url="https://media.example/x").export(bot=bot, fallback=True)
    assert http.requests == []
```

`expected_thread_body` is taken from Task 1 with the text set to `hello`. Also test `UniMessage.of(..., adapter="SeaTalk")`, private/group targets, text/at/reply conversion, incoming media conversion, and an `on_alconna` text command through NoneBug. Verify no phantom reply ID when sending returns no ID; recall/edit/enumeration remain unsupported.

- [x] **Step 2: Verify red.** `uv run --extra alconna pytest tests/test_alconna.py -q` fails on missing loader/conversion.
- [x] **Step 3: Implement the lazy loader and converters.** Keep the loader module independent of Alconna imports; import builders/exporters inside loader methods. Use `.value == "SeaTalk"` without mutating upstream enums. Map universal user IDs to employee codes, preserving `seatalk:` prefixes for SeaTalk-only identities and rejecting unsendable identities. Preserve opaque native card/forward/raw content as universal `Other`, but disallow re-export for high-level sending. Targets carry `thread_id` in `extra`, use adapter string `SeaTalk`, and no unsupported `SupportScope`. `get_target` rejects a private event without an employee recipient instead of manufacturing a sendable target; `get_message_id` rejects absent IDs. Keep export-handler type annotations compatible with the released decorator's runtime inspection. Do not override recall/edit methods just to raise errors; inherit unsupported behavior.
- [x] **Step 4: Verify green.** Run `uv run --extra alconna pytest tests/test_alconna.py tests/test_bot.py -q`; expect success without patching loader mappings or enums. Unsupported external loader behavior requires a design revision, not a monkeypatch. Document the excluded `Target.dump`/`Target.load` round trip in Task 8.
- [x] **Step 5: Commit.** Stage the bridge/tests/dependency changes, then `git commit -m "feat: add optional Alconna message integration"`.

## Task 8: Verify the wheel and document a runnable bot

**Files:** Create `README.md`, `examples/bot.py`, `examples/.env.example`, `examples/plugins/echo.py`, `.github/workflows/test.yml`, `tests/test_distribution.py`; update project metadata and contract document only to record actual verification results.

**Interfaces:** Consumes the finished public adapter API and packaged entry point. Produces an installable `0.1.0` wheel, runnable example, and CI lanes. The example registers `Adapter`, loads `examples.plugins.echo`, and uses `~none+~httpx+~websockets` with the corresponding NoneBot extras. Configuration contains placeholder credentials and an explicit matching HTTPS API base.

- [x] **Step 1: Write the distribution check.** `tests/test_distribution.py` accepts a wheel location via `SEATALK_TEST_WHEEL`. Assert it includes `nonebot/adapters/seatalk/py.typed` and the loader entry point, but no SDK package, top-level `nonebot/__init__.py`, secrets, tests, or local path dependency. Skip only this artifact-specific test when the variable is absent; the release command below must set it.
- [x] **Step 2: Write the usage example and README.** Cover driver installation/configuration, subscriptions/permissions from Task 1, paired service URLs, identity/mention settings, private/group/thread echo, supported send/receive segment matrix, failure diagnostics, acknowledgement/loss limitations, optional Alconna usage, and unsupported persisted-target round trips. Explain missing message IDs and the absence of automatic send retries. Do not choose a repository license on the user's behalf or bundle unlicensed SDK sources.
- [x] **Step 3: Build and run artifact checks.** Run `uv run ruff check nonebot tests examples`, `uv run ruff format --check nonebot tests examples`, `uv run --extra alconna pytest tests -q`, and `uv build`. Then run `SEATALK_TEST_WHEEL=dist/nonebot_adapter_seatalk-0.1.0-py3-none-any.whl uv run pytest tests/test_distribution.py -q`. Expect all checks to pass and exactly the intended adapter distribution.
- [x] **Step 4: Test clean installs and add CI lanes.** Install the wheel in fresh temporary virtual environments, outside the source tree and without `PYTHONPATH`. Base lane: Python 3.10, NoneBot 2.4.0, Pydantic 1.10.x, no Alconna. Optional lane: Python 3.12, NoneBot 2.5.0, Pydantic 2.x, Alconna 0.62.1. Current-Python lane: Python 3.14, NoneBot 2.5.0/Pydantic 2.x, base adapter. Use `uv venv --python <version> <temp-path>` and `uv pip install --python <temp-path>/bin/python <wheel> <lane-pins>`; test dependencies and driver extras may be installed for the relevant suite. Run the base suite excluding `test_alconna.py` in base lanes and the full suite in the optional lane. Prove the base import and loader import do not import Alconna. Record any unsupported lane honestly and reconcile metadata before completion.
- [x] **Step 5: Record live verification status.** The required live scenarios are private reply, mentioned group reply, thread reply, and reconnect. Execute only with explicit authorization and a designated test app/destination; otherwise record `Not live-verified` and keep the live acceptance checklist open. Lack of live access does not turn mocked tests into a production claim.
- [x] **Step 6: Commit.** Stage only the release documentation/example/CI/test changes, then `git commit -m "docs: document and verify the SeaTalk adapter package"`. Apply the selected execution workflow's final branch review before integration. No automatic push or publication.

## Coverage and handoff

Spec sections 1–4 and 13 are covered by Task 1 and the execution constraints; sections 5–6 by Tasks 2/5; section 7 by Tasks 4/5; sections 8–9 by Tasks 2/3/5/6; section 10 by Task 6; section 11 by Task 7; section 12 by the task tests and Task 8. All five Review Focus items have owning tests. Unverified external contracts and live acceptance remain explicitly identified rather than replaced with assumptions.

Executed natively following user approval. The rulings in the execution status supersede plan assumptions about undocumented mention offsets and Alconna fallback exception types. Live acceptance is recorded as unverified, not completed.
