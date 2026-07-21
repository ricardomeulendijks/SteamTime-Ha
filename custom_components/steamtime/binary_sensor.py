"""Binary sensor platform: awaiting confirmation (design §4)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.components.binary_sensor import BinarySensorEntity

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
    """Set up the awaiting-confirmation binary sensor."""
    async_add_entities([SteamTimeAwaitingConfirmationBinarySensor(entry)])


class SteamTimeAwaitingConfirmationBinarySensor(SteamTimeEntity, BinarySensorEntity):
    """`on` when >= 1 dish is `ready_to_add`."""

    _attr_translation_key = "awaiting_confirmation"

    def __init__(self, entry: SteamTimeConfigEntry) -> None:
        """Set up the sensor for this config entry."""
        super().__init__(entry.entry_id, "awaiting_confirmation")
        self._entry = entry

    def _ready_dish_ids(self) -> list[str]:
        state = self._entry.runtime_data.session_manager.state
        if state is None:
            return []
        return [d.id for d in state.dishes if d.status is DishStatus.READY_TO_ADD]

    @property
    def is_on(self) -> bool:
        """True when at least one dish is awaiting confirmation."""
        return len(self._ready_dish_ids()) > 0

    @property
    def extra_state_attributes(self) -> dict[str, list[str]]:
        """The session-scoped ids of dishes awaiting confirmation."""
        return {"dish_ids": self._ready_dish_ids()}
