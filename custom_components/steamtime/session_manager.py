"""
Runtime: hosts the live engine instance (design §2, §3.4, §5.2).

The only writer of session state. Arms/cancels `async_track_point_in_time`
callbacks for the engine's next due target, persists state on every
transition before firing its effects, and notifies entities via a
dispatcher signal.
"""

from __future__ import annotations

import asyncio
from dataclasses import asdict
from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import uuid4

from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.event import async_track_point_in_utc_time

from .const import (
    EVENT_ADD_DISH,
    EVENT_DISH_DONE,
    EVENT_SESSION_CANCELLED,
    EVENT_SESSION_COMPLETED,
    LOGGER,
    SIGNAL_SESSION_UPDATED,
)
from .engine import (
    AddAlertEffect,
    Dish,
    DishStatus,
    DoneAlertEffect,
    SessionCancelledEffect,
    SessionCompletedEffect,
    SessionState,
    SessionStatus,
    advance,
    build_session,
    cancel_session,
    confirm_dish,
    session_from_dict,
    session_to_dict,
)
from .localization import resolve_dish_name

if TYPE_CHECKING:
    from collections.abc import Sequence

    from homeassistant.core import CALLBACK_TYPE, HomeAssistant

    from .engine import DishSpec, Effect
    from .storage import HistoryStore, SessionStore


class SessionAlreadyRunningError(HomeAssistantError):
    """Raised by `async_start_session` when a session is already running."""


def _now() -> float:
    """Return the current time as epoch UTC seconds."""
    return datetime.now(UTC).timestamp()


def _next_target(state: SessionState) -> float | None:
    """Return the earliest future timestamp `state` needs re-evaluating at."""
    targets = [d.planned_add_at for d in state.dishes if d.status is DishStatus.PENDING]
    targets += [
        d.done_at
        for d in state.dishes
        if d.status is DishStatus.COOKING and d.done_at is not None
    ]
    return min(targets) if targets else None


class SessionManager:
    """Owns the live `SessionState` and its timer."""

    def __init__(
        self,
        hass: HomeAssistant,
        session_store: SessionStore,
        history_store: HistoryStore,
    ) -> None:
        """Set up the manager. Call `async_setup` before use."""
        self.hass = hass
        self._session_store = session_store
        self._history_store = history_store
        self.state: SessionState | None = None
        self._unsub_timer: CALLBACK_TYPE | None = None
        # Serializes every state transition below. `_process` awaits a store
        # write with self.state left unset (start) or unchanged (confirm/
        # cancel) across that await, so without this lock two concurrent
        # calls (e.g. a double-tapped start_session) could both pass their
        # guard check before either one's effect on self.state lands.
        self._lock = asyncio.Lock()

    async def async_setup(self) -> None:
        """Restore a persisted live session, fast-forwarding it (design §5.2)."""
        async with self._lock:
            data = await self._session_store.async_load()
            if data is None:
                return

            state = session_from_dict(data)
            state, effects = advance(state, _now())
            await self._process(state, effects)

    async def async_unload(self) -> None:
        """Cancel the armed timer callback, if any."""
        self._cancel_timer()

    async def async_start_session(self, dish_specs: Sequence[DishSpec]) -> None:
        """Build and start a new session. Raises if one is already running."""
        async with self._lock:
            if self.state is not None:
                raise SessionAlreadyRunningError

            state = build_session(uuid4().hex, dish_specs, _now())
            state, effects = advance(state, _now())
            await self._process(state, effects)

    async def async_confirm_dish(self, dish_id: str, at: float) -> None:
        """Confirm a dish. A no-op warning if not ready, unknown, or no session."""
        async with self._lock:
            if self.state is None:
                LOGGER.warning("confirm_dish(%s): no session running", dish_id)
                return

            state, warning = confirm_dish(self.state, dish_id, at)
            if warning:
                LOGGER.warning(
                    "confirm_dish(%s): not ready to add, or unknown", dish_id
                )
                return

            state, effects = advance(state, at)
            await self._process(state, effects)

    async def async_cancel_session(self) -> None:
        """Cancel the running session. A no-op if none is running."""
        async with self._lock:
            if self.state is None:
                LOGGER.warning("cancel_session: no session running")
                return

            state, effects = cancel_session(self.state)
            await self._process(state, effects)

    async def _on_timer(self, fire_time: datetime) -> None:
        """Handle an armed timer firing: re-evaluate and process due effects."""
        async with self._lock:
            if self.state is None:
                return
            state, effects = advance(self.state, fire_time.timestamp())
            await self._process(state, effects)

    async def _process(self, state: SessionState, effects: Sequence[Effect]) -> None:
        """
        Persist, fire effects, notify entities, then re-arm the next timer.

        A completed session's history entry is written *before* the live
        session store is cleared — not after — so a crash between the two
        never loses the session: the history entry is the only durable
        record once the live copy is gone, so it must exist first (design
        §10's "after completion but mid-history-write?" review prompt).
        """
        history_id = await self._persist_completed_history(effects)

        if state.status is SessionStatus.RUNNING:
            await self._session_store.async_save(session_to_dict(state))
            self.state = state
        else:
            await self._session_store.async_clear()
            self.state = None

        self._fire_bus_events(state, effects, history_id)
        async_dispatcher_send(self.hass, SIGNAL_SESSION_UPDATED)

        self._rearm(self.state)

    async def _persist_completed_history(self, effects: Sequence[Effect]) -> str | None:
        """Write the completed-session history entry, if this batch has one."""
        completed = next(
            (e for e in effects if isinstance(e, SessionCompletedEffect)), None
        )
        if completed is None:
            return None
        return await self._history_store.async_add_entry(
            completed_at=completed.completed_at,
            dishes=[asdict(dish) for dish in completed.dishes],
        )

    def _fire_bus_events(
        self, state: SessionState, effects: Sequence[Effect], history_id: str | None
    ) -> None:
        """Translate declarative engine effects into HA bus events."""
        language = self.hass.config.language
        for effect in effects:
            if isinstance(effect, AddAlertEffect):
                dish = _find_dish(state, effect.dish_id)
                self.hass.bus.async_fire(
                    EVENT_ADD_DISH,
                    {
                        "session_id": state.session_id,
                        "dish_id": dish.id,
                        "dish_name": resolve_dish_name(
                            dish.name_en, dish.name_nl, language
                        ),
                        "temperature": dish.temperature,
                        "steam_minutes": dish.steam_minutes,
                    },
                )
            elif isinstance(effect, DoneAlertEffect):
                dish = _find_dish(state, effect.dish_id)
                self.hass.bus.async_fire(
                    EVENT_DISH_DONE,
                    {
                        "session_id": state.session_id,
                        "dish_id": dish.id,
                        "dish_name": resolve_dish_name(
                            dish.name_en, dish.name_nl, language
                        ),
                    },
                )
            elif isinstance(effect, SessionCompletedEffect):
                self.hass.bus.async_fire(
                    EVENT_SESSION_COMPLETED,
                    {"session_id": state.session_id, "history_id": history_id},
                )
            elif isinstance(effect, SessionCancelledEffect):
                self.hass.bus.async_fire(
                    EVENT_SESSION_CANCELLED,
                    {
                        "session_id": state.session_id,
                        "dish_ids": list(effect.ready_to_add_dish_ids),
                    },
                )

    def _rearm(self, state: SessionState | None) -> None:
        """Cancel any armed timer and arm one for the next due target, if any."""
        self._cancel_timer()
        if state is None:
            return

        target = _next_target(state)
        if target is None:
            return

        self._unsub_timer = async_track_point_in_utc_time(
            self.hass, self._on_timer, datetime.fromtimestamp(target, tz=UTC)
        )

    def _cancel_timer(self) -> None:
        if self._unsub_timer is not None:
            self._unsub_timer()
            self._unsub_timer = None


def _find_dish(state: SessionState, dish_id: str) -> Dish:
    return next(d for d in state.dishes if d.id == dish_id)
