# SteamTime PRD → HA Integration: Scope Map

*The original PRD (`docs/reference/steam-oven-app-prd.md`) was written for a standalone Android app. Its functional intent — auto-sequenced steam timing with confirm-to-start and graceful late adds — carries over intact; its platform assumptions do not. This map is authoritative over the PRD wherever they differ. Design references point into `docs/design.md`.*

## User stories

| Story | Status | HA form |
|---|---|---|
| US-1 Browse predefined dishes | **Kept** | Bundled `dishes_predefined.json` merged with custom dishes; queryable via `steamtime.get_dishes` (design §6, §8). No browse *UI* is shipped — dashboards/scripts consume the service |
| US-2 Account / login | **Dropped** | HA users are the identity layer; the integration stores nothing per-user. Everything the PRD hung on accounts (data restore, ownership) is HA's own backup/auth concern |
| US-3 Add a custom dish | **Kept** | `steamtime.add_dish` with the same validation bounds (name 1–100, minutes 1–600, temp 1–250) (design §6) |
| US-4 Category filter | **Transformed** | Categories remain on every dish and in `get_dishes` output; filtering is the consumer's job (dashboard/script), not an integration feature |
| US-5 Search dishes | **Transformed** | Same: data exposed, search is the consumer's job. No in-integration search |
| US-6 Adjust steam time | **Kept** | Per-session override: `minutes` field on `start_session` dish entries (design §6). Permanent changes via `update_dish` (custom dishes only) |
| US-7 Single-dish session | **Kept** | Same engine path, n = 1, no special-casing (design §3.1) |
| US-8 Multi-dish session | **Kept** | `steamtime.start_session` (design §6) |
| US-9 Auto-sequencing | **Kept verbatim** | `plannedOffset_i = t_1 − t_i`, longest first (design §3.1) |
| US-10 Live status view | **Transformed** | `sensor.steamtime_session` `dishes` attribute + timestamp sensors for countdowns (design §4). Rendering is a dashboard concern; no custom frontend for the POC |
| US-11 "Add next dish" alert | **Kept** | `steamtime_add_dish` event → blueprint notification (design §6, §7) |
| US-12 Confirm dish added | **Kept** | `steamtime.confirm_dish` service, `button.steamtime_confirm`, and the blueprint's actionable-notification button — all three land on the same command (design §4, §6, §7) |
| US-13 Late-add handling | **Kept verbatim** | `doneAt` from own `confirmedAt`; other dishes untouched (design §3.2) |
| US-14 "Dish done" alert | **Kept** | `steamtime_dish_done` event → blueprint (design §6, §7) |
| US-15 Reliable background alerts | **Dissolved** | The PRD's highest technical risk does not exist on a server platform. Residual analog: alerts must survive an HA restart — restore-and-fast-forward (design §5), and the notification round trip is the new week-1 spike (design §11) |
| US-16 Favorites | **Dropped** | Favorites existed for quick access in an app UI that no longer exists. HA-side equivalents (scripts wrapping `start_session` for frequent combos, dashboard buttons) are better and free. Revisit only if a custom frontend is ever built |
| US-17 Auto session history | **Kept** | History store, frozen snapshots at completion, cancellations never logged (design §3.3, §5) |
| US-18 Restart past session | **Kept** | `steamtime.restart_session(history_id)` (design §6) |
| US-19 Cross-device sync | **Dropped** | Every HA frontend already shows the same server state; nothing to build |
| US-20 Share a session | **Dropped (POC)** | Cross-*household* sharing has no cheap HA-native equivalent (the Firebase capability-URL model doesn't port). Post-POC candidate: export/import a session as YAML/JSON via `supports_response` services. Not in scope now |
| US-21 Import a shared session | **Dropped (POC)** | Same as US-20 |

## Non-functional requirements

| PRD item | HA form |
|---|---|
| Background-alert reliability spike | Replaced by design §11: actionable-notification round trip + restart recovery |
| Platform target (Android 16/17) | Replaced: latest stable HA Core, verified at implementation time (CLAUDE.md rule 1) |
| Privacy / data minimization | Stronger by construction: fully local, no accounts, no cloud, no analytics. Data = dish names, times, timestamps in HA's own storage |
| Localization (en + nl, no hardcoded strings) | **Kept**: `strings.json` + `translations/`, `name_en`/`name_nl` on predefined dishes (design §8) |
| Tech stack (Flutter + Firebase) | Replaced: Python custom integration; no add-on, no external services |
| Play Store milestone | Replaced: HACS custom repo → HACS default store (design §11 watchlist) |

## PRD assumptions that still hold

Oven preheat remains out of scope (user starts the session when the oven is ready). No portion-based time scaling. No brand-specific data. The predefined dish database content is compiled by the product owner, not the agent. No monetization, no analytics, no content moderation.

## Assumptions that are void

Everything under the PRD's Accounts & Sync section and Firebase-specific assumptions (mandatory login, Dynamic Links/App Links, Firestore snapshotting mechanics). The *semantic* commitments they encoded — history entries are frozen snapshots; shared/cancelled-session behavior — are preserved in the design where their feature survived.
