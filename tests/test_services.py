"""Tests for the service command surface (design §6)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, cast

import pytest
import voluptuous as vol
from homeassistant.exceptions import ServiceValidationError
from pytest_homeassistant_custom_component.common import async_fire_time_changed

from custom_components.steamtime.const import (
    DOMAIN,
    SERVICE_ADD_DISH,
    SERVICE_CANCEL_SESSION,
    SERVICE_CONFIRM_DISH,
    SERVICE_GET_DISHES,
    SERVICE_GET_HISTORY,
    SERVICE_REMOVE_DISH,
    SERVICE_RESTART_SESSION,
    SERVICE_START_SESSION,
    SERVICE_UPDATE_DISH,
)
from custom_components.steamtime.engine import DishStatus

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from pytest_homeassistant_custom_component.common import MockConfigEntry


async def test_start_session_with_dish_id_reference_and_minutes_override(
    hass: HomeAssistant, entry: MockConfigEntry
) -> None:
    await hass.services.async_call(
        DOMAIN,
        SERVICE_START_SESSION,
        {"dishes": [{"dish_id": "broccoli", "minutes": 7}]},
        blocking=True,
    )

    manager = entry.runtime_data.session_manager
    assert manager.state is not None
    dish = manager.state.dishes[0]
    assert dish.name_en == "Broccoli"
    assert dish.steam_minutes == 7  # overridden, not the predefined 10


async def test_start_session_with_inline_dish_defaults_category_and_temperature(
    hass: HomeAssistant, entry: MockConfigEntry
) -> None:
    await hass.services.async_call(
        DOMAIN,
        SERVICE_START_SESSION,
        {"dishes": [{"name": "Leftover stew", "minutes": 15}]},
        blocking=True,
    )

    manager = entry.runtime_data.session_manager
    assert manager.state is not None
    dish = manager.state.dishes[0]
    assert dish.name_en == "Leftover stew"
    assert dish.name_nl is None
    assert dish.category == "other"
    assert dish.temperature == 100


@pytest.mark.usefixtures("entry")
async def test_start_session_unknown_dish_id_raises(hass: HomeAssistant) -> None:
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            DOMAIN,
            SERVICE_START_SESSION,
            {"dishes": [{"dish_id": "does-not-exist"}]},
            blocking=True,
        )


@pytest.mark.usefixtures("entry")
async def test_start_session_already_running_raises(hass: HomeAssistant) -> None:
    await hass.services.async_call(
        DOMAIN,
        SERVICE_START_SESSION,
        {"dishes": [{"name": "Fish", "minutes": 10}]},
        blocking=True,
    )

    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            DOMAIN,
            SERVICE_START_SESSION,
            {"dishes": [{"name": "Peas", "minutes": 5}]},
            blocking=True,
        )


async def test_confirm_dish_via_service(
    hass: HomeAssistant, entry: MockConfigEntry
) -> None:
    await hass.services.async_call(
        DOMAIN,
        SERVICE_START_SESSION,
        {"dishes": [{"name": "Fish", "minutes": 10}]},
        blocking=True,
    )
    manager = entry.runtime_data.session_manager
    assert manager.state is not None
    dish_id = manager.state.dishes[0].id

    await hass.services.async_call(
        DOMAIN, SERVICE_CONFIRM_DISH, {"dish_id": dish_id}, blocking=True
    )

    assert manager.state.dishes[0].status is DishStatus.COOKING


async def test_cancel_session_via_service(
    hass: HomeAssistant, entry: MockConfigEntry
) -> None:
    await hass.services.async_call(
        DOMAIN,
        SERVICE_START_SESSION,
        {"dishes": [{"name": "Fish", "minutes": 10}]},
        blocking=True,
    )

    await hass.services.async_call(DOMAIN, SERVICE_CANCEL_SESSION, {}, blocking=True)

    assert entry.runtime_data.session_manager.state is None


@pytest.mark.usefixtures("entry")
async def test_add_dish_then_get_dishes_includes_it(hass: HomeAssistant) -> None:
    await hass.services.async_call(
        DOMAIN,
        SERVICE_ADD_DISH,
        {
            "name": "Asparagus",
            "minutes": 12,
            "temperature": 100,
            "category": "vegetables",
        },
        blocking=True,
    )

    response = await hass.services.async_call(
        DOMAIN, SERVICE_GET_DISHES, {}, blocking=True, return_response=True
    )
    assert response is not None
    dishes = cast("list[dict[str, Any]]", response["dishes"])
    names = [d["name_en"] for d in dishes]
    assert "Asparagus" in names
    assert "Broccoli" in names  # predefined dishes are still there


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("name", ""),
        ("name", "x" * 101),
        ("minutes", 0),
        ("minutes", 601),
        ("temperature", 0),
        ("temperature", 251),
        ("category", "dessert"),
    ],
)
@pytest.mark.usefixtures("entry")
async def test_add_dish_validation_bounds(
    hass: HomeAssistant, field: str, value: Any
) -> None:
    data = {"name": "Test", "minutes": 10, "temperature": 100, "category": "other"}
    data[field] = value

    with pytest.raises(vol.Invalid):
        await hass.services.async_call(DOMAIN, SERVICE_ADD_DISH, data, blocking=True)


async def test_update_dish_replaces_fields(
    hass: HomeAssistant, entry: MockConfigEntry
) -> None:
    await hass.services.async_call(
        DOMAIN,
        SERVICE_ADD_DISH,
        {
            "name": "Asparagus",
            "minutes": 12,
            "temperature": 100,
            "category": "vegetables",
        },
        blocking=True,
    )
    dish_id = entry.runtime_data.dish_library.custom_dishes[0]["id"]

    await hass.services.async_call(
        DOMAIN,
        SERVICE_UPDATE_DISH,
        {
            "dish_id": dish_id,
            "name": "Asparagus (green)",
            "minutes": 14,
            "temperature": 100,
            "category": "vegetables",
        },
        blocking=True,
    )

    updated = entry.runtime_data.dish_library.custom_dishes[0]
    assert updated["name_en"] == "Asparagus (green)"
    assert updated["steam_minutes"] == 14


@pytest.mark.usefixtures("entry")
async def test_update_dish_unknown_or_predefined_raises(hass: HomeAssistant) -> None:
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            DOMAIN,
            SERVICE_UPDATE_DISH,
            {
                "dish_id": "broccoli",
                "name": "Hacked",
                "minutes": 1,
                "temperature": 1,
                "category": "other",
            },
            blocking=True,
        )


async def test_remove_dish(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    await hass.services.async_call(
        DOMAIN,
        SERVICE_ADD_DISH,
        {
            "name": "Asparagus",
            "minutes": 12,
            "temperature": 100,
            "category": "vegetables",
        },
        blocking=True,
    )
    dish_id = entry.runtime_data.dish_library.custom_dishes[0]["id"]

    await hass.services.async_call(
        DOMAIN, SERVICE_REMOVE_DISH, {"dish_id": dish_id}, blocking=True
    )

    assert entry.runtime_data.dish_library.custom_dishes == []


@pytest.mark.usefixtures("entry")
async def test_remove_dish_unknown_or_predefined_raises(hass: HomeAssistant) -> None:
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            DOMAIN, SERVICE_REMOVE_DISH, {"dish_id": "broccoli"}, blocking=True
        )


async def test_get_history_and_restart_session(
    hass: HomeAssistant, entry: MockConfigEntry
) -> None:
    manager = entry.runtime_data.session_manager
    await hass.services.async_call(
        DOMAIN,
        SERVICE_START_SESSION,
        {"dishes": [{"name": "Fish", "minutes": 1}]},
        blocking=True,
    )
    assert manager.state is not None
    dish_id = manager.state.dishes[0].id
    confirmed_at = manager.state.dishes[0].planned_add_at
    await manager.async_confirm_dish(dish_id, confirmed_at)
    done_at = manager.state.dishes[0].done_at
    assert done_at is not None

    # Let the dish's armed timer fire for real, completing the session
    # through the manager's normal production code path.
    async_fire_time_changed(hass, datetime.fromtimestamp(done_at + 1, tz=UTC))
    await hass.async_block_till_done()
    assert manager.state is None

    response = await hass.services.async_call(
        DOMAIN, SERVICE_GET_HISTORY, {}, blocking=True, return_response=True
    )
    assert response is not None
    history = cast("list[dict[str, Any]]", response["history"])
    assert len(history) == 1
    history_id = history[0]["id"]

    await hass.services.async_call(
        DOMAIN,
        SERVICE_RESTART_SESSION,
        {"history_id": history_id},
        blocking=True,
    )
    assert manager.state is not None
    assert manager.state.dishes[0].name_en == "Fish"


@pytest.mark.usefixtures("entry")
async def test_restart_session_unknown_history_id_raises(hass: HomeAssistant) -> None:
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            DOMAIN,
            SERVICE_RESTART_SESSION,
            {"history_id": "does-not-exist"},
            blocking=True,
        )
