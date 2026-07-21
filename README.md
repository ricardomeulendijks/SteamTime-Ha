# SteamTime

A Home Assistant custom integration (domain: `steamtime`) — a cooking companion for
steam-oven users. Pick the dishes you're cooking, and SteamTime auto-sequences them
(longest steam time first), tells you exactly when to add each one, and starts each
dish's own countdown only once you confirm it's actually in the oven. Late additions
never disturb dishes already cooking.

See [`docs/design.md`](docs/design.md) for the technical design and
[`docs/prd-scope-map.md`](docs/prd-scope-map.md) for what carried over from the
original product spec.

## Install

### HACS (recommended)

1. HACS → the three-dot menu (top right) → **Custom repositories**.
2. Add this repository's URL, category **Integration**.
3. Search for **SteamTime** in HACS and install it.
4. Restart Home Assistant.
5. **Settings → Devices & Services → Add Integration → SteamTime.** No configuration
   fields — just confirm.

### Manual

Copy `custom_components/steamtime` into your Home Assistant `custom_components/`
directory, restart, then add the integration as above.

## Entities

One device, **SteamTime**, holding:

| Entity | What it shows |
|---|---|
| `sensor.steamtime_session` | `idle` / `running`, plus a `dishes` attribute listing every dish's id, name, status, and timestamps — enough for a dashboard to render the full live status |
| `sensor.steamtime_next_add` | When the next dish should go in (a past timestamp if one's ready right now) |
| `sensor.steamtime_next_done` | When the next cooking dish finishes |
| `binary_sensor.steamtime_awaiting_confirmation` | On while >= 1 dish is waiting to be confirmed added |
| `button.steamtime_confirm` | Confirms the oldest waiting dish — a convenience; `steamtime.confirm_dish` is the precise path |
| `button.steamtime_cancel` | Cancels the session. **Disabled by default** — it's destructive; enable it deliberately and consider adding a dashboard confirmation |

## Services

| Service | Purpose |
|---|---|
| `steamtime.start_session` | Start a session: a list of dishes, each either `{dish_id, minutes?}` (from your library, with an optional one-off time override) or `{name, minutes, temperature?}` (inline, one-off) |
| `steamtime.confirm_dish` | Confirm a dish (by its session-scoped id, e.g. `d2`) was physically added |
| `steamtime.cancel_session` | Cancel the running session |
| `steamtime.add_dish` / `update_dish` / `remove_dish` | Manage your custom dish library. Predefined dishes can't be edited or removed |
| `steamtime.get_dishes` | Merged predefined + custom library, for scripts and dashboards |
| `steamtime.get_history` | Completed-session history, newest first |
| `steamtime.restart_session` | Start a new session from a past history entry's frozen snapshot |

## Notifications

The integration itself only fires events — delivery is a separate automation
**blueprint**:

1. **Settings → Automations & Scenes → Blueprints → Import Blueprint**, and paste the
   URL to
   [`blueprints/automation/steamtime/steamtime_notify.yaml`](blueprints/automation/steamtime/steamtime_notify.yaml)
   in this repo.
2. Create a new automation from the imported blueprint, pick your phone's notify
   target(s), and save.

That's it — "add this dish" alerts arrive with a **Confirm added** action button you
can tap from the lock screen, done-alerts follow, and a cancelled session clears any
notifications still waiting on a reply.

## Example dashboard card

A minimal Markdown card rendering live status from `sensor.steamtime_session`:

```yaml
type: markdown
content: >-
  {% set s = states.sensor.steamtime_session %}
  {% if s.state == 'running' %}
  **Session running**

  {% for dish in s.attributes.dishes %}
  - {{ dish.name }} — {{ dish.status }}
  {% endfor %}
  {% else %}
  No session running.
  {% endif %}
```

Pair it with `sensor.steamtime_next_add` / `sensor.steamtime_next_done` (both
`device_class: timestamp`) in a standard entities or tile card for live countdowns —
no template needed, dashboards render countdowns from a timestamp natively.

## Development

This template ships with configuration for **two** dependency update tools. Pick
**one** and remove or disable the other:

- **Renovate** (`.github/renovate.json`) is enabled by default.
- **Dependabot** (`.github/_dependabot.yml`) is included but disabled — the `_`
  prefix means GitHub ignores it. To use Dependabot instead, rename the file
  back to `.github/dependabot.yml` and delete `.github/renovate.json`.

Run `scripts/develop` to start a local Home Assistant instance with this
integration loaded (config in `config/configuration.yaml`). Run `scripts/lint`
before committing.

### Running quality gates on Windows

`homeassistant` (and therefore `pytest-homeassistant-custom-component`)
doesn't import on native Windows — it pulls in the Unix-only `fcntl` module.
If you're developing on Windows, run `scripts/test-docker` from a WSL2 Ubuntu
shell (`wsl` from PowerShell) with Docker Engine installed there; it runs
ruff, mypy, and the full pytest suite inside a Linux container. See the
script's header comment for why it syncs to a native WSL copy first instead
of bind-mounting the Windows path directly.
