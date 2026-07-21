"""
Diagnostics platform (design §9).

Redacts nothing — no personal data exists beyond dish names, which the
user typed themselves.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .engine import session_to_dict

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

    from .data import SteamTimeConfigEntry


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant,  # noqa: ARG001 - required by the diagnostics platform protocol
    entry: SteamTimeConfigEntry,
) -> dict[str, Any]:
    """Return the dish library, live session, and history for this entry."""
    data = entry.runtime_data
    live_session = data.session_manager.state
    return {
        "predefined_dishes": data.dish_library.predefined_dishes,
        "custom_dishes": data.dish_library.custom_dishes,
        "live_session": session_to_dict(live_session) if live_session else None,
        "history": data.history.entries,
    }
