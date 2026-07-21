# SteamTime — Home Assistant Integration: Technical Design v1

*Port of the SteamTime Android technical design (v3, Flutter/Firebase) to a Home Assistant custom integration. This document is the implementation contract: it is written to be directly consumable by an implementation agent. Read `docs/prd-scope-map.md` alongside it for what was kept, transformed, or dropped from the original PRD.*

---

## 1. What the platform change dissolves — and what survives

The Android design spent most of its complexity budget on problems Home Assistant solves natively. Understanding this mapping prevents an implementation agent from faithfully re-porting machinery that no longer has a reason to exist:

| Android design (TD v3) | Why it existed | HA replacement |
|---|---|---|
| Foreground service + isolate boundary (§3, §6) | Phone OS kills backgrounded apps | HA is an always-on server; the engine runs in HA's event loop |
| Exact-alarm fallback + grace offset + setup screen (§6.1, §6.4) | Doze/OEM battery killers | Not needed; `async_track_point_in_time` in a server process |
| Command inbox (one file per command) (§5.5) | Multi-isolate write race | Not needed; single event loop. Services/buttons dispatch directly |
| State file + crash recovery (§5.5) | Process death mid-cook | **Kept in spirit**: `Store` helper + restore-and-fast-forward on HA restart (§5) |
| Firebase Auth / Google Sign-In (§7) | User identity | Dropped; HA's own users are the identity layer |
| Firestore + security rules (§4, §10) | Cloud data + multi-tenant access control | Dropped; single-household local `Store`. The entire rules layer has no equivalent and no replacement is needed |
| Cross-device sync (§9) | Data stuck on one phone | Dropped; every HA frontend shows the same server state |
| Share links / App Links / import sanitization (§8) | Cross-*account* sharing | Dropped for POC (see scope map; a YAML export could return post-POC) |
| Notification action buttons via plugin (§6.3) | Confirm from lock screen | Companion-app **actionable notifications**, wired by a shipped automation blueprint (§7) |
| Flutter UI screens | The app *was* the UI | Entities on a dashboard + services; no custom frontend for the POC |

**What survives, nearly verbatim:** the §5 sequencing engine — the descending-sort offset calculation, the per-dish `pending → readyToAdd → cooking → done` state machine, the late-add rule (each dish's `doneAt` derives from its own `confirmedAt`, never the plan), timestamp-based state with fast-forward recovery, completion-snapshot history semantics, and cancellation writing nothing to history. That engine is the product; everything else in this document is HA plumbing around it.

## 2. Architecture

A custom integration, domain `steamtime`, single config entry. Layers, with a strict dependency rule — **HA code depends on the engine; the engine depends on nothing**:

- **`engine/`** — pure Python, no `homeassistant.*` imports, no I/O, no clocks of its own (time is always passed in). Sequencing math, state machine, serialization to/from a plain dict (§3).
- **Runtime (`session_manager.py`)** — owns the live engine instance inside HA: arms/cancels `async_track_point_in_time` callbacks for the engine's next due target, persists state on every transition, fires HA events, and notifies entities via dispatcher signals. This is the *only* writer of session state.
- **Entities (`sensor.py`, `binary_sensor.py`, `button.py`)** — render engine state; never mutate it except by dispatching the same commands a service call would.
- **Services (`services.py`)** — the command surface (§6).
- **Storage (`storage.py`)** — three `Store` objects: dish library, live session, history (§5).
- **Blueprint (`blueprints/automation/steamtime/steamtime_notify.yaml`)** — actionable-notification wiring, shipped in the repo and referenced in the README (§7).

## 3. Sequencing engine (ported from TD v3 §5)

All times inside the engine are **epoch UTC seconds (float)** — never local wall-clock, never remaining-time counters. The engine is a function of `(state, command | now)` → `(state', effects)` where effects are declarative (`fire_add_alert(dish)`, `fire_done_alert(dish)`, `session_completed`) for the runtime to execute.

### 3.1 Sequencing

Given selected dishes sorted descending by steam time (`t_1 ≥ … ≥ t_n`), each dish gets a planned add-offset computed once at session start:

```
plannedOffset_i = t_1 − t_i
```

Dish 1's offset is 0, so its add-alert fires immediately at session start. Every dish — including the first — goes through the identical confirm-then-countdown flow; no special-casing. If every dish is confirmed exactly on its planned offset, all countdowns end at `sessionStart + t_1`. Dishes with equal steam times get equal offsets and become `readyToAdd` simultaneously — each fires its own add event; there is no merging.

Each dish instance gets a session-scoped id (`d1`, `d2`, … in sequence order) so the same library dish can appear twice in one session and be confirmed individually.

### 3.2 Per-dish state machine

| Status | Meaning | Transition |
|---|---|---|
| `pending` | Planned add-offset not yet reached | → `readyToAdd` when `sessionStart + plannedOffset_i` passes |
| `readyToAdd` | Add-alert fired; waiting for user confirmation | → `cooking` on confirm (service, button, or notification action) |
| `cooking` | Countdown from the **actual** confirmation timestamp | → `done` when `confirmedAt + t_i` passes |
| `done` | Done-alert fired | Terminal |

`doneAt` always derives from the dish's **own `confirmedAt`**, never from the planned offset. This single rule is the late-add handling: a late confirmation shifts only that dish's finish later; `plannedOffset` values for still-`pending` dishes were computed once and are never recalculated, and `cooking` dishes run independently. A dish left in `readyToAdd` waits indefinitely — no timeout, no auto-confirm.

The confirm command carries the timestamp of the user action (the service call / notification-action time), and the countdown starts from **that** timestamp — so processing latency never skews cooking time.

### 3.3 Completion and cancellation

When every dish reaches `done`, the runtime writes a history entry (§5) — a **frozen snapshot** of each dish as configured: name (en + nl if present), the *actual* steam minutes used including any per-session adjustment, temperature, category — then clears the live-session store and fires `steamtime_session_completed`. Later edits or deletion of a library dish never affect history.

`cancel_session` tears everything down — cancel timer callbacks, clear the live-session store, fire `steamtime_session_cancelled` — and **writes nothing to history**. Completed sessions only.

### 3.4 Fast-forward evaluation

The engine exposes `advance(state, now)` which fires every transition whose target timestamp is ≤ `now`, in chronological order, returning all resulting effects. The runtime calls this (a) from each timer callback and (b) once on restore after an HA restart (§5.2). Because state is timestamps, an HA that was down for 20 minutes catches up in one call: dishes whose `doneAt` passed transition straight to `done` and their (late) events fire on restore. This is TD v3 §5.5's recovery fast-forward, minus the process-death machinery around it.

The runtime never runs a 1-second tick loop. After each `advance`, it arms exactly one `async_track_point_in_time` callback for the earliest future target (or none if the session awaits only confirmations).

## 4. Entity model

One device ("SteamTime") under the config entry, holding:

| Entity | Type | State | Key attributes |
|---|---|---|---|
| `sensor.steamtime_session` | sensor | `idle` \| `running` | `session_id`, `started_at`, `dishes`: list of `{id, name, status, planned_add_at, confirmed_at, done_at, steam_minutes, temperature}` (timestamps as ISO UTC) |
| `sensor.steamtime_next_add` | sensor, `device_class: timestamp` | When the next dish should be added (earliest `pending` target; if a dish is `readyToAdd`, that past timestamp — i.e. "now") | `dish_id`, `dish_name`, `temperature` |
| `sensor.steamtime_next_done` | sensor, `device_class: timestamp` | Earliest `doneAt` among `cooking` dishes | `dish_id`, `dish_name` |
| `binary_sensor.steamtime_awaiting_confirmation` | binary_sensor | `on` when ≥ 1 dish is `readyToAdd` | `dish_ids` |
| `button.steamtime_confirm` | button | Confirms the **oldest** `readyToAdd` dish (convenience; the precise path is the service) | — |
| `button.steamtime_cancel` | button | Cancels the session | **Registry-disabled by default** (destructive; users enable it deliberately and should add a dashboard confirmation) |

Timestamp sensors are deliberate: dashboard cards render live countdowns from a timestamp natively, so UI smoothness never depends on entity update frequency — the HA equivalent of TD v3's "snapshots carry targets, not remaining-seconds." When no session is running, the timestamp sensors and binary sensor report `unknown`/`off`; buttons no-op with a log line.

Live-status view (PRD US-10) = the session sensor's `dishes` attribute on any dashboard (a markdown or custom card can pretty-print it; not part of the integration for the POC).

## 5. Storage & restart recovery

Three `homeassistant.helpers.storage.Store` objects, all versioned:

1. **`steamtime.dishes`** — the user's custom dishes: `{id, name, steam_minutes, temperature, category}`. Predefined dishes are *not* stored here — they ship as `dishes_predefined.json` inside the integration (§8), merged in memory at load. Custom dish ids are prefixed (`custom_…`) so they can never collide with predefined ids across integration updates.
2. **`steamtime.session`** — the live session: the engine state dict, written **on every state transition, before the transition's events are fired** (session start, dish ready, dish confirmed, dish done, completion, cancellation → cleared). Not written on timer arms — state is timestamps, so there's nothing to save between transitions.
3. **`steamtime.history`** — completed-session snapshots, newest first, capped at 50 entries (oldest dropped). Entry: `{id, completed_at, dishes: [frozen snapshot]}`.

**Restart recovery (§5.2 of this doc, the critical path):** in `async_setup_entry`, load `steamtime.session`. If a non-completed session exists: reconstruct the engine from it, call `advance(state, now)` once — firing any events that came due while HA was down (late, but fired; the blueprint delivers late notifications, which beats silence) — persist, re-arm the next callback, and update entities. A session must survive `ha core restart` mid-cook with nothing lost except timeliness of alerts that fell inside the downtime window. Losing the session is a critical bug.

Writes are awaited before effects observable to the user (events, entity updates) are emitted, so a crash between persist and effect replays the transition on restore rather than losing it — `advance` transitions are idempotent replays by construction (same timestamps in, same state out). Duplicate *events* after an ill-timed crash are acceptable; lost state is not.

## 6. Services & events (public API — breaking changes must be flagged)

### Services

| Service | Fields | Behavior |
|---|---|---|
| `steamtime.start_session` | `dishes`: list, each either `{dish_id, minutes?}` (library reference with optional per-session time override — PRD US-6) or `{name, minutes, temperature?}` (inline one-off dish) | Rejects if a session is already running. Builds the sequence, persists, fires the first add event(s) immediately |
| `steamtime.confirm_dish` | `dish_id` (session-scoped, e.g. `d2`) | `readyToAdd → cooking` from the call timestamp. Idempotent: confirming a non-`readyToAdd` dish is a warning no-op, not an error — a double-tapped notification action must not raise |
| `steamtime.cancel_session` | — | §3.3 |
| `steamtime.add_dish` / `steamtime.update_dish` / `steamtime.remove_dish` | dish fields / `dish_id` | Custom-dish library CRUD. Validation mirrors the original rules layer: name 1–100 chars, minutes int 1–600, temperature 1–250, category in `{vegetables, fish, meat, other}`. Predefined dishes are immutable — `update`/`remove` on a predefined id is an error |
| `steamtime.get_dishes` | — (`supports_response`) | Merged predefined + custom library, for scripts/dashboards |
| `steamtime.get_history` | — (`supports_response`) | The history list |
| `steamtime.restart_session` | `history_id` | Starts a new session from a history entry's frozen snapshot (PRD US-18); normal sequencing flow |

### Events (HA bus)

| Event type | Data | Fired when |
|---|---|---|
| `steamtime_add_dish` | `session_id, dish_id, dish_name, temperature, steam_minutes` | A dish enters `readyToAdd` |
| `steamtime_dish_done` | `session_id, dish_id, dish_name` | A dish enters `done` |
| `steamtime_session_completed` | `session_id, history_id` | All dishes done |
| `steamtime_session_cancelled` | `session_id, dish_ids` | Cancellation. `dish_ids` lists dishes that were `readyToAdd` at cancellation time, so the blueprint can clear their stale add-notification tags without racing the (already-cleared) session state |

Events are the automation surface: the blueprint consumes them, and users can hang anything else off them (TTS announcements, light flashes) without the integration knowing.

## 7. Notifications (replaces TD v3 §6 entirely)

The integration itself sends **no notifications** — it fires events. Delivery is a shipped automation **blueprint** (`blueprints/automation/steamtime/steamtime_notify.yaml`) the user imports once and points at their `notify.mobile_app_*` service(s). The blueprint:

1. Triggers on `steamtime_add_dish` → sends an actionable companion-app notification ("Add *{dish}* to the oven — {temperature} °C") with a **Confirm added** action button, `tag: steamtime_{dish_id}` so it can be updated/cleared.
2. Triggers on `mobile_app_notification_action` for that action → calls `steamtime.confirm_dish` with the dish id carried in the action payload. The confirmation timestamp is the trigger time, so countdown accuracy survives any automation latency.
3. Triggers on `steamtime_dish_done` → sends "*{dish}* is done"; on `steamtime_session_completed` → sends a completion summary; clears stale `readyToAdd` notifications on cancel.

Blueprint inputs: notify target(s), whether add-alerts are critical/high-priority, optional media_player for a chime. This split (integration fires events, blueprint delivers) is the design's biggest idiomatic win: lock-screen confirm buttons — the thing that required a foreground service, a command inbox, and an exact-alarm fallback on Android — is companion-app standard behavior wired in ~60 lines of YAML the user can customize freely.

## 8. Dish data, config flow, localization

**Predefined dishes** ship as `dishes_predefined.json` in the integration: `{id, name_en, name_nl, steam_minutes, temperature, category}`. Content is compiled by the product owner (per the PRD); the agent creates the file with ~10 placeholder dishes and a schema comment, and never invents "real" steam times beyond obvious placeholders. Display name resolution: `name_nl` when HA's language is Dutch and the field is present, else `name_en` — custom dish names are shown as typed, untranslated (same policy as TD v3 §11).

**Config flow:** single instance (`single_config_entry`), no user-entered fields — just confirm-and-create. No options flow for the POC (the dish library is managed via services, not options — a list-of-objects library is a poor fit for options-flow forms). No YAML configuration.

**Localization:** all integration strings (config flow, entity names, service descriptions, event-adjacent text used by the blueprint defaults) in `strings.json` + `translations/en.json` and `translations/nl.json`. Category display labels are translation keys, never stored display text.

## 9. Build order

Each step ends with quality gates green (see CLAUDE.md):

1. **Engine** (`engine/`) — pure Python: sequencing, state machine, `advance`, serialization. Unit tests with synthetic clocks, including late-add and "HA was down for N minutes" fast-forward scenarios. *No HA imports, no HA fixtures.*
2. **Storage** — the three stores, versioned schemas, dish-library merge with the bundled JSON.
3. **Integration skeleton** — manifest, config flow (single instance), setup/unload, device.
4. **Session manager** — engine hosting, point-in-time callbacks, persistence-before-effects, restart recovery. Integration tests: start → restart-HA-simulation (reload entry) → state intact and fast-forwarded.
5. **Services** — full command surface, schemas, `supports_response` queries, validation.
6. **Entities** — sensors, binary sensor, buttons, dispatcher wiring.
7. **Events + blueprint** — event payloads finalized, blueprint YAML written and manually tested end-to-end with a real companion app.
8. **History & restart-from-history.**
9. **Polish** — translations complete, README (install via HACS custom repo, blueprint import, dashboard example), diagnostics platform (redact nothing — no personal data exists beyond dish names).

Steps 1 and 7 are the risk concentration (§11) — front-load them.

## 10. Adversarial review prompts (run before calling a milestone done)

- What happens if HA restarts (a) between a dish's `readyToAdd` transition and its event firing, (b) while a dish is `cooking`, (c) after completion but mid-history-write?
- What happens when `confirm_dish` arrives for an already-`cooking` dish (double-tapped notification), for an unknown id, or with no session running?
- What happens when `start_session` is called while a session runs? When the dish list is empty, has 25 dishes, or references a deleted custom dish?
- Which code paths could block the event loop? Which awaited store writes could interleave with a second service call (are transitions serialized)?
- Does `async_unload_entry` cancel the armed callback and dispatcher listeners? Does reloading the entry resume the live session?
- If a user edits a custom dish mid-session, is the running session unaffected (it must be — the session holds copies, not references)?

## 11. Risks & Week-1 spike

The Android design's dominant risk (OEM background killing) is gone. The HA version's risk concentration is different and smaller:

1. **Actionable-notification round trip** — companion-app action → `mobile_app_notification_action` event → `confirm_dish`, on both Android and iOS companion apps, including from a locked phone. This is user-facing step zero; if it's flaky, the product's core interaction is flaky. **Spike:** build step 1 (engine) plus a throwaway script-started fake session with 1–3-minute dishes and the blueprint; validate the round trip on real phones before building entities/services fully.
2. **Restart recovery correctness** — covered by tests in step 4, but validate once on a real HA (`ha core restart` mid-session).
3. **Watchlist, not risk:** HACS default-store requirements (repo metadata, docs) — handle at publication, the analog of the original's Play Store milestone.

---

*Changelog: v1 — initial HA port of TD v3. Supersedes the Android technical design for all platform decisions; preserves its engine semantics (§3), history snapshot semantics, and cancellation semantics unchanged.*

*v1.1 (step 7, blueprint work) — `steamtime_session_cancelled` gained `dish_ids`: the original `session_id`-only payload gave the notification blueprint no way to know which per-dish add-notification tags to clear, and by the time an automation reacts to the event, `SessionManager` has already cleared its state and re-rendered the sensor, so there was no reliable side channel to recover that list either. Additive change to `SessionCancelledEffect` (engine) and the fired event; not a breaking change for existing consumers of `session_id`.*
