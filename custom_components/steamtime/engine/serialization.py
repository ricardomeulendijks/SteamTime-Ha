"""
Plain-dict serialization for `SessionState` (design §3, §5).

Only `str | int | float | None` values and lists/dicts of them — safe to hand
to `homeassistant.helpers.storage.Store` unchanged.
"""

from __future__ import annotations

from typing import Any

from .models import Dish, DishStatus, SessionState, SessionStatus


def dish_to_dict(dish: Dish) -> dict[str, Any]:
    """Serialize one `Dish` to a plain dict."""
    return {
        "id": dish.id,
        "name_en": dish.name_en,
        "name_nl": dish.name_nl,
        "steam_minutes": dish.steam_minutes,
        "temperature": dish.temperature,
        "category": dish.category,
        "planned_add_at": dish.planned_add_at,
        "status": dish.status.value,
        "confirmed_at": dish.confirmed_at,
        "done_at": dish.done_at,
    }


def dish_from_dict(data: dict[str, Any]) -> Dish:
    """Deserialize one `Dish` from a plain dict."""
    return Dish(
        id=data["id"],
        name_en=data["name_en"],
        name_nl=data["name_nl"],
        steam_minutes=data["steam_minutes"],
        temperature=data["temperature"],
        category=data["category"],
        planned_add_at=data["planned_add_at"],
        status=DishStatus(data["status"]),
        confirmed_at=data["confirmed_at"],
        done_at=data["done_at"],
    )


def session_to_dict(state: SessionState) -> dict[str, Any]:
    """Serialize a `SessionState` to a plain dict."""
    return {
        "session_id": state.session_id,
        "started_at": state.started_at,
        "status": state.status.value,
        "dishes": [dish_to_dict(dish) for dish in state.dishes],
    }


def session_from_dict(data: dict[str, Any]) -> SessionState:
    """Deserialize a `SessionState` from a plain dict."""
    return SessionState(
        session_id=data["session_id"],
        started_at=data["started_at"],
        status=SessionStatus(data["status"]),
        dishes=[dish_from_dict(dish) for dish in data["dishes"]],
    )
