# Implementation decisions and handoff

Implemented on `feat/seatalk-adapter`, based on `main`. Both review passes were read-only. The receiving-core review found four issues fixed with failing-then-passing regression tests; the completion review found no actionable issues. The completion review deliberately excluded previously reviewed receiving code.

## Decisions in execution order

Earlier blocked-checkpoint decisions are retained here as history; authenticated documentation subsequently unblocked sending and Alconna. Current limitations are in README.

- Task 2: Ruling: source tests append the local adapter search path, disabled for clean-wheel checks — both Hatchling and uv_build editable installs add only the root; official Feishu tests explicitly extend nonebot.adapters.__path__. Retain planned Hatchling after investigating both — cost if wrong: installed-wheel checks must catch hidden packaging defects.
- Task 2: Ruling: session-scoped asyncio fixture/test loops match NoneBug session fixtures — function default caused ScopeMismatch before tests ran — cost if wrong: integration tests could share loop state; adapters own cleanup.
- Final: minor (deferred): enrich reconnect/rejection/handler logs with more safe correlation IDs and diagnostic detail; current logs retain application IDs and exception categories.
- Final: Ruling: Unicode mention slicing remains unimplemented until offset units are verified — preserve text/metadata rather than guess — cost: native leading mentions cannot yet be stripped for commands.
- Final: Ruling: HTTP contracts, raw-API origin checks, token refresh and reply sending remain blocked, not accepted as complete — absent primary evidence — cost: this checkpoint cannot send messages.
- Final: Ruling: Alconna loading/conversion/fallback remains pending task6 — test the eventual bridge against real sending interfaces — cost: no Alconna compatibility claim at this checkpoint.
- Final: Ruling: independently validate base wheel and version floor while final release docs/Alconna packaging remain pending — useful verification without claiming release readiness — cost: repeat distribution checks after those later features change the artifact.
- Final: Ruling: live SeaTalk/redelivery verification remains unavailable without authorized test credentials/destinations — only automated peer tests are claimed — cost: environment-specific behavior remains unverified.
- Tasks 1/2: Ruling: official docs specify username mappings but no offset units; convert unique nonoverlapping literal @username mappings and preserve ambiguous text/metadata, regardless of undocumented offsets — no slicing unit is guessed — cost: repeated usernames remain text. This supersedes the earlier offset blocker and adjusts the Unicode fixture to documented fields.
- Task 6: Ruling: private threads are documented and supported; private quotes are undocumented and rejected — cost: private quoting remains unavailable even if some backend accepts it. HTTP evidence now unblocks tasks6–7.
- Task 7: Ruling: strict export validation raises native UnsupportedMessage instead of SerializeFailed — Alconna0.62.1 UniMessage.export catches SerializeFailed even above the exporter and silently returns FallbackMessage; no upstream patching — cost: callers must catch UnsupportedMessage for rejected content. Missing receipt IDs still raise SerializeFailed. This preserves the specification's no silent media conversion rule.
- Final review scope ruling: receiving core was already reviewed/fixed at9cdd025; review remaining delta955d0c5..HEAD only, per user prohibition on repeated review of checked code. Cost: whole-branch assurance combines the prior receiving-core review with this completion review.
- Final: Ruling: previously reviewed receiving core remains excluded from repeat review — user explicitly prohibits repeat review; prior four fixes remain tested — cost: combined review evidence spans two checkpoints.
- Final: Ruling: live endpoint pairing/rendering/delivery/reconnect remains unverified — documentation access authorizes no live sends — cost: production interoperability must be checked on a designated app.
- Final: Ruling: private quoting, outgoing media, persisted Alconna targets, recall/edit and enumeration remain unsupported as specified — no invented platform or integration capabilities — cost: users needing these features require future work.

## Verification

- Final runtime source suite: 117 tests passed including artifact checks and Alconna.
- Installed wheel, Python3.10 / NoneBot2.4 / Pydantic1: 98 passed, optional Alconna module skipped.
- Installed wheel, Python3.14 / NoneBot2.5 / Pydantic2: 98 passed, optional Alconna module skipped; five pytest-asyncio deprecation warnings.
- Installed wheel, Python3.12 / NoneBot2.5 / Alconna0.62.1: 117 passed.
- Ruff lint/format, wheel/sdist, and diff whitespace checks passed.
- No live send, push, merge, or publication performed. Documentation cookie scratch file removed.

## Live acceptance still open

- [ ] Confirm matching REST/WebSocket endpoints and app permissions.
- [ ] Private text reply.
- [ ] Mentioned group reply and rendering.
- [ ] Thread reply.
- [ ] Reconnect and platform redelivery behavior.
