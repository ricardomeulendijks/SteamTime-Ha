"""
Custom integration to integrate SteamTime with Home Assistant.

For more details about this integration, please refer to
https://github.com/ricardomeulendijks/SteamTime-Ha
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.const import Platform

from .data import SteamTimeData
from .services import async_setup_services, async_unload_services
from .session_manager import SessionManager
from .storage import DishLibraryStore, HistoryStore, SessionStore

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

    from .data import SteamTimeConfigEntry

PLATFORMS: list[Platform] = [
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
]


async def async_setup_entry(hass: HomeAssistant, entry: SteamTimeConfigEntry) -> bool:
    """Set up this integration using UI."""
    dish_library = DishLibraryStore(hass)
    history = HistoryStore(hass)
    await dish_library.async_load()
    await history.async_load()

    session_manager = SessionManager(hass, SessionStore(hass), history)
    await session_manager.async_setup()

    entry.runtime_data = SteamTimeData(
        dish_library=dish_library,
        history=history,
        session_manager=session_manager,
    )

    await async_setup_services(hass, entry)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: SteamTimeConfigEntry) -> bool:
    """Handle removal of an entry."""
    async_unload_services(hass)
    await entry.runtime_data.session_manager.async_unload()
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
