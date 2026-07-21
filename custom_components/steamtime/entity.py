"""Shared base entity: the single SteamTime device (design §2, §4)."""

from __future__ import annotations

from homeassistant.core import callback
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import Entity

from .const import DOMAIN, SIGNAL_SESSION_UPDATED


class SteamTimeEntity(Entity):
    """
    Base entity tying every platform entity to the one SteamTime device.

    Push-updated only (never polled): subscribes to `SIGNAL_SESSION_UPDATED`
    and re-renders from `SessionManager.state` whenever the runtime fires it.
    """

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, entry_id: str, unique_id_suffix: str) -> None:
        """Set up shared device info and this entity's unique id."""
        self._attr_unique_id = f"{entry_id}_{unique_id_suffix}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry_id)},
            name="SteamTime",
            entry_type=DeviceEntryType.SERVICE,
        )

    async def async_added_to_hass(self) -> None:
        """Subscribe to session updates once added to hass."""
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass, SIGNAL_SESSION_UPDATED, self._handle_session_updated
            )
        )

    @callback
    def _handle_session_updated(self) -> None:
        """Re-render from the current SessionManager state."""
        self.async_write_ha_state()
