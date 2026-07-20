"""Config flow for SteamTime."""

from __future__ import annotations

from homeassistant import config_entries

from .const import DOMAIN


class SteamTimeConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Config flow for SteamTime. Single instance, no fields — confirm and create."""

    VERSION = 1

    async def async_step_user(
        self,
        user_input: dict[str, str] | None = None,
    ) -> config_entries.ConfigFlowResult:
        """Handle the single confirm-and-create step."""
        if user_input is not None:
            return self.async_create_entry(title="SteamTime", data={})

        return self.async_show_form(step_id="user")
