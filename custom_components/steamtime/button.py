"""Button platform: confirm and cancel (design §4)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.components.button import ButtonEntity

from .const import DOMAIN, LOGGER, SERVICE_CANCEL_SESSION, SERVICE_CONFIRM_DISH
from .engine import DishStatus
from .entity import SteamTimeEntity

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

    from .data import SteamTimeConfigEntry


async def async_setup_entry(
    _hass: HomeAssistant,
    entry: SteamTimeConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the confirm and cancel buttons."""
    async_add_entities([SteamTimeConfirmButton(entry), SteamTimeCancelButton(entry)])


class SteamTimeConfirmButton(SteamTimeEntity, ButtonEntity):
    """Confirms the oldest `ready_to_add` dish. The precise path is the service."""

    _attr_translation_key = "confirm"

    def __init__(self, entry: SteamTimeConfigEntry) -> None:
        """Set up the button for this config entry."""
        super().__init__(entry.entry_id, "confirm")
        self._entry = entry

    async def async_press(self) -> None:
        """Confirm the oldest ready-to-add dish, via the confirm_dish service."""
        state = self._entry.runtime_data.session_manager.state
        ready = (
            [d for d in state.dishes if d.status is DishStatus.READY_TO_ADD]
            if state
            else []
        )
        if not ready:
            LOGGER.warning("steamtime.confirm button: no dish is awaiting confirmation")
            return

        oldest = min(ready, key=lambda dish: dish.planned_add_at)
        await self.hass.services.async_call(
            DOMAIN, SERVICE_CONFIRM_DISH, {"dish_id": oldest.id}, blocking=True
        )


class SteamTimeCancelButton(SteamTimeEntity, ButtonEntity):
    """Cancels the running session. Disabled by default — destructive."""

    _attr_translation_key = "cancel"
    _attr_entity_registry_enabled_default = False

    def __init__(self, entry: SteamTimeConfigEntry) -> None:
        """Set up the button for this config entry."""
        super().__init__(entry.entry_id, "cancel")
        self._entry = entry

    async def async_press(self) -> None:
        """Cancel the running session, via the cancel_session service."""
        if self._entry.runtime_data.session_manager.state is None:
            LOGGER.warning("steamtime.cancel button: no session is running")
            return

        await self.hass.services.async_call(
            DOMAIN, SERVICE_CANCEL_SESSION, {}, blocking=True
        )
