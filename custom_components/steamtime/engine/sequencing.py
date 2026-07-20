"""Session construction: sorting and offset calculation (design §3.1)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .models import Dish, SessionState

if TYPE_CHECKING:
    from collections.abc import Sequence

    from .models import DishSpec


def build_session(
    session_id: str,
    dish_specs: Sequence[DishSpec],
    now: float,
) -> SessionState:
    """
    Build a new session from selected dishes, longest steam time first.

    Each dish gets a session-scoped id (`d1`, `d2`, ...) in sequence order and
    a `planned_add_at` timestamp computed once, here, and never recalculated.
    Dish 1's offset is always 0 — its `planned_add_at` equals `now`. Callers
    must follow up with `advance(state, now)` to fire the resulting effects;
    this function only constructs state.
    """
    ordered = sorted(dish_specs, key=lambda spec: spec.steam_minutes, reverse=True)
    longest_minutes = ordered[0].steam_minutes if ordered else 0

    dishes = [
        Dish(
            id=f"d{index}",
            name_en=spec.name_en,
            name_nl=spec.name_nl,
            steam_minutes=spec.steam_minutes,
            temperature=spec.temperature,
            category=spec.category,
            planned_add_at=now + (longest_minutes - spec.steam_minutes) * 60,
        )
        for index, spec in enumerate(ordered, start=1)
    ]

    return SessionState(session_id=session_id, started_at=now, dishes=dishes)
