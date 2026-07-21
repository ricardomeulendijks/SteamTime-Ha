"""Runtime data bundled on the config entry (design §2)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from homeassistant.config_entries import ConfigEntry

if TYPE_CHECKING:
    from .notifications import NotificationDispatcher
    from .session_manager import SessionManager
    from .storage import DishLibraryStore, HistoryStore


@dataclass
class SteamTimeData:
    """Everything `async_setup_entry` builds, handed to platforms/services."""

    dish_library: DishLibraryStore
    history: HistoryStore
    session_manager: SessionManager
    notification_dispatcher: NotificationDispatcher


type SteamTimeConfigEntry = ConfigEntry[SteamTimeData]
