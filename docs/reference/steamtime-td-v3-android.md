# Technical Design Document: SteamTime — v3

*Companion to the SteamTime PRD. Covers architecture, data model, and implementation approach for the Android POC (Flutter + Firebase). This document is written to be directly consumable by an implementation agent. Treat v3 as authoritative wherever it differs from earlier revisions.*

---

## 0. Changelog

### v2 → v3 (audit pass)

| # | Change | Type | Where |
|---|---|---|---|
| S1 | `sessions` update rule tightened: the only permitted update is toggling `isShareable` (enforced with `diff().affectedKeys()`). v2 allowed an owner to rewrite `dishes`, `origin`, and `createdAt` after creation — meaning a shared session's content could be swapped *after* the recipient inspected the link, and history entries were mutable despite §4 calling them frozen snapshots. | **Security fix** | §10 |
| S2 | `createdAt` is now validated on create (`== request.time`, i.e. the client must use a server timestamp) and `isShareable` must be `false` on create. v2 validated neither. | **Security fix** | §4, §10 |
| S3 | All create/update rules now use `keys().hasOnly(...)` to reject undeclared fields. Notably this makes it impossible for a client to write `nameNl` on a custom dish (v2's schema said predefined-only, but nothing enforced it) or to attach arbitrary extra fields to any document. | **Security fix** | §10 |
| S4 | `dishes` update rule now re-validates `temperatureCelsius` (v2's update rule silently dropped it, so an owner could update a dish and set temperature to any value/type). Temperature is now range-bounded on create and update. | Security hardening | §10 |
| S5 | Imported session data is now explicitly treated as **untrusted input**: the import flow sanitizes the fetched `dishes` array client-side before copying (Firestore rules cannot iterate array elements, so per-element validation can only happen here). | **Security fix** | §8 |
| D1 | Fixed a duplicate-notification race: v2 scheduled each fallback exact alarm at the *same instant* the foreground service fires the real notification, so on a healthy device both would fire (the service can't cancel an alarm at the exact moment it triggers). Fallback alarms are now scheduled at **target + 45 s grace**; the service cancels them when it fires the real alert. | **Design fix** | §6.1, §13 |
| D2 | Fixed a service-lifecycle gap at completion: v2 had the foreground service stop only *after* the main isolate's Firestore write, but if the user swiped the app away, the main isolate may be dead and the write can only happen on next launch — leaving the service (and its persistent notification) running indefinitely. The service now stops itself immediately after persisting the `completed` state; the history write catches up on next launch. | **Design fix** | §5.4 |
| D3 | The session's Firestore document ID is now **pre-generated at session start** and stored in the persisted state; the completion write uses `set()` on that ID instead of `add()`. This makes the history write truly idempotent even if the process dies between the write succeeding and the `writtenToHistory` flag being persisted (v2's flag alone left a double-write window). | **Design fix** | §4, §5.4, §5.5 |
| D4 | Defined app-launch behavior when a session is live: **attach** to the running service (don't reconstruct) vs. **recover** (service not running, non-completed state on disk) vs. **finish** (completed, unwritten). v2's recovery text conflated the first two. Clarified that the main isolate may *read* the state file for its initial view snapshot (single-writer rule constrains writers, not readers). | Clarification | §5.5 |
| D5 | Unified the command path: **all** commands (main isolate, notification-action isolates, alarm callbacks) go through the command inbox; `sendDataToTask` is demoted to an optional latency-reducing wake nudge. One code path, one test surface, one delivery guarantee. Commands now carry the `sessionId`; the drain discards mismatched/stale files, and leftover files are swept at session start. | Simplification / robustness | §3, §5.5, §6.3 |
| D6 | Degraded fallback when `SCHEDULE_EXACT_ALARM` is denied: schedule **inexact** alarms (`inexactAllowWhileIdle`) instead of scheduling nothing. Late is better than absent if the OEM also kills the service. | Design fix | §6.1 |
| — | Minor: favorites rules validate fields and require `dishId == {docId}`; import screen clamps and defaults invalid values; test plan extended to cover S1/D1/D3; dangling-favorite handling noted. | Hardening | §8, §10, §12 |

### v1 → v2 (retained for context — these decisions are load-bearing; do not "simplify" them away)

| Change | Type | Where |
|---|---|---|
| `dishes`: `ownerId` and `source` immutable on update (v1 allowed relabeling a custom dish as `predefined`, injecting it into the shared database). | **Security fix** | §10 |
| `sessions`: `read` split into `get` vs. `list` (v1 allowed any user to enumerate all shared sessions via `where isShareable == true`, defeating the capability-URL model). | **Security fix** | §10 |
| Session engine moved out of Riverpod into the foreground-service isolate with persisted state as source of truth (v1 was not implementable across isolates). | **Architecture fix** | §5, §6 |
| Local persistence + crash recovery; command inbox as one-file-per-command; removed unused `(source, category)` index; `nameNl` localization decision; App Links kept with plan-B; alert-reliability setup screen; epoch-UTC-ms timestamps. | Various | §3–§8, §11 |

---

## 1. Overview & Architecture Style

SteamTime is built as a layered architecture with a strict rule: **presentation depends on state, state depends on domain, domain never depends on Firebase.** Concretely:

- **Presentation** — Flutter widgets, reading and calling into Riverpod providers. No Firebase imports here.
- **State** — Riverpod providers (§3), the seam between UI and everything below it.
- **Domain** — plain Dart: the sequencing engine (§5) and data models. No Firebase or Flutter imports at all — this layer is what makes the core logic unit-testable without a device or emulator (§12).
- **Data** — repositories that wrap Firestore/Auth calls and expose plain Dart models upward. This is the only layer that knows Firestore exists.

The one deliberate exception to "state flows from Firestore" is the active session itself (§5): while a session is running, its state lives on-device only — as a persisted local session document owned by the foreground-service isolate — and is written to Firestore exactly once, at completion. This gives the app offline resilience (§9), crash recovery (§5.5), and testability (§12) with one mechanism.

**Stack recap** (from the PRD): Flutter for the client, Firebase for the backend (Auth, Firestore, Hosting). Chosen for low/no startup cost and fast POC development, with Flutter's single codebase keeping the door open for the planned iOS release without a rewrite.

## 2. Project Structure

Organized **feature-first**, with the data/domain/presentation split from §1 repeated *inside* each feature folder, rather than one giant `lib/data`, `lib/domain`, `lib/presentation` split at the root. For a solo developer working with AI coding agents, colocating everything related to one feature matters more day-to-day than a textbook-strict layering at the root — while the internal data/domain/presentation split within each feature still preserves the separation of concerns from §1.

```
lib/
  core/
    router/                 # go_router setup, deep-link route for §8
    theme/
    firebase/               # Firebase initialization shared across features
    timer_engine/           # the pure-Dart sequencing engine from §5
    session_store/          # local persistence of the active session and
                            # the command inbox (§5.5)
    notifications/          # foreground service task, alert scheduling,
                            # notification action handlers (§6)
  features/
    auth/
      data/                 # Google Sign-In + FirebaseAuth wrapper
      presentation/         # sign-in screen
    dishes/
      data/                 # dishes repository (§4)
      domain/               # dish model, category enum
      presentation/         # browse/search/filter screens, custom dish form
    sessions/
      data/                 # sessions repository (§4), history queries
      domain/               # uses core/timer_engine
      presentation/         # setup, live status, history screens,
                            # alert-reliability setup screen (§6.4)
    favorites/
      data/
      presentation/
    sharing/
      data/                 # share-link generation, import logic (§8)
      presentation/
  l10n/
    app_en.arb
    app_nl.arb
  main.dart
```

## 3. State Management

Firestore streams (favorites, history, dishes), auth state, and the UI's view of the active session all need to share state without depending on the widget tree.

**Chosen approach: Riverpod, with code generation** (`flutter_riverpod` ^3.x + `riverpod_annotation` + `riverpod_generator`).

- **No `BuildContext` coupling.** Providers behave identically inside or outside the widget tree.
- **Maps cleanly onto Firestore.** A `StreamProvider` wraps a Firestore snapshot listener with almost no glue code — used directly for Favorites, Session History, and Sync (§9).
- **Testable without a UI harness.** A `ProviderContainer` can instantiate and exercise providers in isolation (§12) — important when an AI agent is writing both the implementation and its tests.
- **The dominant modern pattern.** By 2026, the Riverpod code-gen style is the most common idiomatic approach in the Flutter ecosystem, which means an AI coding agent is more likely to produce working, idiomatic code with fewer hallucinated APIs than for a less common pattern.

### Provider layout

| Provider | Type | Purpose |
|---|---|---|
| `authStateProvider` | `StreamProvider` | Wraps `FirebaseAuth.authStateChanges()` |
| `dishRepositoryProvider` | `Provider` | Exposes predefined + custom dish queries |
| `favoritesProvider` | `StreamProvider` | Firestore listener on the user's favorite dishes |
| `sessionHistoryProvider` | `StreamProvider` | Firestore listener on the user's session history (must keep the `where('ownerId','==',uid)` clause — see §10) |
| `activeSessionViewProvider` | `NotifierProvider` | **Read-model** of the in-progress session for the UI — a mirror of the state owned by the service isolate (see below), *not* the engine itself. Seeded on app launch by a read-only load of the persisted state file (§5.5), then updated from service snapshots |
| `sessionCommandsProvider` | `Provider` | Sends user commands ("confirm dish added", "cancel session") by **writing a command file into the inbox** (§5.5) and optionally nudging the service via `sendDataToTask`. "Start session" is the one exception: it starts the service with the initial payload (§6.1) |
| `alertSchedulerProvider` | `Provider` | Main-isolate concerns of the alert layer only: permission status checks for the setup screen (§6.4) and notification-plugin initialization. Per-dish alarm scheduling/cancellation happens **inside the service isolate** at state transitions (§6.1), not through this provider |

**Important isolate boundary.** `flutter_foreground_task` runs its task callback in a **separate Dart isolate**, and Riverpod state is not shared across isolates. Therefore the sequencing engine does **not** live inside a Riverpod provider. Ownership during an active session is:

1. **Service isolate** — runs the timer engine (§5), owns the authoritative session state, persists it to disk on every state transition (§5.5), and pushes state snapshots to the main isolate via `FlutterForegroundTask.sendDataToMain`.
2. **Main isolate (UI)** — `activeSessionViewProvider` holds the latest snapshot received from the service and renders it. Countdowns are rendered locally from the snapshot's timestamps (the snapshot carries targets, not remaining-seconds), so UI smoothness doesn't depend on channel frequency.
3. **All command producers** *(unified in v3)* — the main isolate, notification-action handlers, and fallback-alarm callbacks never mutate engine state directly. Every command is a file in the persisted command inbox (§5.5), which the service isolate drains on its next tick (≤ 1 s). `sendDataToTask` may be sent alongside as a wake nudge to cut that latency, but delivery never depends on it. This gives one code path that is robust from every app state, including a fully dead process (the command waits for recovery).

The engine itself remains pure Dart with no Flutter/Firebase imports; the service isolate is just its host process.

## 4. Data Model (Firestore Schema)

All top-level collections use the Firebase Auth `uid` directly as the ownership key — no separate `users` profile document is created, since the app doesn't need to store anything beyond what Auth already provides (consistent with the PRD's data-minimization requirement).

### `dishes` (top-level collection)

Predefined and custom dishes share one collection so category filtering (US-4) and search (US-5) can operate over both with a single in-memory list.

| Field | Type | Notes |
|---|---|---|
| `name` | string | English name; for custom dishes, whatever the user typed. 1–100 chars (enforced in rules, §10) |
| `nameNl` | string (optional) | Dutch display name. **Predefined dishes only**, populated by the product owner alongside the English data via the Admin SDK. Clients can never write this field — the rules' `hasOnly` field list excludes it (§10). Custom dish names are shown as-is, untranslated (§11) |
| `category` | string | Fixed enum: `vegetables`, `fish`, `meat`, `other`. Stored as the enum key, never as display text — display labels are localized in the app via `gen-l10n` (§11) |
| `steamTimeMinutes` | number | Default steam time; positive integer ≤ 600 (enforced in rules, §10) |
| `temperatureCelsius` | number | Default temperature; > 0 and ≤ 250 (enforced in rules, §10) |
| `source` | string | `"predefined"` \| `"custom"` — **immutable after creation** (§10) |
| `ownerId` | string \| null | `null` for predefined dishes; the creator's `uid` for custom dishes — **immutable after creation** (§10) |

The client runs two listeners — `dishes where source == "predefined"` and `dishes where ownerId == currentUid` — and merges them into one in-memory list in `dishRepositoryProvider`. Predefined dishes are effectively static (populated once by the product owner per the PRD) and read-heavy, so this listener can rely on Firestore's local cache aggressively. Category filtering and search (US-4, US-5) run as in-memory filters over the merged list — at POC-scale dish counts this avoids Firestore's lack of native full-text search without a third-party search service. Search matches against `name` and, when the app locale is Dutch, `nameNl` as well.

Deleting a custom dish may leave a dangling favorite (§4, favorites). The dish-delete flow should also delete the corresponding `favorites/{dishId}` document if present; the favorites list view must additionally tolerate a favorite whose dish no longer resolves (skip it) so a missed cleanup never crashes the UI.

### `sessions` (top-level collection)

Represents a session in the user's **history** (US-17) — either a completed cooking session or an imported shared session. Per §3/§5, the active/in-progress session lives only in local device state and is written here once it finishes. **The document ID for a cooked session is pre-generated client-side at session start** (`firestore.collection('sessions').doc().id`) and carried in the persisted session state, so the completion write is an idempotent `set()` (§5.4).

| Field | Type | Notes |
|---|---|---|
| `ownerId` | string | `uid` of the user whose history this belongs to |
| `createdAt` | timestamp | When this history entry came into existence: session completion time for cooked sessions, import time for imported ones. Written as `FieldValue.serverTimestamp()`; rules enforce `== request.time` (§10). Used for history ordering |
| `origin` | string | `"cooked"` \| `"imported"` — lets the history UI label imported-but-not-yet-cooked entries; a re-run of an imported session writes a new `"cooked"` entry like any other session. Immutable after creation (§10) |
| `dishes` | array of maps | Snapshot of each dish **as configured**: `{ name, nameNl?, steamTimeMinutes, temperatureCelsius, category }`. For cooked sessions, `steamTimeMinutes` is the *actual* time used, including any per-session adjustment (US-6). This is a frozen copy, not a reference, so later edits or deletion of a custom dish never affect history (US-17). Immutable after creation (§10). Rules cannot validate inside array elements (no iteration in Firestore rules) — element-level validity is the writing client's job, and imported arrays are sanitized before writing (§8) |
| `isShareable` | boolean | Must be `false` on create (§10). Set `true` the first time the user taps "Share" (US-20); enables the *get-by-ID* read exception in security rules (§10). This is the **only** field an update may change (§10) |

Using the document's own auto-generated ID as the share-link identifier means "share a session" (US-20) requires no separate sharing table — the link simply encodes this document ID (§8). Firestore auto-IDs are 20 characters of high-entropy alphanumerics, which is what makes the capability-URL model in §10 sound: an ID cannot practically be guessed, shared sessions cannot be *listed* (only fetched by exact ID), and — as of v3 — a shared session's content is immutable, so what the recipient fetches is exactly what the sender shared.

Because `dishes` is a full snapshot, a shared/imported session (US-21) works for recipients even if they don't have the custom dish in their own database — the import copies this document's `dishes` array into a new document owned by the recipient (§8).

### `favorites` (subcollection: `users/{uid}/favorites/{dishId}`)

Purely personal, one entry per favorited dish, so this is scoped under the user rather than a top-level collection with an `ownerId` filter — it keeps the security rule a short "owner only" check (§10) and makes "is this dish favorited" a direct document lookup rather than a query. (No parent `users/{uid}` document is ever created; Firestore subcollections do not require one.)

| Field | Type | Notes |
|---|---|---|
| `dishId` | string | Must equal the document ID (enforced in rules, §10); kept as a field for convenience in list views |
| `addedAt` | timestamp | |

### Indexes required

- `sessions`: composite index on (`ownerId`, `createdAt` descending) — supports the session history list ordered by recency.
- **No index is needed for `dishes`**: both listeners (`source == "predefined"` and `ownerId == uid`) are single-field equality queries covered by Firestore's automatic indexes, and category filtering/search is in-memory.

## 5. Core Timer & Sequencing Engine

This is plain Dart with no Firebase or Flutter dependency, hosted in the foreground-service isolate while a session runs (§3), so it can be unit tested in isolation from any UI or backend (§12). All times inside the engine are **epoch UTC milliseconds** — never local wall-clock strings — so device timezone or DST changes mid-session cannot corrupt countdowns, and persisted state (§5.5) restores unambiguously.

### 5.1 Sequencing algorithm

Given the selected dishes sorted **descending** by steam time (`t_1 ≥ t_2 ≥ ... ≥ t_n`), each dish `i` gets a **planned add-offset**, calculated once, at session start:

```
plannedOffset_i = t_1 - t_i   (minutes, relative to the moment the session starts)
```

Dish 1 (the longest) always has `plannedOffset = 0`, so its "add now" alert fires immediately when the session starts (US-9). Every dish — including dish 1 — goes through the identical confirm-then-countdown flow described below; there's no special-casing of the first dish. This is what makes the "everyone finishes together" behavior fall out naturally: if every dish is confirmed exactly on its planned offset, every dish's countdown ends at `sessionStart + t_1`.

### 5.2 Per-dish state machine

| Status | Meaning | Transition |
|---|---|---|
| `pending` | Planned add-offset hasn't arrived yet | → `readyToAdd` when `plannedOffset_i` elapses |
| `readyToAdd` | "Add dish now" alert has fired (US-11); waiting for user confirmation | → `cooking` when the user confirms (in-app or notification action, US-12) |
| `cooking` | Countdown running from the **actual** confirmation timestamp | → `done` when `confirmedAt + t_i` is reached |
| `done` | "Dish done" alert has fired (US-14) | Terminal |

Each dish's `doneAt` target is always computed from **its own** `confirmedAt`, not from the originally planned offset. This single rule implements late-add handling (US-13): if a dish is confirmed later than planned, only its own `cooking`→`done` window shifts later — the `plannedOffset` values for dishes still in `pending` were computed once upfront and are never recalculated, and any dish already `cooking` runs independently. (Deliberate consequence, per US-13's acceptance criteria: a late-confirmed dish finishes later than the rest rather than dragging the whole meal — "other dishes are unaffected" is the requirement.)

The engine "ticks" once per second, but a tick is nothing more than draining the command inbox and comparing the current epoch time against each dish's stored target timestamps, firing any due transitions. Because state is timestamps rather than decrementing counters, a missed tick (or a full process restart, §5.5) loses nothing — the next comparison catches up instantly.

**Stalls and cancellation.** A dish left unconfirmed in `readyToAdd` simply waits — there is no timeout or auto-confirm; the prompt persists (in-app and in the ongoing notification) until the user confirms or cancels. A `cancelSession` command (available from the live status view) tears everything down: cancel all pending fallback alarms, dismiss notifications, delete the persisted state and command inbox (§5.5), stop the foreground service. **Nothing is written to history** — US-17 logs *completed* sessions only, so a cancelled session leaves no trace.

### 5.3 Live status view (US-10)

Because multiple dishes are typically cooking simultaneously in a real multi-dish session, the status view is a per-dish list rather than a single "current dish" field:
- Every dish in `cooking` shows its own live remaining time.
- The single dish (if any) in `readyToAdd` is highlighted as the "add this now" prompt.
- Dishes still `pending` show their scheduled add time.

For a single-dish session (US-7), this collapses naturally to one entry with no "next" prompt — no separate code path.

### 5.4 Session completion *(revised in v3 — service lifecycle and write idempotency)*

Once every dish reaches `done`, the service isolate:

1. Marks the persisted session state (§5.5) as `completed` and stores the final history payload in it: the `dishes` snapshot array (name, the *actual* steam time used including US-6 adjustments, temperature, category) plus `origin: "cooked"`.
2. Pushes a final `completed` snapshot to the main isolate (if it's alive).
3. Cancels any remaining fallback alarms, and **stops the foreground service immediately.** The service does *not* wait for the Firestore write — with all alerts fired and the state safely on disk, it has no further job, and waiting on a main-isolate write that may only happen on next app launch (user swiped the app away) would leave the service and its persistent notification running indefinitely.

**The Firestore write happens in the main isolate**, never the service isolate — this keeps Firebase entirely out of the service isolate and avoids double-initializing Firebase across isolates. Trigger points, whichever comes first: (a) the main isolate receives the `completed` snapshot while the app is open, or (b) on next app launch, the session store (§5.5) contains a `completed` session with `writtenToHistory == false`.

**Idempotency** *(strengthened in v3)*: the write is a `set()` to the session document ID that was pre-generated at session start (§4) — not an `add()`. A `set()` retried after a crash overwrites the same document with the same content, so even the worst-case crash window (write succeeded, `writtenToHistory` flag not yet persisted) produces no duplicate history entry. After a successful write (or hand-off to Firestore's offline queue, §9) the flag is persisted and the local session state is deleted.

### 5.5 Local persistence, command inbox & crash recovery

The active session's state is persisted on-device for the whole life of the session:

- **What**: one small JSON document — the pre-generated Firestore session ID (§5.4), dish list with per-session adjusted times, `plannedOffset_i`, per-dish status, `confirmedAt`/`doneAt` timestamps (epoch UTC ms), `sessionStartedAt`, resolved locale, `completed`/`writtenToHistory` flags.
- **Where**: a single file in the app's private documents directory, written atomically (write-to-temp + rename). Not `shared_preferences` — a file keeps reads/writes trivially available from any isolate without plugin-cache staleness issues across isolates. **The service isolate is this file's sole *writer*** (with two narrow exceptions owned by the main isolate after the service has stopped: setting `writtenToHistory` and deleting the file, §5.4). Any isolate may *read* it — the main isolate does exactly that on launch to seed `activeSessionViewProvider` before the first service snapshot arrives.
- **Command inbox (separate from the state file)**: every command (§3, point 3; §6.3) is written as its own uniquely-named file (`commands/<epochMs>_<uuid>.json`) in a sibling directory — an atomic create with no shared-file read-modify-write, so any number of isolates can produce commands without a write race. **Each command file carries the `sessionId` it targets** *(added in v3)*: the drain applies commands whose `sessionId` matches the live session and deletes any that don't (e.g. a notification-action tap that raced a cancellation). The service isolate drains the directory on each tick (processing in filename order, deleting each file after applying it); the recovery path below drains it the same way. Any leftover files are swept when a *new* session starts.
- **When (state file)**: on every state transition (session start, alert fired, dish confirmed, dish done, completion) — *not* on every 1-second tick, which is unnecessary because state is timestamps (§5.2).
- **Launch behavior** *(clarified in v3 — three distinct cases)*:
  1. **Service is running** (`FlutterForegroundTask.isRunningService`): *attach*, don't reconstruct — read the state file once for the initial view snapshot, then consume live snapshots from the service. Never start a second engine.
  2. **Service not running, state file holds a non-`completed` session**: the process died mid-cook. Restart the foreground service; it reconstructs the engine from the persisted state, drains the command inbox (a confirm tapped on a post-kill fallback notification is applied here, with its original tap timestamp), and a single tick fast-forwards anything that became due while the process was dead — e.g. a dish whose `doneAt` passed transitions straight to `done` and its (late) notification fires.
  3. **State file holds a `completed` session with `writtenToHistory == false`**: perform the history write (§5.4), then clear the file. No service involved.

This is deliberately minimal scope: one state file plus an inbox directory, written on transitions only. It exists to make the session survive process death, not to be a database.

## 6. Background Alerts & Notifications

This is the PRD's highest-risk item (US-15), so the design uses two mechanisms layered together rather than relying on a single one.

### 6.1 Chosen approach: foreground service (primary) + exact alarms (fallback)

**Primary — Android foreground service.** When the user taps "start session," the main isolate starts the foreground service (`flutter_foreground_task`) with a persistent "Session in progress" notification, passing the configured session (the pre-generated session ID, dish list with per-session adjusted times, resolved locale) as the initial task payload; the timer engine (§5) is constructed inside the task isolate from that payload and immediately persists its initial state (§5.5). Android does not Doze or kill foreground services the way it does background work. The service's task isolate hosts the timer engine (§3, §5): once per second it drains the command inbox, evaluates due transitions, fires "add dish" / "dish done" notifications (via `flutter_local_notifications`), persists any transition (§5.5), and pushes a state snapshot to the main isolate. This works regardless of whether the app UI is open, backgrounded, or the screen is locked. The persistent notification doubles as a lightweight live-status display.

**Fallback — exact alarms, scheduled with a grace offset** *(fixed in v3)*. For each dish's currently-known target time (planned add-time, or done-time once confirmed), the service isolate *also* schedules a one-off exact alarm (`zonedSchedule` with `AndroidScheduleMode.exactAllowWhileIdle`, backed by `AlarmManager.setExactAndAllowWhileIdle`) — **at `target + 45 seconds`, not at `target`**. Rationale: on a healthy device, the service fires the real notification at `target` and cancels the fallback within the grace window; scheduling both for the same instant (as v2 did) guarantees the user gets *two* notifications for every event, because an alarm cannot be cancelled at the exact moment it triggers. If an OEM's battery manager kills the foreground service — the PRD specifically flags Samsung and Xiaomi — the fallback fires up to 45 s late with the app process fully dead, which is an acceptable degradation for a cooking timer, and the persisted state (§5.5) allows full recovery when the user reopens the app. Notification title/body are baked in at schedule time (from the locale-resolved strings, §11), so the alarm needs no app code to render correctly. Each alarm is cancelled and rescheduled as dishes move through their state machine, so there's never more than one pending alarm per not-yet-alerted dish; alarm scheduling is invoked from the service isolate at the same transition points where state is persisted.

**Degraded mode** *(added in v3)*: if `SCHEDULE_EXACT_ALARM` is not granted (the user skipped that step in §6.4), the fallback layer schedules **inexact** alarms (`AndroidScheduleMode.inexactAllowWhileIdle`) instead of scheduling nothing — under Doze these may be minutes late, but a late fallback still beats a silent failure if the OEM also kills the service. The setup screen keeps nudging toward the exact permission.

**Why not WorkManager.** WorkManager (and `workmanager` in Flutter) is designed for *deferrable* background work — the OS is explicitly allowed to batch and delay it by minutes under Doze. That's the wrong tool for user-facing, time-critical alerts. It's a common default reach in Flutter background-task tutorials, but not appropriate here.

### 6.2 Permissions this requires

| Permission | Purpose | Notes |
|---|---|---|
| `POST_NOTIFICATIONS` | Show any notification (Android 13+) | Runtime request, part of the setup screen (§6.4) |
| `SCHEDULE_EXACT_ALARM` | Fallback exact alarms | Denied by default on Android 13+; requires sending the user to the system "Alarms & reminders" settings screen, not an in-app dialog — requested with a clear explanation via the setup screen (§6.4). If never granted, the fallback degrades to inexact alarms (§6.1) |
| Foreground service type declaration | Required for the session-in-progress service | No existing Android FGS type (`location`, `dataSync`, etc.) fits a cooking timer well; use `specialUse` with a manifest-declared justification string |
| `REQUEST_IGNORE_BATTERY_OPTIMIZATIONS` | Ask the user to exempt the app from OEM battery restrictions | Recommended prompt in the setup screen (§6.4), since this is the most common real-world cause of killed timers on Samsung/Xiaomi devices |

(`USE_EXACT_ALARM` is deliberately *not* used: it's auto-granted but restricted by Play policy to apps whose core function is alarms/timers/calendars and is subject to Play Console review. `SCHEDULE_EXACT_ALARM` — user-granted, no review — is the safer choice for Play publication, per the PRD's Play Store milestone.)

### 6.3 Notification action buttons

The "Confirm added" action (US-12) is attached directly to the "add dish" notification via `flutter_local_notifications` action buttons, so it works whether the app is foregrounded, backgrounded, or not running — Android delivers the tap to a background isolate regardless. **The handler does not mutate engine state directly**: it writes a `confirmDish(sessionId, dishId, tappedAt)` command file into the command inbox directory (§5.5). The service isolate drains the inbox on its next tick (≤ 1 s later), performs the `readyToAdd → cooking` transition using the *tap* timestamp (so the countdown isn't skewed by inbox latency), and cancels/reschedules the corresponding fallback alarm. If the tap arrives while the process is dead (post-kill fallback-alarm scenario), the command sits in the inbox and is applied during recovery on next launch (§5.5); if it arrives after the session was cancelled, the `sessionId` mismatch causes it to be discarded (§5.5).

### 6.4 Alert-reliability setup screen

Before the user's **first** session starts (and reachable later from settings), the app shows a one-time setup screen with a live checklist:

1. Notifications permission — granted / grant button (runtime request).
2. "Alarms & reminders" (`SCHEDULE_EXACT_ALARM`) — granted / button deep-linking to the system settings screen, with a one-line plain-language explanation of why ("so alerts still work if your phone puts the app to sleep").
3. Battery-optimization exemption — exempted / prompt button, framed as recommended.

The user can proceed with items unchecked (nothing is hard-blocked except `POST_NOTIFICATIONS`, without which the app is pointless), but the checklist makes the fallback layer's existence a deliberate user choice rather than a silently skipped dialog. State of the checklist is re-evaluated every time a session starts; if a previously granted item was revoked, a compact warning banner appears on the session setup screen.

### 6.5 What the Week 1 spike (§13) needs to validate

This design is based on documented Android behavior, but OEM-specific background-killing is notoriously inconsistent in practice. The spike must confirm, on at least one Samsung and one Xiaomi device: the foreground service survives a multi-dish session with the screen off; **exactly one** notification fires per event on a healthy device (grace-offset cancellation works, §6.1); the fallback alarm actually fires if the service is force-killed; recovery from persisted state (§5.5) reconstructs the session correctly after a process kill; the notification-action → command-inbox → service round trip works from all app states; and the setup screen (§6.4) actually gets testers to grant `SCHEDULE_EXACT_ALARM`.

## 7. Authentication

**Chosen approach: Google Sign-In as the sole method**, via `google_sign_in` + Firebase Auth's Google credential provider — no email/password option for the POC. (Implementation note: use the current `google_sign_in` v7+ API — its initialization/auth flow changed significantly from the v6 examples that dominate older tutorials; don't generate against the legacy API.)

- Every Android device already has a Google account signed in at the OS level, so this is close to a one-tap login — no signup form, no password to create, matching the persona's need for something usable with zero tutorial.
- Google owns all account recovery entirely outside the app. Since there's no password, "custom account recovery flows" isn't a gap to fill later — it's a non-issue by construction.
- No email/password fields means less personal data touches the app at all, fitting the PRD's data-minimization requirement.
- Session handling (token refresh, persistence across app restarts) is handled by Firebase Auth automatically.

Mandatory login (US-2 — no anonymous-first mode) is enforced structurally: the root of the app watches `authStateProvider` (§3); if it emits no user, the router shows only the sign-in screen and nothing else is reachable — including the deep-link import route (§8), which redirects to sign-in first and resumes the import afterward.

Email/password support could be added later (e.g. for testers without a Google account) without restructuring anything — Firebase Auth supports linking multiple providers to one account — but it's left out of the POC to keep the two-week scope tight.

## 8. Session Sharing

**Note on the PRD's tech stack:** it names Firebase Dynamic Links for this feature. That service was fully shut down by Google in August 2025 and cannot be used. The replacement below still uses Firebase (Hosting), just not Dynamic Links.

**Chosen approach: Firebase Hosting + Android App Links**, not a third-party deep-linking service. Dynamic Links' main advantage over OS-native App Links was *deferred* deep linking — routing an uninstalled user through the Play Store and into the right in-app screen after install. SteamTime doesn't need that: sharing is limited to a small group of testers who already have the app installed (per the PRD's Out of Scope section). Android App Links cover everything this feature actually requires, for free, using infrastructure already in the stack.

### Flow

1. **Share (US-20):** tapping "Share" on a session sets `isShareable: true` on its `sessions/{sessionId}` document (§4) if not already set — the only field-level update the rules permit (§10) — then builds `https://steamtime.web.app/s/{sessionId}` and hands it to the OS share sheet (`share_plus`) — WhatsApp or any other app, no special-casing.
2. **Open the link:** a `.well-known/assetlinks.json` hosted on the Firebase Hosting site verifies the domain to Android, so a tap opens SteamTime directly (via `app_links` / `go_router` deep-link routing) to an import screen with the session ID extracted from the path. **Implementation note:** `assetlinks.json` must list the SHA-256 certificate fingerprints of *both* the local debug keystore (for development) and the Play App Signing key (for the published build) — a missing release fingerprint is the classic way App Links silently stop working after Play publication. If verification fails or the app isn't installed, the link falls back to a static Hosting page ("Install SteamTime to open this session") — acceptable for a POC where deferred install-and-open isn't a target scenario.
3. **Import (US-21):** the import screen fetches `sessions/{sessionId}` by direct ID (readable via the `get` rule because `isShareable == true`, §10), **sanitizes** the fetched `dishes` array, and copies it into a new document owned by the recipient, with `origin: "imported"`, `createdAt: serverTimestamp()`, `isShareable: false` (§4). Because that array is a full snapshot, this works even if the sender's custom dish is later edited or deleted, and even though the recipient never had that dish in their own database.

**Import sanitization** *(added in v3)*: the fetched array is another user's data and — because Firestore rules cannot validate inside array elements (§4) — must be treated as untrusted input, not blindly copied under the recipient's `uid`. Before writing the copy, the client: drops any keys other than `{name, nameNl, steamTimeMinutes, temperatureCelsius, category}`; truncates `name`/`nameNl` to 100 chars and rejects empty names; coerces `steamTimeMinutes` to an int clamped to 1–600 and `temperatureCelsius` to 1–250; maps any unknown `category` to `other`; rejects the import entirely if the array is empty or exceeds 20 dishes. (The sender's content was written under the same immutability rules, so in practice this is a cheap defense-in-depth pass, not a UX obstacle.)

No separate "share" data model is needed — the existing `sessions` document *is* the shareable payload, addressed by its own high-entropy document ID, with content immutability (§10) guaranteeing the payload can't be swapped after sharing. The security model for this is the `get`/`list` split plus the update restriction in §10.

### Plan B if timeline pressure hits

If App Links setup (Hosting site, assetlinks, deep-link routing) threatens the two-week POC deadline, the defined fallback is a **manual import code**: "Share" copies the raw session ID to the clipboard, and an "Import a session" screen accepts a pasted ID. Same Firestore documents, same rules, same sanitization, zero web infrastructure — only the delivery mechanism degrades (paste instead of tap). The decision point is end of week 1: if the spike (§13) and core session flow are on track, build App Links; if not, ship plan B and note App Links as post-POC polish. Everything else in this section is unchanged either way.

## 9. Cross-Device Sync

This mostly falls out of decisions already made: `favoritesProvider` and `sessionHistoryProvider` (§3) are Firestore listeners keyed by the logged-in user's `uid`. Logging into a new device re-attaches the same listeners to the same paths, and Firestore delivers the current data automatically — no custom sync/merge logic (US-19).

The §5 design pays off here for offline resilience: the active session's timer state is kept entirely on-device while a session is running, so patchy kitchen Wi-Fi has **zero effect on an in-progress cooking session** — sequencing, countdowns, and alerts all work purely off-device. The only network touchpoint is the final history write at completion (§5.4), and Firestore's built-in offline write queue handles that gracefully: if the device is offline at that moment, the write is queued locally and syncs when connectivity returns. The pre-generated document ID + `set()` write (§5.4) makes retries idempotent across app restarts.

## 10. Security Rules & Privacy

### Firestore security rules

Changes from v2 are marked. The v2 fixes (immutable `ownerId`/`source`; `get`/`list` split) are retained and remain load-bearing.

```
rules_version = '2';
service cloud.firestore {
  match /databases/{database}/documents {

    // Shared field validation for custom dishes (create and update).
    function validDishFields(d) {
      return d.name is string
          && d.name.size() > 0
          && d.name.size() <= 100
          && d.category in ['vegetables', 'fish', 'meat', 'other']
          && d.steamTimeMinutes is int
          && d.steamTimeMinutes > 0
          && d.steamTimeMinutes <= 600
          && d.temperatureCelsius is number
          && d.temperatureCelsius > 0
          && d.temperatureCelsius <= 250;
    }

    match /dishes/{dishId} {
      // Predefined dishes are public read (US-1 doesn't require login to view
      // them), even though the app's own UI never lets an unauthenticated user
      // reach this screen (login is gated at the router, US-2). The rule
      // reflects what the data itself allows, independent of app-level UX.
      // This asymmetry is intentional — see "US-1 vs US-2" note below.
      allow read: if resource.data.source == 'predefined'
                  || (request.auth != null && resource.data.ownerId == request.auth.uid);

      // Clients may only ever create custom dishes owned by themselves, with
      // sane field values and NO undeclared fields (v3: hasOnly). Note that
      // 'nameNl' is deliberately absent from the field list — it is
      // predefined-only (§4) and predefined dishes are seeded via the Admin
      // SDK (which bypasses rules), never written by clients.
      allow create: if request.auth != null
                    && request.resource.data.keys().hasOnly(
                         ['name', 'category', 'steamTimeMinutes',
                          'temperatureCelsius', 'source', 'ownerId'])
                    && request.resource.data.source == 'custom'
                    && request.resource.data.ownerId == request.auth.uid
                    && validDishFields(request.resource.data);

      // ownerId and source are immutable on update (v2 security fix, kept).
      // v3: field list enforced with hasOnly, and ALL mutable fields are
      // re-validated — including temperatureCelsius, which v2's update rule
      // omitted, letting an owner set it to any value or type.
      allow update: if request.auth != null
                    && resource.data.ownerId == request.auth.uid
                    && request.resource.data.keys().hasOnly(
                         ['name', 'category', 'steamTimeMinutes',
                          'temperatureCelsius', 'source', 'ownerId'])
                    && request.resource.data.ownerId == resource.data.ownerId
                    && request.resource.data.source == resource.data.source
                    && validDishFields(request.resource.data);

      allow delete: if request.auth != null
                    && resource.data.ownerId == request.auth.uid;
    }

    match /sessions/{sessionId} {
      // 'read' split into 'get' and 'list' (v2 security fix, kept):
      // a shared session can only be fetched by its exact document ID (the
      // capability the share link carries); listing is owner-only, and the
      // history query MUST include where('ownerId','==',uid) for the list
      // rule to pass — Firestore evaluates list rules against the query's
      // constraints, not per-document. Do not "simplify" that clause away.
      allow get: if request.auth != null
                 && (resource.data.ownerId == request.auth.uid
                     || resource.data.isShareable == true);
      allow list: if request.auth != null
                  && resource.data.ownerId == request.auth.uid;

      // v3: exact field set enforced; createdAt must be the server timestamp
      // (client writes FieldValue.serverTimestamp()); isShareable must start
      // false. Rules cannot iterate the dishes array, so element-level
      // validity is the writing client's responsibility (§4, §8) — rules cap
      // its size and type.
      allow create: if request.auth != null
                    && request.resource.data.keys().hasOnly(
                         ['ownerId', 'createdAt', 'origin', 'dishes', 'isShareable'])
                    && request.resource.data.ownerId == request.auth.uid
                    && request.resource.data.createdAt == request.time
                    && request.resource.data.origin in ['cooked', 'imported']
                    && request.resource.data.isShareable == false
                    && request.resource.data.dishes is list
                    && request.resource.data.dishes.size() > 0
                    && request.resource.data.dishes.size() <= 20;

      // SECURITY FIX (v3): the ONLY permitted update is toggling isShareable.
      // v2's update rule let an owner rewrite dishes/origin/createdAt after
      // creation — so a shared session's content could be swapped after the
      // recipient inspected the link, and "frozen" history snapshots (§4)
      // were in fact mutable. History entries have no legitimate edit flow;
      // the single mutation the product needs (US-20) is this flag.
      allow update: if request.auth != null
                    && resource.data.ownerId == request.auth.uid
                    && request.resource.data.diff(resource.data)
                         .affectedKeys().hasOnly(['isShareable'])
                    && request.resource.data.isShareable is bool;

      allow delete: if request.auth != null
                    && resource.data.ownerId == request.auth.uid;
    }

    match /users/{uid}/favorites/{dishId} {
      allow read, delete: if request.auth != null && request.auth.uid == uid;
      // v3: field validation added; dishId field must match the doc ID.
      allow create, update: if request.auth != null
                    && request.auth.uid == uid
                    && request.resource.data.keys().hasOnly(['dishId', 'addedAt'])
                    && request.resource.data.dishId == dishId
                    && request.resource.data.addedAt is timestamp;
    }
  }
}
```

**US-1 vs. US-2 read-access nuance (decision, closed).** The PRD requires predefined dishes to be viewable without login (US-1) while also requiring login before using *any* feature (US-2). These are reconciled at the UX level — login is gated at the router, so the public-read rule is never exercised by a real user in the POC — and the public-read rule is kept as the honest expression of what the *data* is (a global, non-personal database). This is intentional, not an oversight, and requires no change.

**Implications an implementation agent must respect:**

- Session creation must write `createdAt: FieldValue.serverTimestamp()` — any client-supplied timestamp fails the `== request.time` check.
- The "Share" action must be a targeted update touching only `isShareable`; a full-document `set()` will be rejected by the diff rule.
- The history query must keep its `where('ownerId','==',uid)` clause (see rule comment).

### Privacy

- No separate `users` profile document exists (§4) — Firebase Auth's `uid` is the only identity anchor the app stores, and Google Sign-In (§7) means no email/password fields pass through app-owned storage either.
- User-generated data (custom dishes, favorites, session history) is tied to `uid` because sync and sharing functionally require it — not incidental collection — and is limited to exactly the fields those features need (§4), now also enforced at the rules level via `hasOnly`.
- The active-session file and command inbox (§5.5) live in the app's private storage, contain no personal data beyond dish names/timestamps, and are deleted at session completion/cancellation.
- No analytics or usage tracking is implemented, per the PRD's Out of Scope section.
- Full GDPR compliance work is explicitly out of scope for this POC; the rules above cover data minimization and access control, not a formal legal compliance program.

## 11. Localization

**Chosen approach: Flutter's first-party `gen-l10n` toolchain** (`.arb` files + `flutter_localizations`), not a third-party package like `easy_localization`. It's built into the Flutter SDK, needs no extra dependency, and is the most heavily documented localization pattern in the ecosystem — the same reasoning as the state-management choice in §3 (an AI coding agent is more likely to generate this correctly than a less common alternative).

- All UI chrome strings (buttons, labels, alert/notification text, screen titles) live in `app_en.arb` (default) and `app_nl.arb` (Dutch, per the PRD), with `flutter gen-l10n` generating typed accessors — no hardcoded UI strings anywhere. Notification text fired from the service isolate (§6) uses the same generated strings; the service resolves the locale once at session start (it arrives in the initial payload and is persisted with the session state, so recovery renders in the same language).
- `MaterialApp.supportedLocales` is English + Dutch, OS locale as default, no in-app language switcher for the POC (not called for in the PRD).

**Dish data localization.** `gen-l10n` covers app-bundled strings, not data in Firestore. The resolution:

- **Categories**: stored as fixed enum keys (§4), never as display text. Display labels for the four categories are ordinary `gen-l10n` strings — no schema impact, fully translated.
- **Predefined dish names**: an optional `nameNl` field per dish (§4), populated by the product owner alongside the English data via the Admin SDK (the PRD already assigns dish-database population to the product owner); clients cannot write it (§10). The client displays `nameNl` when the locale is Dutch and it's present, falling back to `name`. Search matches both fields under a Dutch locale. This is the lightest schema change that satisfies "no untranslated user-facing text" for the two-language POC; a `translations` map can replace it if more languages are ever added post-POC.
- **Custom dish names**: user-entered free text, displayed exactly as typed, never translated. Session-history snapshots (§4) carry whatever names were in effect at cook time.

## 12. Testing Strategy

Given a solo developer working with AI coding agents, the goal isn't exhaustive coverage — it's concentrating tests where a bug would be hardest to notice by manually poking at the app, and structuring things so an agent can verify its own work rather than only being checked by eye.

| Layer | What to test | Why |
|---|---|---|
| Sequencing engine (§5) | Pure Dart unit tests: offset calculation, state transitions, late-add handling, fast-forward recovery from persisted state, completion snapshot building | The core logic the app exists to deliver; no UI or Firebase dependency; exactly the kind of isolated logic an AI agent can write correct tests for without a device or emulator. The recovery fast-forward (§5.5) is purely time-math and easy to get subtly wrong — test it with synthetic "process was dead for N minutes" scenarios |
| Session store & command inbox (§5.5) | Unit tests: round-trip serialization, atomic write, inbox drain semantics (apply-once, filename ordering, **sessionId mismatch → discard**), leftover-file sweep at session start | This file is the single source of truth during a session and commands arrive from multiple isolates; corruption, double-applied, or wrongly-applied commands would be very hard to diagnose from manual testing |
| Riverpod providers (§3) | Unit tests using `ProviderContainer` with overridden Firestore/Auth dependencies; include seeding `activeSessionViewProvider` from a state-file read | Verifies the UI-facing state (auth gating, history streams, view-model snapshots) without a real backend or widget tree |
| Firestore security rules (§10) | Rules unit tests via the Firestore emulator (`@firebase/rules-unit-testing`). Must include: (a) owner flipping a custom dish's `source` to `predefined` → denied; (b) authenticated non-owner running `where('isShareable','==',true)` list query → denied; (c) non-owner `get` of a shareable session by ID → allowed; **(d, v3) owner updating a session's `dishes` or `origin` → denied, while an `isShareable`-only update → allowed; (e, v3) create with extra/undeclared fields, client-supplied `createdAt`, or `isShareable: true` → denied; (f, v3) client writing `nameNl` on a custom dish → denied** | Rules are the one layer where a bug is a data leak, not just a broken feature — every security fix in the changelog gets a regression test so it can't be reintroduced |
| Background alerts (§6) | Manual device testing only, not automated | Foreground-service behavior and OEM battery-killing are inherently real-device, real-OS behavior — this is what the Week 1 spike (§13) exists for |
| Widget/UI | Skipped for the POC | Given the two-week timeline and solo-plus-agent setup, UI correctness is verified by using the app during dev and by the friends-and-family testing milestone itself |

## 13. Week 1 Technical Spike Plan

The PRD calls background-alert reliability the highest technical risk and asks for it to be validated before the alert features are built around it. §6 is based on documented Android behavior, not empirical testing — this spike turns it from "should work" into "confirmed to work."

**Scope:** a throwaway test harness, not the real app — just enough to start a fake multi-dish "session" with short (1–3 minute) intervals and observe whether alerts fire as designed. No Firestore, no auth, no real UI — but it **should** include the real service-isolate + persisted-state + command-inbox skeleton from §3/§5.5/§6, because that architecture is exactly what the spike needs to validate alongside raw alert delivery.

**Test matrix — run each scenario on at least a Pixel (control), one Samsung, and one Xiaomi device:**

| Scenario | What's being checked |
|---|---|
| App in foreground | Baseline — should always work, and **exactly one notification per event** (the fallback alarm's grace-offset cancellation, §6.1, is doing its job) |
| App backgrounded (home button) | Foreground service + notification still fire on time; still one notification per event |
| Screen locked | Same, with the screen off |
| Notification action tapped from each of the above states | Command-inbox round trip: tap → inbox → service transition, with the countdown starting from the tap timestamp |
| App task-killed (swiped from recents) | Whether the foreground service survives a user-initiated kill, or only the fallback exact alarm saves it; on reopen, session state is fully reconstructed from the persisted file (§5.5), and a confirm tapped on the fallback notification while dead is applied during recovery |
| Device idle 15+ minutes (Doze) | Confirms Doze doesn't delay the alert |
| Battery optimization *not* exempted | The realistic default state for most users — tests whether the design holds without the extra permission |
| Exact-alarm permission denied | Confirms the foreground service alone is still "good enough," and that the inexact-alarm degraded mode (§6.1) fires eventually if the service is also killed |

**Success criteria:** alerts fire within a few seconds of their target time across all three devices in all scenarios above, with no duplicate notifications, except the intentionally-adversarial task-kill case — there, the fallback alarm firing within its grace window (target + 45 s, §6.1) *and* correct state reconstruction on reopen counts as a pass.

**If it doesn't hold up:** fallback options, in order of preference: (1) make disabling battery optimization a *required* setup step in the §6.4 checklist rather than recommended, (2) accept degraded reliability with a clear in-app warning ("keep SteamTime open for the most reliable alerts") for POC purposes, or (3) write a small native Android (Kotlin) alarm/service component and bridge to it via a platform channel, bypassing the Flutter plugin layer entirely. Whatever is found should update §6 directly with real findings rather than staying as an assumption.

## 14. Risks & Remaining Open Questions

- **Background alert reliability (§6) — the only genuinely open item.** The design uses documented Android behavior plus the recovery layer, but hasn't been validated on real devices; that's exactly what the Week 1 spike (§13) exists to do. Treat §6 as provisional until the spike reports back, and record its findings directly into §6.
- **Sharing plan-B decision point (§8).** Not a risk, but a scheduled decision: end of week 1, choose App Links vs. the manual import code based on remaining runway. Both paths are fully specified above.
- **Watchlist item — Play Store review of `specialUse` foreground service type (§6.2).** The manifest justification string ("in-progress cooking session timer with time-critical user alerts") is expected to pass review, but `specialUse` is by definition subject to human judgment at publication time. If rejected, the mitigation is the native-component fallback from §13 or re-evaluating FGS type choices — flag it, don't pre-build for it.
