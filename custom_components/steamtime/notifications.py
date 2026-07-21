"""
Built-in notification delivery (design §7).

Optional: only active when the config entry's options specify at least one
notify target. Listens to the same public bus events (§6) the shipped
blueprint consumes — this is just another consumer of that public API, not
a replacement for it. The blueprint remains available for anyone who wants
different delivery behavior; both can run at the same time with no
conflict, since confirming an already-cooking dish is an idempotent no-op.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .const import (
    CONF_CRITICAL_ADD_ALERTS,
    CONF_NOTIFY_TARGETS,
    DOMAIN,
    EVENT_ADD_DISH,
    EVENT_DISH_DONE,
    EVENT_SESSION_CANCELLED,
    EVENT_SESSION_COMPLETED,
    LOGGER,
    SERVICE_CONFIRM_DISH,
)

if TYPE_CHECKING:
    from homeassistant.core import CALLBACK_TYPE, Event, HomeAssistant

    from .data import SteamTimeConfigEntry

_MOBILE_APP_ACTION_EVENT = "mobile_app_notification_action"
_CONFIRM_ACTION_PREFIX = "steamtime_confirm_"


class NotificationDispatcher:
    """Sends built-in notifications to the notify target(s) in entry.options."""

    def __init__(self, hass: HomeAssistant, entry: SteamTimeConfigEntry) -> None:
        """Set up the dispatcher. Call `async_setup` before use."""
        self.hass = hass
        self._entry = entry
        self._unsubs: list[CALLBACK_TYPE] = []

    def async_setup(self) -> None:
        """Start listening, if any notify target is configured."""
        if not self._targets():
            return

        listen = self.hass.bus.async_listen
        self._unsubs = [
            listen(EVENT_ADD_DISH, self._handle_add_dish),
            listen(EVENT_DISH_DONE, self._handle_dish_done),
            listen(EVENT_SESSION_COMPLETED, self._handle_session_completed),
            listen(EVENT_SESSION_CANCELLED, self._handle_session_cancelled),
            listen(_MOBILE_APP_ACTION_EVENT, self._handle_confirm_action),
        ]

    def async_unload(self) -> None:
        """Stop listening."""
        for unsub in self._unsubs:
            unsub()
        self._unsubs.clear()

    def _targets(self) -> list[str]:
        return list(self._entry.options.get(CONF_NOTIFY_TARGETS, []))

    def _critical(self) -> bool:
        return bool(self._entry.options.get(CONF_CRITICAL_ADD_ALERTS, False))

    async def _send(self, target: str, payload: dict[str, Any]) -> None:
        domain, _, service = target.partition(".")
        try:
            await self.hass.services.async_call(domain, service, payload)
        except Exception:  # noqa: BLE001 - one bad target must not break the rest
            LOGGER.warning("Could not send notification via %s", target, exc_info=True)

    async def _send_to_all(self, payload: dict[str, Any]) -> None:
        for target in self._targets():
            await self._send(target, payload)

    async def _handle_add_dish(self, event: Event) -> None:
        dish_id = event.data["dish_id"]
        critical = self._critical()
        message = (
            f"Add {event.data['dish_name']} to the oven — "
            f"{event.data['temperature']} °C"
        )
        await self._send_to_all(
            {
                "title": "Add to the oven",
                "message": message,
                "data": {
                    "tag": f"steamtime_{dish_id}",
                    "actions": [
                        {
                            "action": f"{_CONFIRM_ACTION_PREFIX}{dish_id}",
                            "title": "Confirm added",
                        }
                    ],
                    "push": {
                        "interruption-level": "critical" if critical else "active",
                        "sound": {
                            "name": "default",
                            "critical": 1 if critical else 0,
                            "volume": 1.0 if critical else 0.5,
                        },
                    },
                    "priority": "high" if critical else "normal",
                    "ttl": 0 if critical else 2419200,
                    "channel": "alarm_stream" if critical else "default",
                },
            }
        )

    async def _handle_dish_done(self, event: Event) -> None:
        dish_id = event.data["dish_id"]
        await self._send_to_all(
            {
                "title": "Done",
                "message": f"{event.data['dish_name']} is done",
                "data": {"tag": f"steamtime_{dish_id}"},
            }
        )

    async def _handle_session_completed(self, _event: Event) -> None:
        await self._send_to_all(
            {"title": "SteamTime", "message": "Session complete — everything's ready!"}
        )

    async def _handle_session_cancelled(self, event: Event) -> None:
        for dish_id in event.data.get("dish_ids", []):
            await self._send_to_all(
                {
                    "message": "clear_notification",
                    "data": {"tag": f"steamtime_{dish_id}"},
                }
            )
        await self._send_to_all({"title": "SteamTime", "message": "Session cancelled"})

    async def _handle_confirm_action(self, event: Event) -> None:
        action = event.data.get("action", "")
        if not action.startswith(_CONFIRM_ACTION_PREFIX):
            return

        dish_id = action[len(_CONFIRM_ACTION_PREFIX) :]
        await self.hass.services.async_call(
            DOMAIN, SERVICE_CONFIRM_DISH, {"dish_id": dish_id}
        )
