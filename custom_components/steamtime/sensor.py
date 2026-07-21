"""Sensor platform: session, next-add, next-done (design §4)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity

from .engine import Dish, DishStatus, SessionState
from .entity import SteamTimeEntity
from .localization import resolve_dish_name

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

    from .data import SteamTimeConfigEntry


async def async_setup_entry(
    _hass: HomeAssistant,
    entry: SteamTimeConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the session, next-add, and next-done sensors."""
    async_add_entities(
        [
            SteamTimeSessionSensor(entry),
            SteamTimeNextAddSensor(entry),
            SteamTimeNextDoneSensor(entry),
        ]
    )


def _iso(timestamp: float | None) -> str | None:
    """Convert an epoch timestamp to an ISO 8601 UTC string (design §4)."""
    if timestamp is None:
        return None
    return datetime.fromtimestamp(timestamp, tz=UTC).isoformat()


def _dish_attrs(dish: Dish, language: str) -> dict[str, Any]:
    """Build the session sensor's per-dish attribute shape (design §4)."""
    return {
        "id": dish.id,
        "name": resolve_dish_name(dish.name_en, dish.name_nl, language),
        "status": dish.status.value,
        "planned_add_at": _iso(dish.planned_add_at),
        "confirmed_at": _iso(dish.confirmed_at),
        "done_at": _iso(dish.done_at),
        "steam_minutes": dish.steam_minutes,
        "temperature": dish.temperature,
    }


class SteamTimeSessionSensor(SteamTimeEntity, SensorEntity):
    """`idle` | `running`, with the full dish list as an attribute."""

    _attr_translation_key = "session"

    def __init__(self, entry: SteamTimeConfigEntry) -> None:
        """Set up the sensor for this config entry."""
        super().__init__(entry.entry_id, "session")
        self._entry = entry

    @property
    def native_value(self) -> str:
        """`running` if a session is live, else `idle`."""
        return "running" if self._entry.runtime_data.session_manager.state else "idle"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """session_id, started_at, and the per-dish attribute list."""
        state = self._entry.runtime_data.session_manager.state
        if state is None:
            return {"session_id": None, "started_at": None, "dishes": []}

        language = self.hass.config.language
        return {
            "session_id": state.session_id,
            "started_at": _iso(state.started_at),
            "dishes": [_dish_attrs(dish, language) for dish in state.dishes],
        }


def _earliest_add_target(state: SessionState) -> Dish | None:
    """Return the dish with the earliest plannedAddAt among pending/ready dishes."""
    candidates = [
        dish
        for dish in state.dishes
        if dish.status in (DishStatus.PENDING, DishStatus.READY_TO_ADD)
    ]
    if not candidates:
        return None
    return min(candidates, key=lambda dish: dish.planned_add_at)


def _earliest_done_target(state: SessionState) -> Dish | None:
    """Return the cooking dish with the earliest doneAt."""
    candidates = [dish for dish in state.dishes if dish.status is DishStatus.COOKING]
    if not candidates:
        return None
    return min(candidates, key=lambda dish: dish.done_at or float("inf"))


class SteamTimeNextAddSensor(SteamTimeEntity, SensorEntity):
    """When the next dish should be added — a past timestamp if it's ready now."""

    _attr_translation_key = "next_add"
    _attr_device_class = SensorDeviceClass.TIMESTAMP

    def __init__(self, entry: SteamTimeConfigEntry) -> None:
        """Set up the sensor for this config entry."""
        super().__init__(entry.entry_id, "next_add")
        self._entry = entry

    @property
    def native_value(self) -> datetime | None:
        """The earliest plannedAddAt still pending confirmation, if any."""
        state = self._entry.runtime_data.session_manager.state
        if state is None:
            return None
        dish = _earliest_add_target(state)
        if dish is None:
            return None
        return datetime.fromtimestamp(dish.planned_add_at, tz=UTC)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """dish_id, dish_name, temperature of the relevant dish, if any."""
        state = self._entry.runtime_data.session_manager.state
        dish = _earliest_add_target(state) if state is not None else None
        if dish is None:
            return {"dish_id": None, "dish_name": None, "temperature": None}
        return {
            "dish_id": dish.id,
            "dish_name": resolve_dish_name(
                dish.name_en, dish.name_nl, self.hass.config.language
            ),
            "temperature": dish.temperature,
        }


class SteamTimeNextDoneSensor(SteamTimeEntity, SensorEntity):
    """Earliest doneAt among currently cooking dishes."""

    _attr_translation_key = "next_done"
    _attr_device_class = SensorDeviceClass.TIMESTAMP

    def __init__(self, entry: SteamTimeConfigEntry) -> None:
        """Set up the sensor for this config entry."""
        super().__init__(entry.entry_id, "next_done")
        self._entry = entry

    @property
    def native_value(self) -> datetime | None:
        """The earliest doneAt among cooking dishes, if any."""
        state = self._entry.runtime_data.session_manager.state
        if state is None:
            return None
        dish = _earliest_done_target(state)
        if dish is None or dish.done_at is None:
            return None
        return datetime.fromtimestamp(dish.done_at, tz=UTC)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """dish_id and dish_name of the relevant dish, if any."""
        state = self._entry.runtime_data.session_manager.state
        dish = _earliest_done_target(state) if state is not None else None
        if dish is None:
            return {"dish_id": None, "dish_name": None}
        return {
            "dish_id": dish.id,
            "dish_name": resolve_dish_name(
                dish.name_en, dish.name_nl, self.hass.config.language
            ),
        }
