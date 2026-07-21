"""Tests for the awaiting-confirmation binary sensor (design §4)."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from custom_components.steamtime.const import DOMAIN, SERVICE_START_SESSION

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from pytest_homeassistant_custom_component.common import MockConfigEntry


@pytest.mark.usefixtures("entry")
async def test_off_with_no_session(hass: HomeAssistant) -> None:
    state = hass.states.get("binary_sensor.steamtime_awaiting_confirmation")
    assert state is not None
    assert state.state == "off"
    assert state.attributes["dish_ids"] == []


async def test_on_when_a_dish_is_ready_to_add(
    hass: HomeAssistant, entry: MockConfigEntry
) -> None:
    await hass.services.async_call(
        DOMAIN,
        SERVICE_START_SESSION,
        {"dishes": [{"name": "Fish", "minutes": 10}]},
        blocking=True,
    )
    await hass.async_block_till_done()

    manager = entry.runtime_data.session_manager
    dish_id = manager.state.dishes[0].id

    state = hass.states.get("binary_sensor.steamtime_awaiting_confirmation")
    assert state is not None
    assert state.state == "on"
    assert state.attributes["dish_ids"] == [dish_id]
