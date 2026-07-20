# Project: SteamTime — Home Assistant Integration

## What this is

SteamTime is a cooking companion for steam-oven users: the user picks the dishes they're cooking, the integration auto-sequences them (longest steam time first), tells them exactly when to add each dish, and requires confirmation that a dish was physically added before that dish's independent countdown starts. Late additions never disturb dishes already cooking.

This is a **Home Assistant custom integration** (domain: `steamtime`) — a port of a design originally written for a Flutter/Firebase Android app. It is *not* an add-on: there is no standalone daemon, the engine runs inside HA Core.

**Authoritative documents, in order:**
1. `docs/design.md` — the HA technical design. This is the implementation contract.
2. `docs/prd-scope-map.md` — maps the original PRD's user stories to what is kept, transformed, or dropped in the HA version. When the PRD and the scope map disagree, the scope map wins.
3. The original PRD (`docs/reference/steam-oven-app-prd.md`) — functional intent and acceptance criteria for everything the scope map marks as kept.

If implementation reveals the design is wrong, **stop and flag it** — do not silently diverge from the doc. Options analysis happens in conversation; the doc contains only decisions.

## Target platform

- Home Assistant Core: latest stable at implementation time (verify — HA releases monthly)
- Python: as required by that HA release
- Repo scaffolding: start from the maintained `integration_blueprint` template line (config flow, devcontainer, CI included) and strip what the design doesn't use

## Non-negotiable rules

1. **HA APIs go stale fast.** HA releases monthly and deprecates aggressively. Before using any HA API you are not 100% certain is current, check developers.home-assistant.io — never rely on training data for HA-specific APIs.
2. **The sequencing engine is pure Python.** `custom_components/steamtime/engine/` imports nothing from `homeassistant.*` and does no I/O. It is a timestamp-in, state-out state machine (design §3). Everything HA-specific lives outside it. This mirrors the original design's pure-Dart rule and is what makes the core logic unit-testable without an HA harness.
3. **All timestamps are epoch UTC.** Never local wall-clock strings, never decrementing counters. State is target timestamps; "ticking" is comparing now against targets. A missed callback or an HA restart loses nothing — the next evaluation fast-forwards (design §3.4).
4. **All I/O is async.** No blocking calls in the event loop; storage via `homeassistant.helpers.storage.Store` only.
5. **Session state survives restart.** Every engine state transition is persisted before its side effects are observable (design §5). On setup, a persisted live session is restored and fast-forwarded. Losing a cooking session to an HA restart is a critical bug, not a corner case.
6. **Entities never own state.** Entities render engine state; services and events are the only mutation paths. No entity writes to the engine directly except by dispatching the same commands a service call would.
7. Config via config flow only (single instance). Unique IDs on all entities, proper device info, clean `async_unload_entry` (cancel timers, close store, remove listeners).
8. Every user-facing string goes through `strings.json` / `translations/` (en + nl). Dish names come from the bundled dish data (en + nl fields) or user input — never hardcoded in code.
9. Events fired on the HA bus and service/attribute schemas are **public API** (the notification blueprint and users' automations depend on them). Changing an event payload or attribute name is a breaking change — flag it, don't just do it.

## Quality gates (run before declaring any task done)

- `ruff check . && ruff format --check .`
- `mypy custom_components/steamtime`
- `pytest` (uses `pytest-homeassistant-custom-component`; engine tests must pass with no HA fixtures at all)
- hassfest and HACS validation pass in CI

## Workflow

- Implement in the build order defined in design §9. Each step ends with quality gates green.
- Commit after every green quality-gate run.
- Session scope: one concern per session (engine, config flow, entities, services/events, blueprint, recovery). State the exact HA version in the devcontainer at the start of each implementation session.
- Before a milestone is called done, run the adversarial review prompts in design §10.
