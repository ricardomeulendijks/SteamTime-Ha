"""The service command surface (design §6)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import voluptuous as vol
from homeassistant.core import SupportsResponse
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.dispatcher import async_dispatcher_send

from .const import (
    DISH_CATEGORIES,
    DISH_DEFAULT_CATEGORY,
    DISH_DEFAULT_TEMPERATURE,
    DISH_MINUTES_MAX,
    DISH_MINUTES_MIN,
    DISH_NAME_MAX_LENGTH,
    DISH_NAME_MIN_LENGTH,
    DISH_TEMPERATURE_MAX,
    DISH_TEMPERATURE_MIN,
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
    SIGNAL_DISH_LIBRARY_UPDATED,
)
from .engine import DishSpec
from .session_manager import SessionAlreadyRunningError

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant, ServiceCall, ServiceResponse

    from .data import SteamTimeConfigEntry

_MINUTES = vol.All(
    vol.Coerce(int), vol.Range(min=DISH_MINUTES_MIN, max=DISH_MINUTES_MAX)
)
_TEMPERATURE = vol.All(
    vol.Coerce(int), vol.Range(min=DISH_TEMPERATURE_MIN, max=DISH_TEMPERATURE_MAX)
)
_DISH_NAME = vol.All(
    cv.string, vol.Length(min=DISH_NAME_MIN_LENGTH, max=DISH_NAME_MAX_LENGTH)
)
_CATEGORY = vol.In(DISH_CATEGORIES)

_SESSION_DISH_SCHEMA = vol.Any(
    vol.Schema(
        {
            vol.Required("dish_id"): cv.string,
            vol.Optional("minutes"): _MINUTES,
        }
    ),
    vol.Schema(
        {
            vol.Required("name"): _DISH_NAME,
            vol.Required("minutes"): _MINUTES,
            vol.Optional("temperature"): _TEMPERATURE,
        }
    ),
)

START_SESSION_SCHEMA = vol.Schema(
    {
        vol.Required("dishes"): vol.All(
            cv.ensure_list, [_SESSION_DISH_SCHEMA], vol.Length(min=1)
        ),
    }
)

CONFIRM_DISH_SCHEMA = vol.Schema({vol.Required("dish_id"): cv.string})

DISH_FIELDS_SCHEMA = {
    vol.Required("name"): _DISH_NAME,
    vol.Required("minutes"): _MINUTES,
    vol.Required("temperature"): _TEMPERATURE,
    vol.Required("category"): _CATEGORY,
}

ADD_DISH_SCHEMA = vol.Schema(DISH_FIELDS_SCHEMA)
UPDATE_DISH_SCHEMA = vol.Schema(
    {vol.Required("dish_id"): cv.string, **DISH_FIELDS_SCHEMA}
)
REMOVE_DISH_SCHEMA = vol.Schema({vol.Required("dish_id"): cv.string})
RESTART_SESSION_SCHEMA = vol.Schema({vol.Required("history_id"): cv.string})


def _now() -> float:
    """Return the current time as epoch UTC seconds (the service call time)."""
    return datetime.now(UTC).timestamp()


def _dish_spec_from_session_entry(
    entry: SteamTimeConfigEntry, dish: dict[str, Any]
) -> DishSpec:
    """Resolve one `start_session` dish entry (library ref or inline) to a DishSpec."""
    if "dish_id" in dish:
        library = entry.runtime_data.dish_library
        record = next(
            (d for d in library.all_dishes() if d["id"] == dish["dish_id"]), None
        )
        if record is None:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="unknown_dish_id",
                translation_placeholders={"dish_id": dish["dish_id"]},
            )
        return DishSpec(
            name_en=record["name_en"],
            name_nl=record["name_nl"],
            steam_minutes=dish.get("minutes", record["steam_minutes"]),
            temperature=record["temperature"],
            category=record["category"],
        )

    # Inline one-off dish (design §6): shown as typed, untranslated (§8),
    # and has no category in the schema — defaults to DISH_DEFAULT_CATEGORY.
    return DishSpec(
        name_en=dish["name"],
        name_nl=None,
        steam_minutes=dish["minutes"],
        temperature=dish.get("temperature", DISH_DEFAULT_TEMPERATURE),
        category=DISH_DEFAULT_CATEGORY,
    )


async def async_setup_services(
    hass: HomeAssistant, entry: SteamTimeConfigEntry
) -> None:
    """Register the full command surface for this (single) config entry."""

    async def start_session(call: ServiceCall) -> None:
        dish_specs = [
            _dish_spec_from_session_entry(entry, dish) for dish in call.data["dishes"]
        ]
        try:
            await entry.runtime_data.session_manager.async_start_session(dish_specs)
        except SessionAlreadyRunningError as err:
            raise ServiceValidationError(
                translation_domain=DOMAIN, translation_key="session_already_running"
            ) from err

    async def confirm_dish(call: ServiceCall) -> None:
        await entry.runtime_data.session_manager.async_confirm_dish(
            call.data["dish_id"], _now()
        )

    async def cancel_session(_call: ServiceCall) -> None:
        await entry.runtime_data.session_manager.async_cancel_session()

    async def add_dish(call: ServiceCall) -> None:
        await entry.runtime_data.dish_library.async_add_custom_dish(
            name_en=call.data["name"],
            name_nl=None,
            steam_minutes=call.data["minutes"],
            temperature=call.data["temperature"],
            category=call.data["category"],
        )
        async_dispatcher_send(hass, SIGNAL_DISH_LIBRARY_UPDATED)

    async def update_dish(call: ServiceCall) -> None:
        try:
            await entry.runtime_data.dish_library.async_update_custom_dish(
                call.data["dish_id"],
                name_en=call.data["name"],
                name_nl=None,
                steam_minutes=call.data["minutes"],
                temperature=call.data["temperature"],
                category=call.data["category"],
            )
        except KeyError as err:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="unknown_or_predefined_dish_id",
                translation_placeholders={"dish_id": call.data["dish_id"]},
            ) from err
        async_dispatcher_send(hass, SIGNAL_DISH_LIBRARY_UPDATED)

    async def remove_dish(call: ServiceCall) -> None:
        try:
            await entry.runtime_data.dish_library.async_remove_custom_dish(
                call.data["dish_id"]
            )
        except KeyError as err:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="unknown_or_predefined_dish_id",
                translation_placeholders={"dish_id": call.data["dish_id"]},
            ) from err
        async_dispatcher_send(hass, SIGNAL_DISH_LIBRARY_UPDATED)

    async def get_dishes(_call: ServiceCall) -> ServiceResponse:
        dishes = entry.runtime_data.dish_library.all_dishes()
        response: dict[str, Any] = {"dishes": list(dishes)}
        return response

    async def get_history(_call: ServiceCall) -> ServiceResponse:
        history = entry.runtime_data.history.entries
        response: dict[str, Any] = {"history": list(history)}
        return response

    async def restart_session(call: ServiceCall) -> None:
        history_entry = entry.runtime_data.history.get(call.data["history_id"])
        if history_entry is None:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="unknown_history_id",
                translation_placeholders={"history_id": call.data["history_id"]},
            )

        dish_specs = [
            DishSpec(
                name_en=dish["name_en"],
                name_nl=dish["name_nl"],
                steam_minutes=dish["steam_minutes"],
                temperature=dish["temperature"],
                category=dish["category"],
            )
            for dish in history_entry["dishes"]
        ]
        try:
            await entry.runtime_data.session_manager.async_start_session(dish_specs)
        except SessionAlreadyRunningError as err:
            raise ServiceValidationError(
                translation_domain=DOMAIN, translation_key="session_already_running"
            ) from err

    hass.services.async_register(
        DOMAIN, SERVICE_START_SESSION, start_session, schema=START_SESSION_SCHEMA
    )
    hass.services.async_register(
        DOMAIN, SERVICE_CONFIRM_DISH, confirm_dish, schema=CONFIRM_DISH_SCHEMA
    )
    hass.services.async_register(DOMAIN, SERVICE_CANCEL_SESSION, cancel_session)
    hass.services.async_register(
        DOMAIN, SERVICE_ADD_DISH, add_dish, schema=ADD_DISH_SCHEMA
    )
    hass.services.async_register(
        DOMAIN, SERVICE_UPDATE_DISH, update_dish, schema=UPDATE_DISH_SCHEMA
    )
    hass.services.async_register(
        DOMAIN, SERVICE_REMOVE_DISH, remove_dish, schema=REMOVE_DISH_SCHEMA
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_GET_DISHES,
        get_dishes,
        supports_response=SupportsResponse.ONLY,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_GET_HISTORY,
        get_history,
        supports_response=SupportsResponse.ONLY,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_RESTART_SESSION,
        restart_session,
        schema=RESTART_SESSION_SCHEMA,
    )


def async_unload_services(hass: HomeAssistant) -> None:
    """Remove every registered service (single config entry, so unload = all)."""
    for service in (
        SERVICE_START_SESSION,
        SERVICE_CONFIRM_DISH,
        SERVICE_CANCEL_SESSION,
        SERVICE_ADD_DISH,
        SERVICE_UPDATE_DISH,
        SERVICE_REMOVE_DISH,
        SERVICE_GET_DISHES,
        SERVICE_GET_HISTORY,
        SERVICE_RESTART_SESSION,
    ):
        hass.services.async_remove(DOMAIN, service)
