"""Tests for `build_session` offset calculation (design §3.1)."""

from __future__ import annotations

from custom_components.steamtime.engine import DishStatus, build_session

from .conftest import T0, dish


def test_single_dish_session_has_zero_offset() -> None:
    state = build_session("s1", [dish("Broccoli", 12)], now=T0)

    assert len(state.dishes) == 1
    only = state.dishes[0]
    assert only.id == "d1"
    assert only.planned_add_at == T0
    assert only.status is DishStatus.PENDING


def test_offsets_descend_by_steam_time() -> None:
    state = build_session(
        "s1",
        [dish("Fish", 10), dish("Potatoes", 25), dish("Carrots", 15)],
        now=T0,
    )

    # Sorted longest-first: Potatoes (25), Carrots (15), Fish (10).
    by_id = {d.id: d for d in state.dishes}
    assert by_id["d1"].name_en == "Potatoes"
    assert by_id["d1"].planned_add_at == T0
    assert by_id["d2"].name_en == "Carrots"
    assert by_id["d2"].planned_add_at == T0 + 10 * 60
    assert by_id["d3"].name_en == "Fish"
    assert by_id["d3"].planned_add_at == T0 + 15 * 60


def test_equal_steam_times_get_equal_offsets_and_no_merging() -> None:
    state = build_session(
        "s1",
        [dish("Peas", 10), dish("Beans", 10)],
        now=T0,
    )

    assert len(state.dishes) == 2
    assert all(d.planned_add_at == T0 for d in state.dishes)
    # Distinct instance ids even though offsets and steam times are identical.
    assert {d.id for d in state.dishes} == {"d1", "d2"}
