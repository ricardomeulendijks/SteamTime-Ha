# Product Requirements Document: SteamTime

## 1. Overview & Purpose

Steam ovens cook food quickly and healthily, but figuring out steam times and temperatures for different dishes — and timing them so a full meal is ready together — is tedious. Some high-end steam ovens have a built-in "menu" feature for this, but most steam oven owners have to look up steam times manually and guess when to add the next dish so everything finishes at once.

**SteamTime** turns this into a simple guided timer: the user picks the dishes they're cooking, the app auto-sequences them (longest steam time first) and tells them exactly when to add the next dish and when each one is done — making steaming easy as a menu, on any steam oven.

The product will launch as an Android proof-of-concept to validate the idea with a small group of test users, with an iOS release planned once validated.

**Target audience:** Home cooks worldwide who own a steam oven, regardless of whether their oven has a built-in multi-dish menu feature.

## 2. Goals & Success Criteria

**Primary goal:** Validate that SteamTime is genuinely useful for people who cook with a steam oven, with minimal upfront cost or effort.

**Milestones:**
- **Working POC within 2 weeks** — a functional Android app covering the core features (see Section 4), usable end-to-end for a real cooking session.
- **Friends & family testing** — a small group of test users cook with the app and give informal feedback ("this is useful," "I'd use this again," or concrete complaints).
- **Play Store publication** — once testing feedback is positive, publish the app publicly and observe organic traction (downloads, ratings, retention) as an early signal of product-market fit.

**Explicitly not a goal at this stage:**
- Monetization or revenue
- Scaling to large numbers of users
- Measuring specific engagement targets for the sharing feature — it's included as a core feature, but its usage isn't a success metric yet

## 3. User Personas

**Persona: The Everyday Steamer**

| | |
|---|---|
| **Context** | Owns a steam oven without a built-in multi-dish menu feature (or with very limited support for it). Cooks regular meals at home, often combining 2-3 dishes (e.g. potatoes, vegetables, fish). |
| **Tech comfort** | Moderately tech-savvy — comfortable with everyday apps like Facebook and WhatsApp, but not a power user. The app must be simple enough for this level of comfort without any tutorial needed. |
| **Goal** | Get a full meal on the table where every dish finishes steaming at the same time, without having to look up or remember steam times. |
| **Frustration** | Has to look up steam times/temperatures for each dish separately, then manually calculate and track when to add each one to the oven. Easy to lose track of time while doing other kitchen tasks, resulting in overcooked or cold food. |

*Note: for the POC, this persona is deliberately kept broad (not split by cooking skill or lifestyle), since the primary goal is validating the core timing/sequencing concept with a small group of testers.*

## 4. Core Features

### Dish Database & Customization
- **Predefined dish database** — steam times & temperatures for common dishes, brand-agnostic (using manufacturer data and existing steam-cooking guides as sources).
- **Custom dish creation** — users can add their own dish with a name, steam time, and temperature if it's not in the predefined database.
- **Category filtering** — browse dishes by category (e.g. vegetables, fish, meat).
- **Search function** — text search across the full dish database (predefined + custom).
- **Per-dish time adjustment** — users can increase or decrease the steam time for any dish (+/- minutes) before or during setup.

### Session Setup & Sequencing
- **Multi-dish session setup** — users select one or more dishes to cook together in a session.
- **Single-dish sessions** — selecting just one dish works the same way, simply as a single timer with no sequencing needed.
- **Auto-sequencing** — for multi-dish sessions, the app automatically orders dishes longest steam-time first.

### Live Timing & Alerts
- **Live status view** — during an active session, shows the current dish, time remaining, and what's next.
- **"Add dish now" alert** — fires when the next dish should go into the oven, based on the auto-sequenced plan.
- **Confirm-added action** — user confirms a dish has been physically added, via either an in-app button or a notification action button (both supported). This confirmation is what starts that dish's countdown.
- **Late-add handling** — if the user confirms later than planned, that dish's timer starts counting from the actual confirmation time, not the originally planned time. Other dishes already cooking are unaffected and keep their own independent countdowns.
- **"Dish done" alert** — fires when an individual dish's steam time is complete.
- **Reliable background alerts** — all alerts (add-dish, dish-done) fire reliably via notifications and sound, even when the app is backgrounded or the phone is locked.

### Favorites
- **Favorite dishes** — users can mark individual dishes as favorites for quick access. (Combos are not favorited individually — see Session History below.)

### Session History & Sharing
- **Session history** — every cooking session (the set of dishes used together) is automatically logged, no manual saving required.
- **Restart a past session** — one-tap re-run of any session from history.
- **Share a session** — generate a shareable link for a past session, letting another user import that exact dish combination.
- **Import a shared session** — opening a shared link saves that session into the recipient's own history.

### Accounts & Sync
- **User account (Firebase Auth)** — login required so a user's data can be restored on a new device.
- **Cross-device sync** — favorites and session history sync via the user's account.

## 5. User Stories & Acceptance Criteria

Stories are ordered by build priority: earlier stories are dependencies for later ones. **P0** stories form the minimum viable POC (core dish data + full timer flow); **P1** stories add personalization, history, and sharing on top.

### P0 — Foundation

**US-1: Browse the predefined dish database**
As a user, I want to browse a predefined list of dishes with their steam times and temperatures, so that I don't have to look up cooking information myself.
- Given the app has a predefined dish database, when the user opens the dish list, then they see each dish's name, steam time, and temperature.
- Given the dish list is open, when no filter or search is applied, then all predefined dishes are shown.
- Given the predefined database is global, shared data, when a user browses it, then no login is required to view it.

**US-2: Create an account / log in**
As a user, I want to log in with an account, so that my data can be restored if I switch phones.
- Given a new user opens the app for the first time, when they reach the point of using any feature, then they must create an account or log in via Firebase Auth first — login is mandatory, not optional or deferred.
- Given a user is logged in, when they reinstall the app or use a new device, then logging in with the same account restores their data.
- Given all user-specific features (custom dishes, favorites, session history) require a user identity, when this story is implemented, then it is built before any of those features so their data model can be tied to a user account from the start.

### P0 — Dish Data Customization

**US-3: Add a custom dish**
As a user, I want to add my own dish with a name, steam time, and temperature, so that I can use dishes that aren't in the predefined database.
- Given a logged-in user is adding a custom dish, when they enter a name, steam time, and temperature and save, then the dish appears in their dish list alongside predefined dishes, tied to their account.
- Given required fields (name, steam time, temperature) are missing, when the user tries to save, then the app prevents saving and indicates what's missing.

**US-4: Filter dishes by category**
As a user, I want to filter the dish list by category, so that I can find dishes faster.
- Given the dish list contains dishes with categories (e.g. vegetables, fish, meat), when the user selects a category filter, then only dishes in that category are shown.
- Given a category filter is active, when the user clears it, then the full dish list is shown again.

**US-5: Search dishes**
As a user, I want to search for a dish by name, so that I can quickly find a specific dish without scrolling.
- Given the dish list (predefined + custom) is loaded, when the user types a search term, then matching dishes are shown in real time.
- Given a search term matches no dishes, when the user views the results, then the app shows a clear "no results" state.

**US-6: Adjust a dish's steam time**
As a user, I want to increase or decrease a dish's steam time, so that I can tune it to my own taste or oven.
- Given a dish is selected for a session, when the user adjusts its steam time up or down, then the new time is used for that session's sequencing and alerts.
- Given a time adjustment is made, when the session starts, then the adjusted time (not the default) is used for that dish going forward.

### P0 — Core Session Flow

**US-7: Start a single-dish session**
As a user, I want to start a cooking session with just one dish, so that I get a simple timer even when I'm not combining dishes.
- Given the user selects exactly one dish, when they start the session, then a single countdown timer begins for that dish with no sequencing logic involved.
- Given a single-dish session is running, when the steam time elapses, then the user gets a "dish done" alert (see US-14).

**US-8: Start a multi-dish session**
As a user, I want to select multiple dishes for one cooking session, so that I can coordinate a full meal.
- Given the user selects two or more dishes, when they start the session, then all selected dishes are included in one coordinated session.
- Given a multi-dish session is started, when setup completes, then the session moves to auto-sequencing (US-9) before any timer starts.

**US-9: Auto-sequence a multi-dish session**
As a user, I want the app to automatically order my dishes by steam time, so that I don't have to figure out the sequence myself.
- Given a multi-dish session with dishes of different steam times, when the session is sequenced, then dishes are ordered longest steam time first.
- Given the sequence is determined, when the session starts, then the first alert relates to the first (longest) dish going into the oven.

**US-10: View live session status**
As a user, I want to see the current status of my session while cooking, so that I know what's happening without guessing.
- Given a session is active, when the user opens the app, then they see the current dish, time remaining, and which dish is next.
- Given a session has only one dish, when the user views status, then it shows just that dish's remaining time with no "next dish" info.

**US-11: Receive an "add next dish" alert**
As a user, I want to be alerted when it's time to add the next dish, so that I don't have to watch the clock myself.
- Given a multi-dish session is running, when the calculated time arrives for the next dish to be added, then the app fires an alert telling the user which dish to add.
- Given the current dish's alert has already fired, when no next dish remains, then no further "add dish" alerts fire for that session.

**US-12: Confirm a dish has been added**
As a user, I want to confirm when I've physically added a dish to the oven, so that its timer starts at the right moment.
- Given an "add next dish" alert has fired, when the user taps "confirm" in the app, then that dish's countdown starts immediately.
- Given an "add next dish" alert has fired, when the user taps the confirm action directly from the notification (without opening the app), then that dish's countdown starts immediately, same as an in-app confirmation.

**US-13: Handle a late dish confirmation**
As a user, I want the app to handle it gracefully if I add a dish later than planned, so that my other dishes aren't affected by my delay.
- Given the user confirms a dish later than the originally planned add-time, when the confirmation happens, then that dish's countdown starts from the actual confirmation time, not the original planned time.
- Given one dish is added late, when other dishes are already cooking, then their countdowns and alerts are unaffected by the delay.

**US-14: Receive a "dish done" alert**
As a user, I want to be alerted when a dish is finished steaming, so that I know when to take it out.
- Given a dish's countdown reaches zero, when this happens, then the app fires a "dish done" alert specific to that dish.
- Given multiple dishes finish at different times, when each one completes, then each gets its own separate "dish done" alert.

**US-15: Reliable alerts in the background or on a locked screen**
As a user, I want alerts to fire even if my phone is locked or the app isn't open, so that I don't miss a step while doing other things in the kitchen.
- Given a session is active and the app is backgrounded or the phone is locked, when an "add dish" or "dish done" alert is due, then the notification and sound fire the same as if the app were in the foreground.
- Given the device is in a low-power or restricted background mode, when an alert is due, then the app still delivers the notification (subject to platform limitations, to be validated during POC testing).

### P1 — Personalization & History

**US-16: Mark a dish as favorite**
As a user, I want to mark individual dishes as favorites, so that I can find the ones I use most quickly.
- Given a logged-in user views a dish in the database, when they mark it as a favorite, then it appears in a "favorites" view tied to their account.
- Given a dish is already a favorite, when the user unmarks it, then it's removed from the favorites view.

**US-17: Automatic session history logging**
As a user, I want my past cooking sessions saved automatically, so that I don't have to remember to save them myself.
- Given a session (single or multi-dish) completes, when it finishes, then it's automatically added to the logged-in user's session history with its dish combination.
- Given the user opens session history, when they view it, then past sessions are listed with the dishes used and roughly when they were cooked.
- Given a custom dish used in a past session is later edited or deleted, when the user views that session in history, then it still shows a snapshot of the dish's values as they were at the time of cooking, unaffected by the later edit or deletion.

**US-18: Restart a past session**
As a user, I want to re-run a session from my history with one tap, so that I can repeat a meal without re-selecting every dish.
- Given a past session in history, when the user selects "restart," then a new session is created with the same dishes and settings as before.
- Given a restarted session, when it begins, then it goes through the normal sequencing and alert flow like any new session.

### P1 — Sync & Sharing

**US-19: Cross-device sync**
As a user, I want my favorites and session history to sync across devices, so that my data isn't stuck on one phone.
- Given a logged-in user makes a change (favorite a dish, complete a session), when the change happens, then it syncs to their account.
- Given the same account is used on a new device, when the user logs in, then their favorites and session history appear as they were on the previous device.

**US-20: Share a session via link**
As a user, I want to share a past session with someone else, so they can cook the same combination of dishes.
- Given a session in the user's history, when they select "share," then the app generates a shareable link representing that session's dish combination.
- Given a share link is generated, when the user sends it to someone (e.g. via WhatsApp), then the link, when opened, is valid and points to that specific session.
- Given a shared session includes a custom dish, when the link is generated, then it carries the full dish data (name, steam time, temperature), not just a reference — so it works for recipients who don't have that dish in their own database.

**US-21: Import a shared session**
As a user, I want to open a session link someone shared with me, so that I can cook the same combination without setting it up myself.
- Given a logged-in user receives a shared session link, when they open it in the app, then the session's dish combination is saved into their own session history.
- Given the session is imported, when the user starts it, then it behaves like any other session (auto-sequencing, alerts, etc.).

## 6. Non-Functional Requirements

**Reliability — background alerts (highest technical risk)**
- Alerts ("add next dish," "dish done") must fire directly, at the calculated time, regardless of whether the app is in the foreground, backgrounded, or the phone is locked.
- Android's battery optimization and OEM-specific background restrictions (e.g. Doze mode, manufacturer-specific process killing on Samsung, Xiaomi, etc.) are a known risk to this requirement. **This should be treated as a technical spike early in development** — prototype and validate reliable background alert delivery in week 1, rather than leaving it until the alert features are built, so any fundamental limitations are discovered while there's still time to address them.

**Platform & compatibility**
- Target Android versions released within roughly the last year (as of mid-2026, this means Android 16 and the newly released Android 17). Exact minimum SDK/API level to be confirmed at implementation time, since Android's release cadence may shift this window.
- iOS is out of scope for the POC (see Section 7) but the tech stack choice below is made with an eventual iOS release in mind.

**Privacy & data handling**
- Full GDPR compliance work is out of scope for this friends-and-family POC stage.
- The app should minimize stored personal data: use an external authentication provider (Firebase Auth) rather than building custom auth, and avoid collecting or storing personal information (name, email, etc.) beyond what the auth provider requires.
- User-generated data (custom dishes, favorites, session history) is necessarily stored and tied to the user's account ID to support sync and sharing — this is a functional requirement, not incidental data collection, and should be limited strictly to what those features need.

**Localization**
- All user-facing text must be implemented as translatable strings — no hardcoded text in the UI.
- English is the primary language at launch, with Dutch as the first additional language to be added.

**Technology stack**
- **Flutter** for the app itself (single codebase, supports the planned Android-first/iOS-later rollout with minimal additional cost).
- **Firebase** as the backend (Authentication for login, Firestore or Realtime Database for custom dishes/favorites/session history, hosting/dynamic links for session sharing).
- This stack is chosen for low/no startup cost and fast POC development; it can be revisited if specific features (e.g. background reliability) turn out to need a different approach.

**Performance**
- No specific performance targets are defined for the POC; general responsiveness is expected but not a formal requirement at this stage.

## 7. Out of Scope

The following are explicitly **not** part of this POC, based on decisions made throughout this PRD:

- **iOS app** — deferred until the Android POC has been validated with test users; not part of this build, though Flutter + Firebase were chosen with iOS in mind for later.
- **Direct oven connectivity** — no Bluetooth/WiFi/IoT integration with the steam oven itself; the app is a manual companion only (user physically adds/removes dishes and confirms in-app).
- **Portion/quantity-based time scaling** — steam times are fixed regardless of how much of a dish is being cooked (e.g. 2 potatoes vs. 6).
- **Brand-specific dish data** — the dish database is generic and brand-agnostic; sorting or filtering by oven brand/manufacturer is not included.
- **Favoriting combinations of dishes** — only individual dishes can be favorited; combinations are handled via automatic session history instead.
- **Monetization** — no payments, subscriptions, or ads.
- **Full GDPR compliance program** — beyond using an external auth provider and minimizing stored personal data, formal privacy/legal compliance work is not part of this POC.
- **Performance optimization** — no specific performance targets are being engineered for at this stage.
- **Analytics/usage tracking** — no dedicated analytics implementation for this POC.
- **Content moderation for shared sessions** — since sharing is limited to a small, trusted group of test users, no moderation tooling is included.
- **Additional languages beyond English and Dutch**.
- **Onboarding tutorials or guided walkthroughs** — the app is expected to be simple enough to use without one; if testing reveals otherwise, this may be reconsidered post-POC.
- **Custom account recovery flows** — password reset, account deletion, etc. beyond what Firebase Auth provides out of the box.

## 8. Open Questions / Assumptions

### Assumptions (decided during this PRD)

- **Oven preheat time is not tracked by the app.** The user is expected to preheat their oven and start the SteamTime session once it's actually ready, the same way they would with a built-in multi-dish menu feature. Preheat times vary by brand and aren't accounted for in the timer logic. This may be revisited post-POC if testers find it confusing (e.g. a user-configurable preheat buffer, or a manual "oven ready" confirmation).
- **Shared/imported sessions carry full dish data**, not just a reference — see US-20/US-21.
- **Session history snapshots custom dish data** at the time of cooking, unaffected by later edits or deletion of that dish — see US-17.
- **Login is mandatory on first launch** — no anonymous-first mode. Chosen over a "try before you log in" flow for POC simplicity — see US-2.
- **The initial dish database** (steam times/temperatures compiled from manufacturer data and existing steam-cooking guides) will be populated directly by the product owner, not by the development agent.
- **Detailed technical design is intentionally out of scope for this PRD.** Data models, Firestore structure, API contracts, and similar implementation details will be worked out in a separate technical design session using this PRD as input.

### Still open

- None outstanding at the time of writing. New questions that surface during technical design or development should be added here.
