"""
Persistence layer: the three `Store` objects (design §5).

`dishes_predefined.json` schema (one object per entry, plain JSON array):
    {id, name_en, name_nl, steam_minutes, temperature, category}
Placeholder content only — the product owner supplies real dish data later
(design §8); ids here are plain slugs, never `custom_`-prefixed.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any, TypedDict, cast
from uuid import uuid4

from homeassistant.helpers.storage import Store
from homeassistant.util.json import load_json_array

from .const import DOMAIN

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

STORAGE_VERSION = 1
STORAGE_KEY_DISHES = f"{DOMAIN}.dishes"
STORAGE_KEY_SESSION = f"{DOMAIN}.session"
STORAGE_KEY_HISTORY = f"{DOMAIN}.history"

CUSTOM_DISH_ID_PREFIX = "custom_"
HISTORY_MAX_ENTRIES = 50

PREDEFINED_DISHES_PATH = Path(__file__).parent / "dishes_predefined.json"


class DishRecord(TypedDict):
    """One dish-library entry, predefined or custom."""

    id: str
    name_en: str
    name_nl: str | None
    steam_minutes: int
    temperature: int
    category: str


class HistoryEntry(TypedDict):
    """One completed-session snapshot (design §3.3, §5)."""

    id: str
    completed_at: float
    dishes: list[dict[str, Any]]


class DishLibraryStore:
    """Predefined (bundled, read-only) + custom (persisted) dishes."""

    def __init__(self, hass: HomeAssistant) -> None:
        """Set up the store; call `async_load` before use."""
        self._hass = hass
        self._store: Store[list[DishRecord]] = Store(
            hass, STORAGE_VERSION, STORAGE_KEY_DISHES
        )
        self._predefined: list[DishRecord] | None = None
        self._custom: list[DishRecord] | None = None

    async def async_load(self) -> None:
        """Load bundled predefined dishes and persisted custom dishes."""
        self._predefined = cast(
            "list[DishRecord]",
            await self._hass.async_add_executor_job(
                load_json_array, PREDEFINED_DISHES_PATH
            ),
        )
        self._custom = await self._store.async_load() or []

    @property
    def custom_dishes(self) -> list[DishRecord]:
        """The user's custom dishes. Call `async_load` first."""
        if self._custom is None:
            msg = "DishLibraryStore.async_load was not called"
            raise RuntimeError(msg)
        return self._custom

    @property
    def predefined_dishes(self) -> list[DishRecord]:
        """The bundled predefined dishes. Call `async_load` first."""
        if self._predefined is None:
            msg = "DishLibraryStore.async_load was not called"
            raise RuntimeError(msg)
        return self._predefined

    def all_dishes(self) -> list[DishRecord]:
        """Predefined dishes followed by custom dishes."""
        return [*self.predefined_dishes, *self.custom_dishes]

    async def async_add_custom_dish(
        self,
        *,
        name_en: str,
        name_nl: str | None,
        steam_minutes: int,
        temperature: int,
        category: str,
    ) -> DishRecord:
        """Add a custom dish, assigning it a `custom_`-prefixed id."""
        dish: DishRecord = {
            "id": f"{CUSTOM_DISH_ID_PREFIX}{uuid4().hex}",
            "name_en": name_en,
            "name_nl": name_nl,
            "steam_minutes": steam_minutes,
            "temperature": temperature,
            "category": category,
        }
        self.custom_dishes.append(dish)
        await self._store.async_save(self.custom_dishes)
        return dish

    async def async_update_custom_dish(  # noqa: PLR0913
        self,
        dish_id: str,
        *,
        name_en: str,
        name_nl: str | None,
        steam_minutes: int,
        temperature: int,
        category: str,
    ) -> DishRecord:
        """
        Replace a custom dish's fields. Raises `KeyError` if unknown.

        Predefined dishes are never in `custom_dishes`, so an attempt to
        update one naturally raises `KeyError` here (design §6).
        """
        dishes = self.custom_dishes
        index = next((i for i, d in enumerate(dishes) if d["id"] == dish_id), None)
        if index is None:
            raise KeyError(dish_id)

        updated: DishRecord = {
            "id": dish_id,
            "name_en": name_en,
            "name_nl": name_nl,
            "steam_minutes": steam_minutes,
            "temperature": temperature,
            "category": category,
        }
        dishes[index] = updated
        await self._store.async_save(dishes)
        return updated

    async def async_remove_custom_dish(self, dish_id: str) -> None:
        """Remove a custom dish. Raises `KeyError` if unknown (design §6)."""
        dishes = self.custom_dishes
        index = next((i for i, d in enumerate(dishes) if d["id"] == dish_id), None)
        if index is None:
            raise KeyError(dish_id)

        del dishes[index]
        await self._store.async_save(dishes)


class SessionStore:
    """The single live-session slot (design §5, item 2)."""

    def __init__(self, hass: HomeAssistant) -> None:
        """Set up the store."""
        self._store: Store[dict[str, Any]] = Store(
            hass, STORAGE_VERSION, STORAGE_KEY_SESSION
        )

    async def async_load(self) -> dict[str, Any] | None:
        """Return the persisted engine state dict, or None if no session."""
        return await self._store.async_load()

    async def async_save(self, state: dict[str, Any]) -> None:
        """Persist the engine state dict. Awaited before effects fire."""
        await self._store.async_save(state)

    async def async_clear(self) -> None:
        """Clear the live session (completion or cancellation)."""
        await self._store.async_remove()


class HistoryStore:
    """Completed-session snapshots, newest first, capped (design §5, item 3)."""

    def __init__(self, hass: HomeAssistant) -> None:
        """Set up the store; call `async_load` before use."""
        self._store: Store[list[HistoryEntry]] = Store(
            hass, STORAGE_VERSION, STORAGE_KEY_HISTORY
        )
        self._entries: list[HistoryEntry] | None = None

    async def async_load(self) -> None:
        """Load persisted history entries."""
        self._entries = await self._store.async_load() or []

    @property
    def entries(self) -> list[HistoryEntry]:
        """All history entries, newest first. Call `async_load` first."""
        if self._entries is None:
            msg = "HistoryStore.async_load was not called"
            raise RuntimeError(msg)
        return self._entries

    def get(self, history_id: str) -> HistoryEntry | None:
        """Look up one entry by id, e.g. for `restart_session` (design §6)."""
        return next((e for e in self.entries if e["id"] == history_id), None)

    async def async_add_entry(
        self, *, completed_at: float, dishes: list[dict[str, Any]]
    ) -> str:
        """Prepend a completed-session snapshot, capping at 50 entries."""
        entry: HistoryEntry = {
            "id": uuid4().hex,
            "completed_at": completed_at,
            "dishes": dishes,
        }
        entries = self.entries
        entries.insert(0, entry)
        del entries[HISTORY_MAX_ENTRIES:]
        await self._store.async_save(entries)
        return entry["id"]
