# SeaTalk contract evidence

Recorded 2026-09-27. Status: WebSocket schema verified against the supplied SDK; authenticated official HTTP and event documentation read on the same date.

## WebSocket

Source: supplied `seatalk-oapi/OPEN_PLATFORM_DEVELOPER_GUIDE.md` and Python `seatalk_oapi_sdk/{protocol,client,dispatcher}.py`, available in the original workspace. No SDK source is redistributed here.

The default endpoint is `wss://ws-openapi.haiserve.com/ws/bot`. Requests carry `cmd` and a `header` with a generated `rid`. Registration sends `app_id` and `app_secret`; success has code 0 and a nonempty `header.token`. The response may include `header.sid`, `header.app_id`, and `data.heartbeat_interval` / `data.heartbeat_timeout`. Heartbeats send `ping` with the session token; the peer sends `pong`. Events use `cmd: event`, `header.callback_id`, and an event body in `data`. Acknowledgements send `ack` with the session token and callback ID. A `kick` terminates the session.

Private events put sender fields and `message` in `event`. Group and thread events put `group_id` and `message` in `event`; sender fields are nested in `message.sender`. Private text uses `text.content`; group/thread text uses `text.plain_text` and `text.mentioned_list`. Media payloads use `content`; files also expose `filename`. Preserve media content without assuming an upload API or downloading it. Quoted messages have `quoted_message_id`; thread messages have `thread_id`.

The event fixtures are independently authored examples with invented IDs based on those schemas. They contain no real user content or credentials.

## HTTP and messages

Official articles were read using user-authorized documentation access; credentials and downloaded article bodies are not distributed.

- [Authentication](https://open.seatalk.io/docs/get-app-access-token): POST `/auth/app_access_token` with app_id/app_secret. Success has code=0, app_access_token and expire (Unix timestamp in seconds), normally valid for 7200 seconds. REST uses `Authorization: Bearer <app_access_token>`; this is independent of the WebSocket session token.
- [Private sending](https://open.seatalk.io/docs/messaging_send-message-to-bot-user_): POST `/messaging/v2/single_chat`, recipient employee_code. Message contains tag=text and text={format:2,content:...}. Text is 1–4096 characters. Optional message.thread_id supports private threads. Text success example is only `{code:0}`: no fabricated message ID. Private quoting is not documented, so the convenience API rejects it.
- [Group sending](https://open.seatalk.io/docs/Send-Message-to-Group-Chat): POST `/messaging/v2/group_chat`, recipient group_id; same text body. Optional message.thread_id and message.quoted_message_id are distinct. A thread ID can identify the root message to start a thread. Root/quoted messages must be within seven days. Group success includes message_id.
- [Formatting](https://open.seatalk.io/docs/format-a-message): format=1 enables Markdown and group mention tags `<mention-tag target="seatalk://user?id=123"/>`. Only SeaTalk-ID user mentions are exported; employee codes are not mention IDs. Ordinary text uses format=2; text accompanying mentions is Markdown escaped. Mention-all and private mentions are outside the initial convenience API.
- [Errors](https://open.seatalk.io/docs/reference_server-api-error-code_): HTTP 200 can contain a nonzero code. Code 100 means invalid/expired token; 101 rate limit; 102 invalid input; 103 permission denied; 1000 invalid app secret. Invalidate a rejected token without replaying the send. Group limit is 100/minute and 20/second, private 300/minute and 20/second per app. No built-in retries. Retry-After/request identifiers are exposed if present; the docs do not promise these headers.
- [Incoming messages](https://open.seatalk.io/docs/Introduction-to-Received-Message-Types) and [group mentions](https://open.seatalk.io/docs/event_new_mentioned_message_from_group_chat): mentions render as `@` plus username, mapped to SeaTalk ID by mentioned_list. These official tables do **not** specify location/length or their units, although the supplied SDK has optional fields. Conversion therefore locates only unique, nonoverlapping literal username mappings; ambiguous/missing names preserve the full text and metadata. No offset unit is assumed. Media content is a URL requiring an API token, expiring after seven days; the adapter preserves it without downloading.
- [SeaTalk IDs](https://open.seatalk.io/docs/SeaTalk-ID): a bot's SeaTalk ID is on the portal's App → Bot page; it is distinct from app_id and employee_code.
- [WebSocket setup](https://open.seatalk.io/docs/WebSocket-Event-Callback): connect first, then select WebSocket under Event Callback and re-verify while connected.

Public REST examples use `https://openapi.seatalk.io`, now the default `api_base`; deployments can override it. Pairing credentials for that origin with the SDK's haiserve socket endpoint remains a deployment verification item. No live sends or production redelivery experiments have been performed.

Fixtures use invented IDs and dummy secrets. HTTP error fixtures model the documented code envelope; optional headers in tests are synthetic robustness cases, not asserted platform guarantees.

## Outgoing image implementation (2026-10-11)

Authenticated official [group sending](https://open.seatalk.io/docs/Send-Message-to-Group-Chat)
and [private sending](https://open.seatalk.io/docs/messaging_send-message-to-bot-user_)
articles were read with user-authorized access on 2026-10-11. Session credentials and
downloaded article bodies are not distributed.

The implementation uses the documented group/private endpoints and destination metadata,
with one `message={tag:"image",image:{content:"<base64>"}}` per image. Contiguous text and
individual images are sent sequentially because a request contains one typed message.
Results retain the actual message IDs returned by each request. No live image send has
been performed. The official
[SeaTalk cs-bot SDK](https://github.com/seatalk-io/cs-bot/blob/main/cs_bot/libs/seatalk_openapi/client.py)
also confirms the image body for private sending (`__assemble_chat_message` and
`send_single_chat_message`). Both official article tables allow PNG/JPG/GIF and specify
a maximum of 5 MB after base64 encoding. The adapter conservatively interprets this as
5,000,000 encoded bytes inclusive, since the article does not define decimal/binary MB.

Group image tables explicitly support `message.thread_id` and `message.quoted_message_id`;
group responses expose `message_id`. Private image examples have no guaranteed message ID.
Private `thread_id` is documented in the text section, not repeated in the image table;
the adapter preserves an explicitly supplied private thread, with actual server support
for that image combination still pending live verification. Mocked requests prove
implementation behavior and contract serialization, not successful live delivery.

Public HTTP(S) image downloads never use the bot's token. Received media is marked as
authenticated and round-tripping it through Alconna preserves that marker. Forwarding
those URLs is explicitly rejected: NoneBot's HTTP request interface does not expose
redirect controls and cannot safely carry application credentials for that operation.
Callers can send already-authorized image bytes instead.

## Automated verification

Installed-wheel checks completed on 2026-09-27: 98 tests passed on Python3.10/NoneBot2.4/Pydantic1 and Python3.14/NoneBot2.5/Pydantic2 (Alconna absent). The optional Python3.12/NoneBot2.5/Alconna0.62.1 lane passed all117 tests. The Python3.14 test runner emitted five pytest-asyncio deprecation warnings. Lint, formatting and wheel/sdist builds passed. No live SeaTalk send or reconnect was exercised.
