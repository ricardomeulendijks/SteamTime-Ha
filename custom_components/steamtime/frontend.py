"""
Serves the optional custom Lovelace card's static assets (design §12).

Registered once per HA process from `async_setup` — not `async_setup_entry`,
which can run again on every options-flow reload (`_async_reload_on_options_
update` in `__init__.py`). `async_register_static_paths` is not idempotent:
a second registration of the same URL raises, so this must not live on the
per-entry setup path.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from homeassistant.components.frontend import add_extra_js_url
from homeassistant.components.http import StaticPathConfig

from .const import FRONTEND_CARD_FILENAME, FRONTEND_CARD_URL_BASE, FRONTEND_CARD_VERSION

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

_WWW_DIR = Path(__file__).parent / "www"


async def async_register_frontend(hass: HomeAssistant) -> None:
    """Serve `www/` at `FRONTEND_CARD_URL_BASE` and auto-load the card."""
    await hass.http.async_register_static_paths(
        [
            StaticPathConfig(
                url_path=FRONTEND_CARD_URL_BASE, path=str(_WWW_DIR), cache_headers=True
            )
        ]
    )
    add_extra_js_url(
        hass,
        f"{FRONTEND_CARD_URL_BASE}/{FRONTEND_CARD_FILENAME}?v={FRONTEND_CARD_VERSION}",
    )
