"""Tests for the custom Lovelace card's static-asset registration (design §12)."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from homeassistant.components.frontend import DATA_EXTRA_MODULE_URL

from custom_components.steamtime.const import (
    FRONTEND_CARD_FILENAME,
    FRONTEND_CARD_URL_BASE,
    FRONTEND_CARD_VERSION,
)

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from pytest_homeassistant_custom_component.common import MockConfigEntry
    from pytest_homeassistant_custom_component.typing import ClientSessionGenerator

_CARD_PATH = (
    Path(__file__).resolve().parent.parent
    / "custom_components"
    / "steamtime"
    / "www"
    / FRONTEND_CARD_FILENAME
)

_EXPECTED_MODULE_URL = (
    f"{FRONTEND_CARD_URL_BASE}/{FRONTEND_CARD_FILENAME}?v={FRONTEND_CARD_VERSION}"
)


async def test_card_served_at_registered_url(
    hass_client: ClientSessionGenerator,
    entry: MockConfigEntry,  # noqa: ARG001 - dependency, triggers component setup
) -> None:
    client = await hass_client()
    resp = await client.get(f"{FRONTEND_CARD_URL_BASE}/{FRONTEND_CARD_FILENAME}")
    assert resp.status == 200
    body = await resp.read()
    assert body == _CARD_PATH.read_bytes()


async def test_card_registered_as_extra_module_url(
    hass: HomeAssistant,
    entry: MockConfigEntry,  # noqa: ARG001 - dependency, triggers component setup
) -> None:
    assert _EXPECTED_MODULE_URL in hass.data[DATA_EXTRA_MODULE_URL].urls
