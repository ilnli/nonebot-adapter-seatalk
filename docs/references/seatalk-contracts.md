# SeaTalk contract evidence

Recorded 2026-09-27. Status: WebSocket schema verified against the supplied SDK; HTTP and mention-offset contracts awaiting primary evidence.

## WebSocket

Source: supplied `seatalk-oapi/OPEN_PLATFORM_DEVELOPER_GUIDE.md` and Python `seatalk_oapi_sdk/{protocol,client,dispatcher}.py`, available in the original workspace. No SDK source is redistributed here.

The default endpoint is `wss://ws-openapi.haiserve.com/ws/bot`. Requests carry `cmd` and a `header` with a generated `rid`. Registration sends `app_id` and `app_secret`; success has code 0 and a nonempty `header.token`. The response may include `header.sid`, `header.app_id`, and `data.heartbeat_interval` / `data.heartbeat_timeout`. Heartbeats send `ping` with the session token; the peer sends `pong`. Events use `cmd: event`, `header.callback_id`, and an event body in `data`. Acknowledgements send `ack` with the session token and callback ID. A `kick` terminates the session.

Private events put sender fields and `message` in `event`. Group and thread events put `group_id` and `message` in `event`; sender fields are nested in `message.sender`. Private text uses `text.content`; group/thread text uses `text.plain_text` and `text.mentioned_list`. Media payloads use `content`; files also expose `filename`. Preserve media content without assuming an upload API or downloading it. Quoted messages have `quoted_message_id`; thread messages have `thread_id`.

The event fixtures are independently authored examples with invented IDs based on those schemas. They contain no real user content or credentials.

## Evidence still required

- Official token endpoint, request/response, expiry units, and failure codes.
- Private/group/thread send requests, recipient identity, quoting rules, text/mention format, size limits, and returned message IDs.
- Mention span offset units and the representation of the bot's own mention.
- HTTP base URL and credential environment paired with the supplied WebSocket endpoint.

The public documentation page rendered a landing page through retrieval tools; its article endpoint returned HTTP 401. Secondary summaries are not used as implementation contracts. No HTTP fixtures or sending implementation may be considered verified until primary evidence is supplied or retrieved.

Live verification: not performed.
