"""Config flow for SteamTime."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import CONF_CRITICAL_ADD_ALERTS, CONF_NOTIFY_TARGETS, DOMAIN

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

# Generic notify.* services that never represent a real device/target.
_GENERIC_NOTIFY_SERVICES = frozenset(
    {"send_message", "notify", "persistent_notification"}
)


def _notify_options_schema(
    hass: HomeAssistant, current: dict[str, Any] | None = None
) -> vol.Schema:
    """
    Build the notify-target(s) + critical-alerts schema.

    Options are real registered `notify.*` services, not entities: actionable
    notification fields (tag, actions, push, priority, ttl, channel) can only
    be sent via a target's actual service, never via the generic
    `notify.send_message` action against a `notify.*` entity — that action's
    schema is `{message, title}` only, for any notify entity (design §7).
    """
    current = current or {}
    service_names = sorted(
        name
        for name in hass.services.async_services_for_domain("notify")
        if name not in _GENERIC_NOTIFY_SERVICES
    )
    return vol.Schema(
        {
            vol.Optional(
                CONF_NOTIFY_TARGETS,
                default=current.get(CONF_NOTIFY_TARGETS, []),
            ): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=[f"notify.{name}" for name in service_names],
                    multiple=True,
                    mode=selector.SelectSelectorMode.DROPDOWN,
                )
            ),
            vol.Optional(
                CONF_CRITICAL_ADD_ALERTS,
                default=current.get(CONF_CRITICAL_ADD_ALERTS, False),
            ): selector.BooleanSelector(),
        }
    )


class SteamTimeConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Config flow for SteamTime. Single instance; confirm, then notify prefs."""

    VERSION = 1

    async def async_step_user(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> config_entries.ConfigFlowResult:
        """Handle the single confirm-and-continue step."""
        if user_input is not None:
            return await self.async_step_notify()

        return self.async_show_form(step_id="user")

    async def async_step_notify(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> config_entries.ConfigFlowResult:
        """
        Collect notify target(s) and the critical-alerts preference.

        Leaving notify targets empty is valid: the integration then sends no
        notifications itself, and the blueprint remains fully usable either
        way (design §7).
        """
        if user_input is not None:
            return self.async_create_entry(
                title="SteamTime", data={}, options=user_input
            )

        return self.async_show_form(
            step_id="notify", data_schema=_notify_options_schema(self.hass)
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        _config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        """Get the options flow for reconfiguring notify preferences."""
        return SteamTimeOptionsFlow()


class SteamTimeOptionsFlow(config_entries.OptionsFlow):
    """Reconfigure notify target(s) and critical-alerts after setup."""

    async def async_step_init(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> config_entries.ConfigFlowResult:
        """Handle the single reconfiguration step."""
        if user_input is not None:
            return self.async_create_entry(data=user_input)

        return self.async_show_form(
            step_id="init",
            data_schema=_notify_options_schema(
                self.hass, dict(self.config_entry.options)
            ),
        )
