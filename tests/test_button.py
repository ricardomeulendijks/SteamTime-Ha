"""Tests for the confirm/cancel buttons (design §4)."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from homeassistant.helpers import entity_registry as er

from custom_components.steamtime.button import (
    SteamTimeCancelButton,
    SteamTimeConfirmButton,
)
from custom_components.steamtime.const import DOMAIN, SERVICE_START_SESSION
from custom_components.steamtime.engine import DishStatus

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from pytest_homeassistant_custom_component.common import MockConfigEntry


async def test_confirm_button_confirms_the_oldest_ready_dish(
    hass: HomeAssistant, entry: MockConfigEntry
) -> None:
    await hass.services.async_call(
        DOMAIN,
        SERVICE_START_SESSION,
        {"dishes": [{"name": "Fish", "minutes": 10}, {"name": "Peas", "minutes": 10}]},
        blocking=True,
    )
    await hass.async_block_till_done()

    manager = entry.runtime_data.session_manager
    dish_0_before = manager.state.dishes[0]
    dish_1_before = manager.state.dishes[1]
    assert dish_0_before.status is DishStatus.READY_TO_ADD
    assert dish_1_before.status is DishStatus.READY_TO_ADD

    button = SteamTimeConfirmButton(entry)
    button.hass = hass
    await button.async_press()
    await hass.async_block_till_done()

    dish_0_after = manager.state.dishes[0]
    dish_1_after = manager.state.dishes[1]
    assert dish_0_after.status is DishStatus.COOKING
    assert dish_1_after.status is DishStatus.READY_TO_ADD


async def test_confirm_button_noop_when_nothing_ready(
    hass: HomeAssistant, entry: MockConfigEntry, caplog: pytest.LogCaptureFixture
) -> None:
    button = SteamTimeConfirmButton(entry)
    button.hass = hass
    await button.async_press()

    assert "no dish is awaiting confirmation" in caplog.text


async def test_cancel_button_cancels_the_session(
    hass: HomeAssistant, entry: MockConfigEntry
) -> None:
    await hass.services.async_call(
        DOMAIN,
        SERVICE_START_SESSION,
        {"dishes": [{"name": "Fish", "minutes": 10}]},
        blocking=True,
    )
    await hass.async_block_till_done()

    button = SteamTimeCancelButton(entry)
    button.hass = hass
    await button.async_press()
    await hass.async_block_till_done()

    assert entry.runtime_data.session_manager.state is None


async def test_cancel_button_noop_when_no_session(
    hass: HomeAssistant, entry: MockConfigEntry, caplog: pytest.LogCaptureFixture
) -> None:
    button = SteamTimeCancelButton(entry)
    button.hass = hass
    await button.async_press()

    assert "no session is running" in caplog.text


@pytest.mark.usefixtures("entry")
async def test_cancel_button_is_disabled_by_default(hass: HomeAssistant) -> None:
    assert hass.states.get("button.steamtime_cancel") is None

    registry = er.async_get(hass)
    registry_entry = registry.async_get("button.steamtime_cancel")
    assert registry_entry is not None
    assert registry_entry.disabled_by is er.RegistryEntryDisabler.INTEGRATION
