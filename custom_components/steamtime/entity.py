"""Shared base entity: the single SteamTime device (design §2, §4)."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity import Entity

from .const import DOMAIN


class SteamTimeEntity(Entity):
    """Base entity tying every platform entity to the one SteamTime device."""

    def __init__(self, entry_id: str) -> None:
        """Set up shared device info, keyed to the (single) config entry."""
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry_id)},
            name="SteamTime",
            entry_type=DeviceEntryType.SERVICE,
        )
