"""Tests for the storage layer (design §5) — needs real HA fixtures."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest

from custom_components.steamtime.storage import (
    CUSTOM_DISH_ID_PREFIX,
    STORAGE_KEY_DISHES,
    STORAGE_KEY_HISTORY,
    STORAGE_KEY_SESSION,
    DishLibraryStore,
    HistoryStore,
    SessionStore,
)

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant


async def test_predefined_dishes_load_with_no_custom_dishes(
    hass: HomeAssistant,
) -> None:
    library = DishLibraryStore(hass)
    await library.async_load()

    assert len(library.predefined_dishes) == 10
    assert library.custom_dishes == []
    assert library.all_dishes() == library.predefined_dishes
    assert all(
        not d["id"].startswith(CUSTOM_DISH_ID_PREFIX) for d in library.predefined_dishes
    )


async def test_add_custom_dish_gets_prefixed_id_and_persists(
    hass: HomeAssistant, hass_storage: dict[str, Any]
) -> None:
    library = DishLibraryStore(hass)
    await library.async_load()

    dish = await library.async_add_custom_dish(
        name_en="Asparagus",
        name_nl="Asperges",
        steam_minutes=12,
        temperature=100,
        category="vegetables",
    )

    assert dish["id"].startswith(CUSTOM_DISH_ID_PREFIX)
    assert dish in library.custom_dishes
    assert dish in library.all_dishes()
    assert hass_storage[STORAGE_KEY_DISHES]["data"] == [dish]


async def test_update_unknown_or_predefined_dish_id_raises_keyerror(
    hass: HomeAssistant,
) -> None:
    library = DishLibraryStore(hass)
    await library.async_load()

    with pytest.raises(KeyError):
        await library.async_update_custom_dish(
            "broccoli",  # a predefined id, never in the custom store
            name_en="Hacked Broccoli",
            name_nl=None,
            steam_minutes=1,
            temperature=1,
            category="vegetables",
        )

    with pytest.raises(KeyError):
        await library.async_update_custom_dish(
            "does-not-exist",
            name_en="Ghost",
            name_nl=None,
            steam_minutes=1,
            temperature=1,
            category="other",
        )


async def test_update_and_remove_custom_dish(hass: HomeAssistant) -> None:
    library = DishLibraryStore(hass)
    await library.async_load()
    added = await library.async_add_custom_dish(
        name_en="Asparagus",
        name_nl="Asperges",
        steam_minutes=12,
        temperature=100,
        category="vegetables",
    )

    updated = await library.async_update_custom_dish(
        added["id"],
        name_en="Asparagus (green)",
        name_nl="Asperges (groen)",
        steam_minutes=14,
        temperature=100,
        category="vegetables",
    )
    assert updated["id"] == added["id"]
    assert updated["name_en"] == "Asparagus (green)"
    assert library.custom_dishes == [updated]

    await library.async_remove_custom_dish(added["id"])
    assert library.custom_dishes == []

    with pytest.raises(KeyError):
        await library.async_remove_custom_dish(added["id"])


async def test_session_store_round_trip_and_clear(
    hass: HomeAssistant, hass_storage: dict[str, Any]
) -> None:
    store = SessionStore(hass)

    assert await store.async_load() is None

    state = {
        "session_id": "s1",
        "started_at": 100.0,
        "status": "running",
        "dishes": [],
    }
    await store.async_save(state)
    assert await store.async_load() == state
    assert hass_storage[STORAGE_KEY_SESSION]["data"] == state

    await store.async_clear()
    assert STORAGE_KEY_SESSION not in hass_storage

    # A fresh instance (as after a real restart) sees no session. Checking
    # via `store` itself would hit a `mock_storage` quirk: it reuses the
    # Store's own pending-write cache as a load-side channel and never
    # clears it, so a same-instance load right after `async_remove` would
    # still see the pre-clear data even though real Store/production
    # behavior (and the `hass_storage` dict above) is correctly empty.
    assert await SessionStore(hass).async_load() is None


async def test_history_store_add_get_and_cap(
    hass: HomeAssistant, hass_storage: dict[str, Any]
) -> None:
    history = HistoryStore(hass)
    await history.async_load()

    first_id = await history.async_add_entry(completed_at=100.0, dishes=[{"id": "d1"}])
    second_id = await history.async_add_entry(completed_at=200.0, dishes=[{"id": "d1"}])

    # Newest first.
    assert [e["id"] for e in history.entries] == [second_id, first_id]
    first_entry = history.get(first_id)
    assert first_entry is not None
    assert first_entry["completed_at"] == 100.0
    assert history.get("unknown") is None
    assert hass_storage[STORAGE_KEY_HISTORY]["data"] == history.entries

    for i in range(60):
        await history.async_add_entry(completed_at=float(i), dishes=[])

    assert len(history.entries) == 50
    # The two original entries were pushed out by the cap.
    assert first_id not in [e["id"] for e in history.entries]
    assert second_id not in [e["id"] for e in history.entries]
