"""Tests for the diagnostics platform (design §9)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from custom_components.steamtime.const import DOMAIN, SERVICE_START_SESSION
from custom_components.steamtime.diagnostics import async_get_config_entry_diagnostics

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from pytest_homeassistant_custom_component.common import MockConfigEntry


async def test_diagnostics_include_dishes_session_and_history(
    hass: HomeAssistant, entry: MockConfigEntry
) -> None:
    await hass.services.async_call(
        DOMAIN,
        SERVICE_START_SESSION,
        {"dishes": [{"name": "Fish", "minutes": 10}]},
        blocking=True,
    )

    diagnostics = await async_get_config_entry_diagnostics(hass, entry)

    assert len(diagnostics["predefined_dishes"]) == 10
    assert diagnostics["custom_dishes"] == []
    assert diagnostics["live_session"] is not None
    assert diagnostics["live_session"]["dishes"][0]["name_en"] == "Fish"
    assert diagnostics["history"] == []


async def test_diagnostics_with_no_session_running(
    hass: HomeAssistant, entry: MockConfigEntry
) -> None:
    diagnostics = await async_get_config_entry_diagnostics(hass, entry)

    assert diagnostics["live_session"] is None
