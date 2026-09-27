# NoneBot2 SeaTalk adapter design

- Date: 2026-09-27
- Status: Proposed; awaiting written-spec review
- Package: `nonebot-adapter-seatalk`
- Import: `nonebot.adapters.seatalk`
- Adapter name: `SeaTalk`
- Remote: `git@github.com:ilnli/nonebot-adapter-seatalk.git`

## 1. Purpose and design brief

Build a reusable NoneBot2 adapter that lets plugin authors receive SeaTalk bot events, run normal NoneBot commands, and reply to users and groups. The intended users are developers operating SeaTalk application bots. A successful first release supports a text command and reply in private chat, group chat, and a group thread, including recovery from a dropped event connection.

The user requested an adapter informed by the supplied SDK, SeaTalk documentation, and existing NoneBot adapters, with preparation for `nonebot/plugin-alconna`. The user accepted the proposed WebSocket-first direction and requested this written spec. This document selects the remaining implementation choices for review; they are proposals, not completed work.

Constraints:

- Use the supplied SDK as the source of truth for the available WebSocket protocol.
- Follow NoneBot's adapter interfaces and asynchronous driver lifecycle.
- Keep the implementation small: no broker, persistent event store, service process, or framework for interchangeable transports.
- Test the principal integration paths and produce useful errors for failures outside those paths.
- Keep Alconna optional, and distinguish command parsing from universal-message support.

## 2. Evidence and assumptions

### Inspected sources

- [Supplied integration guide](../../../seatalk-oapi/OPEN_PLATFORM_DEVELOPER_GUIDE.md).
- [Python SDK client](../../../seatalk-oapi/seatalk-oapi-sdk-py/seatalk_oapi_sdk/client.py), [dispatcher](../../../seatalk-oapi/seatalk-oapi-sdk-py/seatalk_oapi_sdk/dispatcher.py), and [protocol models](../../../seatalk-oapi/seatalk-oapi-sdk-py/seatalk_oapi_sdk/protocol.py).
- [NoneBot adapter API](https://nonebot.dev/docs/api/adapters/).
- [Feishu adapter lifecycle and HTTP integration](https://github.com/nonebot/adapter-feishu/blob/master/nonebot/adapters/feishu/adapter.py).
- [Alconna adapter loading](https://github.com/nonebot/plugin-alconna/blob/master/src/nonebot_plugin_alconna/uniseg/adapters/__init__.py), [loader interface](https://github.com/nonebot/plugin-alconna/blob/master/src/nonebot_plugin_alconna/uniseg/loader.py), and [target implementation](https://github.com/nonebot/plugin-alconna/blob/master/src/nonebot_plugin_alconna/uniseg/target.py).

The SDK is a synchronous, standard-library WebSocket client. Its supported commands are `register`, `event`, `ack`, `ping`, `pong`, and `kick`. It does not implement the HTTP APIs for sending chat messages. Its default connection URL is `wss://ws-openapi.haiserve.com/ws/bot`. Registration supplies a session token and heartbeat settings. The dispatcher acknowledges an event after its registered handler returns normally.

The SDK directory contains no discovered redistribution license. There is also no verified published SDK distribution suitable for a runtime dependency. These facts favor using the SDK as a protocol reference rather than copying its implementation into the adapter or requiring an editable local install.

### External contracts requiring verification

The supplied [SeaTalk documentation URL](https://open.seatalk.io/docs/intro-to-seatalk-open-platform) and the site's linked introduction currently yield the landing page through the available retrieval tools. The documentation application's article endpoint returned HTTP 401 without a login. The following facts are therefore not asserted as verified:

1. The HTTP token endpoint, response expiry representation, and authentication error codes.
2. The private/group text-send schemas, recipient identifier requirements, response identifiers, and thread/quote fields.
3. The encoding unit for mention `location` and `length`, and how the bot's own mention identity is represented.
4. Whether the supplied WebSocket endpoint and the public HTTP API use the same application credentials in the user's environment.

The first implementation-plan task must capture the applicable official documentation or authenticated, sanitized examples for these contracts. Authentication and HTTP sending code must not be built from guessed schemas. Missing evidence blocks that part of implementation and live-release acceptance, but does not require redesigning the adapter interfaces below. A documented inability to support thread replies requires a spec revision, not silent redirection to the parent group.

## 3. Scope

### First release

- One or more configured application bots, each with an independent outbound WebSocket connection.
- Registration, heartbeat, acknowledgement, reconnect, and orderly shutdown.
- Private, group, mentioned-group, and group-thread message events.
- Notices for chat entry, bot membership changes, group conversion, interactive clicks, and message mutations.
- Standard NoneBot text commands, `to_me()` behavior, session identity, and `Bot.send`.
- Text sending to private chats and groups, with explicit quote support and preservation of group-thread destinations once the HTTP contracts are verified.
- Incoming text, mentions, quotes, images, files, video, cards, and forwarded-message data represented without silently discarding unsupported content.
- Optional Alconna integration for text commands and `UniMessage` text, mentions, replies, and incoming media conversion as described below.
- Installation/configuration documentation, a small echo example, core tests, linting, and package build checks.

### Deferred

HTTP webhook reception; media upload and media sending; card construction APIs; outgoing edit/recall operations; organization/contact management wrappers; history synchronization; a Go bridge; durable queues; multiple processes sharing one bot connection; automatic target discovery; and upstream contributions to other repositories.

An authenticated raw HTTP API method remains available to advanced plugins. That escape hatch does not imply that every SeaTalk API has a typed convenience wrapper or a compatibility guarantee from this adapter.

## 4. Approaches and decision

| Approach | Benefit | Cost | Decision |
| --- | --- | --- | --- |
| Implement the supplied protocol using NoneBot async drivers | Native cancellation, testable connection lifecycle, no copied WebSocket framing code or unpublished runtime dependency | Requires a small async implementation of registration, heartbeat, and acknowledgement | Selected |
| Run the supplied synchronous SDK in a worker thread | Reuses its client and dispatcher directly | Requires thread-to-event-loop scheduling, careful shutdown and acknowledgement coordination, plus an SDK distribution decision | Not selected |
| Start with HTTP webhooks or ship both receiving transports | Matches deployments with a public callback URL | Adds callback verification and another lifecycle before the supplied WebSocket path is usable | Deferred |

“Use the SDK” here means follow its wire envelopes and event structures, record fixtures from its examples/tests, and retain the supplied source as a development reference. The adapter will not import its client, alter its behavior, or depend on it at runtime. The independently written transport uses the standard WebSocket implementation supplied by a NoneBot driver.

## 5. Components and data flow

```text
SeaTalk WebSocket
  -> async transport: register / heartbeat / receive / acknowledge
  -> event parser -> bounded in-memory admission -> NoneBot event handling
                                                   |
                                               plugin reply
                                                   |
                                                Bot.send
                                                   |
                                message serializer -> HTTP client -> SeaTalk

Optional Alconna builder/exporter <-> adapter Message / Event / Bot
```

| Module | Responsibility |
| --- | --- |
| `adapter.py` | NoneBot registration, per-bot lifecycle, event admission, dispatch-task ownership, API dispatch |
| `config.py` | Adapter and per-bot configuration |
| `transport.py` | WebSocket envelopes, registration, heartbeat, receive loop, serialized writes |
| `api.py` | HTTP authentication, token caching, raw API requests, supported send endpoints |
| `bot.py` | Event preprocessing, recipient resolution, `send`, convenience API methods |
| `event.py` | Typed NoneBot events, identifiers, session keys, event classification |
| `message.py` | Message segments, incoming conversion, supported outgoing serialization |
| `exception.py` | NoneBot-compatible network, API, unsupported-operation, and send errors |
| `utils.py` | Small shared logging/identity helpers only where genuinely shared |
| `integrations/alconna/` | Optional loader, message builder, and exporter |

Use a normal `nonebot.adapters.seatalk` namespace package, with `py.typed`, without installing a replacement top-level `nonebot/__init__.py`. Target Python 3.10+ and NoneBot2 2.4.x through the current 2.x series; declare the minimum supported version based on the interfaces actually used. Use `nonebot.compat` where Pydantic compatibility is needed. Do not add a second configuration framework.

Require both `WebSocketClientMixin` and `HTTPClientMixin`. Explain missing driver capabilities at startup. An inbound HTTP server is not required. Each `Bot.self_id` is its configured `app_id`; `Adapter.get_name()` returns exactly `SeaTalk`.

## 6. Configuration

The top-level key is `seatalk_bots`, a list of application configurations.

| Field | Default / rule |
| --- | --- |
| `app_id` | Required nonempty string; unique within this adapter |
| `app_secret` | Required secret value; excluded from repr and adapter logs |
| `ws_url` | `wss://ws-openapi.haiserve.com/ws/bot`, from the supplied SDK |
| `api_base` | Required HTTPS base URL in v0.1; avoids assuming the HTTP environment paired with the SDK endpoint |
| `bot_seatalk_id` | Optional explicit identity for self-mention and self-message checks; never inferred from `app_id` |

Reuse NoneBot's `api_timeout` for HTTP operations. Keep implementation constants for registration timeout (15 seconds), fallback heartbeat interval (15 seconds), reconnect delay (initially 1 second, doubling to 30 seconds), and shutdown grace period (10 seconds). Add public tuning settings only when a demonstrated deployment need justifies them.

Both service URLs are explicitly configurable for test environments. Examples use placeholders for secrets and explain how to choose the matching HTTP environment. Do not make calls to a configured service until NoneBot starts the adapter.

## 7. Connection and delivery behavior

### Lifecycle

On startup, create one connection supervisor for each configured application. On each connection:

1. Open the WebSocket through the driver and send `register` with `app_id`, `app_secret`, and a fresh request ID.
2. Require a successful registration response and a nonempty session token within 15 seconds. Reject a conflicting application ID when the response supplies one.
3. Store the session token only for this connection, record the session ID, and call `bot_connect` after registration succeeds.
4. Start application-level heartbeat and receive tasks. Use the returned positive heartbeat interval, falling back to 15 seconds. Consume application `pong` separately from WebSocket control frames.
5. On connection loss, stop heartbeat, close the socket, clear the session token, call `bot_disconnect`, and reconnect with capped exponential delay. Reset the delay after a connection stays registered for 60 seconds.

If the server supplies a positive `heartbeat_timeout`, apply it as the maximum wait for a pong after a ping; otherwise use two heartbeat intervals. Track the oldest unanswered ping so later pings cannot postpone the deadline indefinitely. This timeout is an adapter policy: the supplied SDK exposes the server setting but does not enforce it.

Serialize all writes to the connection. A `kick` or an explicit registration rejection stops that bot's automatic reconnect loop and logs the server reason; an operator can correct its credentials/configuration and restart. This avoids repeatedly taking over a session after a deliberate kick. Temporary network errors continue reconnecting.

### Event admission and acknowledgement

Acknowledgement means **accepted by the running adapter**, not that every plugin completed successfully. This maps the SDK's successful-handler boundary to the adapter's admission handler and avoids slow plugin work delaying the connection.

- Parse/classify an event before admission and retain the original event payload. Associate it with the configured bot and reject conflicting application IDs in the envelope or payload.
- Check for duplicates before reserving capacity. Maintain at most 128 accepted, unfinished event-dispatch tasks per bot. Reserve a slot without waiting in the receive loop. If full, do not acknowledge or dispatch the new event; close the connection and reconnect normally. Recovery depends on server redelivery and is not guaranteed by this adapter.
- On successful task admission, record its deduplication key and send `ack` with the current session token and the event's `callback_id`, if present.
- Deduplicate by `(app_id, event_id)` when `event_id` is present, otherwise `(app_id, callback_id)` when available. With neither identifier, dispatch without claiming duplicate protection. A duplicate callback is acknowledged but not dispatched again.
- Keep pending keys until their tasks complete. Keep completed keys in a per-bot cache capped at 4,096 entries with a 10-minute retention period. Preserve this cache across reconnects, not process restarts.
- Do not mark malformed known events as accepted. Log their event type and correlation IDs, leave them unacknowledged, and continue receiving. Structurally valid unknown event types become generic events and are admitted normally.
- If acknowledgement fails after admission, retain the admitted task and deduplication key. A redelivery can then be acknowledged without running the same handler again during the retention window.

Plugin failures are logged through NoneBot and are not automatically replayed. There is no exactly-once or crash-safe delivery guarantee: a crash after acknowledgement can lose unfinished work. These limitations belong in the README.

On shutdown, stop reconnecting and receiving, close connections, cancel heartbeat tasks, and allow already accepted event tasks up to 10 seconds to finish before cancellation. Observe task exceptions and balance each successful `bot_connect` with one `bot_disconnect`.

## 8. Events, identities, and command behavior

All events retain `event_id`, `event_type`, `timestamp`, `app_id`, `callback_id`, and the original event data. Keep WebSocket session credentials out of event objects. Preserve unfamiliar payload fields for plugin access.

| SeaTalk event | NoneBot representation |
| --- | --- |
| `message_from_bot_subscriber` | `PrivateMessageEvent`, type `message` |
| `new_message_received_from_group_chat` | `GroupMessageEvent`, type `message` for normal message tags |
| `new_mentioned_message_received_from_group_chat` | `GroupMessageEvent`, with explicit bot-addressed metadata |
| `new_message_received_from_thread` | `ThreadMessageEvent`, a group-message specialization |
| `interactive_message_click` | `InteractiveMessageClickEvent`, type `notice`; preserve action value and source identifiers |
| `user_enter_chatroom_with_bot` | Chat-entry notice |
| `bot_added_to_group_chat`, `bot_removed_from_group_chat` | Bot membership notices |
| `group_chat_converted_to_external_group` | Group conversion notice |
| `edit`, `recall_msgs`, `change_members`, `group_removed` message tags | Typed mutation notices, preserving the enclosing payload |
| Unrecognized event type | Generic event, type `notice`, original platform event name preserved |

Message edits and group system updates must not retrigger ordinary text-command matchers. Unknown content tags inside a known message event remain opaque message segments.

`get_user_id()` uses the employee code when available. A fallback SeaTalk ID is returned as `seatalk:<id>` so it cannot be mistaken for an employee code. Events with no actor raise `ValueError` for user-ID access instead of inventing one. Keep both identifiers separately on the event; resolve outbound recipients from explicit fields, never by treating arbitrary user-ID strings as employee codes.

Session IDs contain the app ID, destination, optional thread ID, and sender, using a stable JSON-array encoding to avoid separator collisions:

- Private: `[app_id, "private", user_id, thread_id_or_empty]`.
- Group: `[app_id, "group", group_id, thread_id_or_empty, user_id]`.

Private messages and explicit mentioned-group events are addressed to the bot. Other group/thread messages are addressed to the bot only when a verified mention matches `bot_seatalk_id`, or a leading configured NoneBot nickname matches. Preserve `original_message` before removing a recognized leading bot mention/nickname for command parsing. Never treat any user mention as a bot mention, or equate a SeaTalk user ID with the application ID. If the bot mention cannot be identified reliably, keep the text intact.

Where `bot_seatalk_id` is configured, ignore messages whose sender is that bot to avoid self-reply loops. Do not discard other bots solely because they have a bot sender type.

## 9. Messages and sending

Provide `Message` and `MessageSegment` with normal NoneBot concatenation, filtering, `is_text()`, and plain-text extraction. Supported segment factories:

| Segment | Contents | v0.1 behavior |
| --- | --- | --- |
| `text` | Text content | Receive and send; plain text is the default |
| `at` | SeaTalk/employee identity and display information | Receive; send when the verified API supports that recipient identity |
| `reply` | Quoted message ID | Receive; send as request metadata for supported destinations |
| `image`, `file`, `video` | Incoming URL, name, and available metadata | Receive and expose; no automatic download or re-upload |
| `card`, `forward` | Original structured payload | Receive as opaque structured content |
| `raw` | Unknown tag and original payload | Preserve incoming content; reject high-level sending |

For group text, use `plain_text`; for private text, use `text.content`, as represented in the supplied SDK. Convert verified mention spans into ordered `text` and `at` segments. The mention-offset evidence task must cover non-ASCII and supplementary Unicode characters. Invalid spans preserve the original text and mention metadata without speculative slicing. Nontext segments render a readable marker and never contribute their raw JSON or media URL to `extract_plain_text()`.

`Bot.send(event, message, **kwargs)` resolves a private employee recipient or group destination from the event. For a group-thread event it preserves the thread ID. Missing recipient information is an explicit error; do not query a directory or fall back to sending to a different destination. Interactive-click notices may be replied to only when their source destination is present.

High-level sending accepts one text body, optionally containing supported mentions and one reply segment. Merge adjacent text segments and serialize supported mentions. A reply segment identifies a quote; it does not change the destination. Reject conflicting quote IDs or destination parameters. Quoting is opt-in and distinct from preserving a thread destination. Do not automatically quote every reply.

Validate the complete message before making a request. Reject media, cards, forwarded content, unknown segments, empty content, and unsupported combinations with `UnsupportedMessage`; do not silently drop them, stringify them as chat text, or partially send a mixed message. Respect verified platform size limits and report oversized text instead of adding an automatic splitter.

Expose `send_private_message`, `send_group_message`, and `request_api` through `bot.call_api` and convenience methods. `request_api` accepts an HTTP method, a relative API path, and query/body parameters; authentication and the configured origin stay under adapter control. Unknown API method names raise `ApiNotAvailable`.

Successful high-level sends return `SendResult(message_id, destination, thread_id, raw_response)`. Only populate identifiers actually supplied by the platform. Keep `message_id` optional if the verified endpoint does not return one; never manufacture a message receipt ID. The raw API method returns the decoded platform response.

## 10. HTTP authentication and errors

Keep the HTTP application access token separate from the WebSocket session token. Do not assume they are interchangeable. Cache HTTP tokens per bot, protect refresh with an async lock, and refresh before the expiry specified by the verified API contract. A refresh failure is surfaced to the caller.

Use NoneBot's HTTP driver and timeout. After validating transport status and response shape, translate platform non-success codes into `ActionFailed` carrying the code, server message, API operation, and safe request identifiers. Map connection and timeout failures to `NetworkError`; unsupported high-level operations have a distinct adapter exception.

Do not automatically retry message sends after timeouts or ambiguous network failures, because delivery may already have happened. A clearly documented authentication rejection may invalidate the cached token, but v0.1 surfaces the rejected operation rather than replaying it automatically. Rate-limit failures are returned with available retry metadata; no background retry queue is added.

Logs include app ID, event/callback ID, request ID, event type, and reconnect reason when available. Adapter-owned default logs exclude secrets, tokens, authorization headers, full message bodies, and unfiltered payload dumps. NoneBot/plugins control their own logging; the adapter's event descriptions use identifiers and content types rather than message bodies. Parser errors identify the failing field/type and retain exception chaining for diagnosis.

## 11. Optional Alconna compatibility

The base adapter must import and run without Alconna installed. Package the bridge in an `alconna` optional dependency extra. Select and declare a tested Alconna version range in the implementation plan after checking the installed package, rather than assuming the inspected upstream branch is a release.

Two compatibility levels are required:

1. Standard text command matching using the adapter's `Message`, text extraction, event/session methods, and `to_me` preprocessing.
2. A packaged UniMessage builder/exporter registered through the `n-p-alc.uniseg.adapters` entry-point group. Convert native text, mentions, quotes, and incoming media to universal segments. Export only the text/mention/quote combinations supported by `Bot.send`; unsupported media sending raises an explicit serialization error.

Keep the entry-point loader importable without importing Alconna at module top level. Instantiate the actual builder/exporter only when Alconna loads the integration. Use the exact adapter key `SeaTalk` and lazy optional imports, without modifying Alconna's installed files or global enum definitions.

The inspected loader indexes adapters by `loader.get_adapter().value`; a local string-enum key can provide `SeaTalk` at this boundary. Its interoperability with the released loader must be covered by a real integration test. Any narrow typing accommodation belongs only at this boundary. If the supported release rejects external keys, stop and revise the integration design rather than patching its enum at runtime.

For explicit proactive targets, use `Target(..., adapter="SeaTalk")` and an explicit bot where necessary. Private targets contain employee codes; group targets contain group IDs; carry thread IDs in target extra metadata. Return a message ID only when the send result contains one. Do not advertise recall, edit, or target enumeration capabilities.

Alconna's inspected `Target.load` converts adapter strings back into its built-in `SupportAdapter` enum, which currently lacks SeaTalk. Persisted-target round trips and built-in scope selection are therefore excluded from the local bridge's guarantee and documented as candidates for a future upstream contribution. Basic command and UniMessage tests must run without needing that contribution.

## 12. Verification and release acceptance

Use a small fake WebSocket peer and fake HTTP responses to exercise the adapter boundary. Use SDK examples/test payloads as protocol references, checking their provenance before copying fixtures. Do not retest Python socket framing or add tests that merely duplicate every field definition.

Required automated coverage:

- Successful registration, heartbeat/pong timeout, reconnect, kick handling, and shutdown with no orphan tasks.
- Event admission, duplicate callback acknowledgement, acknowledgement failure followed by redelivery, and a full admission limit without blocking heartbeat processing.
- A private text command/reply and a mentioned group command/reply through NoneBot, including a non-ASCII mention fixture once the offset contract is verified.
- A thread event keeps its destination and session separate from the parent group and other users.
- Mutation/unknown events retain data without triggering normal text commands; incoming nontext segments remain distinguishable from text.
- HTTP token reuse/concurrent refresh, a platform error, a network failure without automatic resend, and unsupported outgoing content rejected before any send.
- Base adapter import without Alconna; with the extra installed, entry-point discovery, text command parsing, UniMessage conversion/sending, and explicit private/group/thread targets.
- Two configured bots do not share credentials, connection tokens, HTTP token caches, sessions, or deduplication state.

Run formatting/lint checks, the focused test suite, and a wheel build. Install the built wheel in a clean environment to prove no undeclared local SDK dependency exists and the optional entry point is packaged. Test the lowest declared and a current supported Python/NoneBot combination; do not claim broader compatibility solely from permissive dependency metadata.

Live acceptance uses a designated test app: private command/reply, mentioned group command/reply, group-thread reply, and disconnect/reconnect. This requires matching environment credentials and permission to send to test destinations. If unavailable, report automated validation separately and label the release as not live-verified.

User-facing documentation must explain driver selection, SeaTalk event subscriptions and permissions, the paired service URLs, bot identity configuration, supported message directions, acknowledgement limitations, and Alconna's scope. It must include a minimal echo plugin and a runnable configuration example without embedded secrets.

## 13. Repository and handoff

Initialize the repository and configure `origin` to the supplied remote. Commit this spec only at the design stage. Keep the supplied SDK files intact; do not automatically include them in the adapter wheel or a public source release. Before redistribution, establish the license/provenance of any supplied material included in commits or test fixtures.

This document authorizes no deployment, package publication, external message send, or upstream PR. Those are separate actions from local implementation.

After the user approves this written spec, create the implementation plan. Its first task resolves the external contracts listed in section 2, then covers core models, transport, HTTP sending, NoneBot behavior, optional Alconna integration, and package/documentation verification. The plan must be presented for review and an execution method selected before product implementation begins.
