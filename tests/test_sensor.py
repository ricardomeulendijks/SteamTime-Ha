"""Tests for the sensor platform (design §4)."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from custom_components.steamtime.const import (
    DOMAIN,
    SERVICE_CONFIRM_DISH,
    SERVICE_START_SESSION,
)

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant, State
    from pytest_homeassistant_custom_component.common import MockConfigEntry


def _state(hass: HomeAssistant, entity_id: str) -> State:
    state = hass.states.get(entity_id)
    assert state is not None
    return state


@pytest.mark.usefixtures("entry")
async def test_session_sensor_idle_with_no_session(hass: HomeAssistant) -> None:
    state = _state(hass, "sensor.steamtime_session")
    assert state.state == "idle"
    assert state.attributes["session_id"] is None
    assert state.attributes["dishes"] == []


async def test_session_sensor_running_with_dish_attributes(
    hass: HomeAssistant, entry: MockConfigEntry
) -> None:
    await hass.services.async_call(
        DOMAIN,
        SERVICE_START_SESSION,
        {"dishes": [{"name": "Fish", "minutes": 10, "temperature": 90}]},
        blocking=True,
    )
    await hass.async_block_till_done()

    manager = entry.runtime_data.session_manager
    state = _state(hass, "sensor.steamtime_session")
    assert state.state == "running"
    assert state.attributes["session_id"] == manager.state.session_id
    dishes = state.attributes["dishes"]
    assert len(dishes) == 1
    assert dishes[0]["name"] == "Fish"
    assert dishes[0]["status"] == "ready_to_add"
    assert dishes[0]["steam_minutes"] == 10
    assert dishes[0]["temperature"] == 90
    assert dishes[0]["planned_add_at"] is not None
    assert dishes[0]["confirmed_at"] is None


async def test_next_add_and_next_done_sensors_track_the_session(
    hass: HomeAssistant, entry: MockConfigEntry
) -> None:
    assert _state(hass, "sensor.steamtime_next_add").state == "unknown"
    assert _state(hass, "sensor.steamtime_next_done").state == "unknown"

    await hass.services.async_call(
        DOMAIN,
        SERVICE_START_SESSION,
        {"dishes": [{"name": "Fish", "minutes": 10, "temperature": 90}]},
        blocking=True,
    )
    await hass.async_block_till_done()

    next_add = _state(hass, "sensor.steamtime_next_add")
    assert next_add.state != "unknown"
    assert next_add.attributes["dish_name"] == "Fish"
    assert next_add.attributes["temperature"] == 90
    # No dish is cooking yet.
    assert _state(hass, "sensor.steamtime_next_done").state == "unknown"

    manager = entry.runtime_data.session_manager
    dish_id = manager.state.dishes[0].id
    await hass.services.async_call(
        DOMAIN, SERVICE_CONFIRM_DISH, {"dish_id": dish_id}, blocking=True
    )
    await hass.async_block_till_done()

    assert _state(hass, "sensor.steamtime_next_add").state == "unknown"
    next_done = _state(hass, "sensor.steamtime_next_done")
    assert next_done.state != "unknown"
    assert next_done.attributes["dish_name"] == "Fish"
