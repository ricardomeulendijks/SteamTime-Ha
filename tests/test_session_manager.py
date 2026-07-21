"""Tests for SessionManager (design §2, §3.4, §5.2)."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import pytest
from pytest_homeassistant_custom_component.common import (
    async_capture_events,
    async_fire_time_changed,
    async_mock_signal,
)

from custom_components.steamtime.const import (
    EVENT_ADD_DISH,
    EVENT_DISH_DONE,
    EVENT_SESSION_CANCELLED,
    EVENT_SESSION_COMPLETED,
    SIGNAL_SESSION_UPDATED,
)
from custom_components.steamtime.engine import DishSpec, DishStatus
from custom_components.steamtime.session_manager import (
    SessionAlreadyRunningError,
    SessionManager,
)
from custom_components.steamtime.storage import HistoryStore, SessionStore

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant


def _fish(minutes: int = 1) -> DishSpec:
    return DishSpec(
        name_en="Fish",
        name_nl="Vis",
        steam_minutes=minutes,
        temperature=90,
        category="fish",
    )


def _peas(minutes: int = 1) -> DishSpec:
    return DishSpec(
        name_en="Peas",
        name_nl="Erwten",
        steam_minutes=minutes,
        temperature=100,
        category="vegetables",
    )


async def _make_manager(hass: HomeAssistant) -> SessionManager:
    history = HistoryStore(hass)
    await history.async_load()
    return SessionManager(hass, SessionStore(hass), history)


async def test_start_session_fires_add_event_for_first_dish_and_persists(
    hass: HomeAssistant, hass_storage: dict[str, Any]
) -> None:
    manager = await _make_manager(hass)
    add_events = async_capture_events(hass, EVENT_ADD_DISH)
    signals = async_mock_signal(hass, SIGNAL_SESSION_UPDATED)

    await manager.async_start_session([_fish(20), _peas(10)])

    assert manager.state is not None
    assert manager.state.dishes[0].status is DishStatus.READY_TO_ADD
    assert manager.state.dishes[1].status is DishStatus.PENDING
    assert len(add_events) == 1
    assert add_events[0].data["dish_name"] == "Fish"
    assert add_events[0].data["temperature"] == 90
    assert add_events[0].data["steam_minutes"] == 20
    assert len(signals) == 1
    assert "steamtime.session" in hass_storage

    await manager.async_unload()  # d2 is still pending; cancel its armed timer


async def test_start_session_raises_if_already_running(hass: HomeAssistant) -> None:
    manager = await _make_manager(hass)
    await manager.async_start_session([_fish()])

    with pytest.raises(SessionAlreadyRunningError):
        await manager.async_start_session([_fish()])


async def test_concurrent_start_session_calls_are_serialized(
    hass: HomeAssistant,
) -> None:
    """Design §10: are transitions serialized against a second service call?

    Two concurrent start_session calls must not both see "no session
    running" — exactly one may succeed, the other must raise, never two
    sessions silently racing each other into self.state.
    """
    manager = await _make_manager(hass)

    results = await asyncio.gather(
        manager.async_start_session([_fish()]),
        manager.async_start_session([_peas()]),
        return_exceptions=True,
    )

    successes = [r for r in results if r is None]
    failures = [r for r in results if isinstance(r, SessionAlreadyRunningError)]
    assert len(successes) == 1
    assert len(failures) == 1
    assert manager.state is not None


async def test_confirm_dish_warns_on_non_ready_or_unknown(
    hass: HomeAssistant, caplog: pytest.LogCaptureFixture
) -> None:
    manager = await _make_manager(hass)
    await manager.async_start_session([_fish(20), _peas(10)])

    await manager.async_confirm_dish("d2", 0.0)  # still pending, not ready_to_add
    assert manager.state is not None
    assert manager.state.dishes[1].status is DishStatus.PENDING
    assert "not ready to add" in caplog.text

    await manager.async_confirm_dish("unknown", 0.0)
    assert "not ready to add" in caplog.text

    await manager.async_unload()  # d2 is still pending; cancel its armed timer


async def test_confirm_dish_with_no_session_running_warns(
    hass: HomeAssistant, caplog: pytest.LogCaptureFixture
) -> None:
    manager = await _make_manager(hass)
    await manager.async_confirm_dish("d1", 0.0)
    assert "no session running" in caplog.text


async def test_cancel_session_fires_cancelled_event_and_clears_state(
    hass: HomeAssistant, hass_storage: dict[str, Any]
) -> None:
    manager = await _make_manager(hass)
    # Equal steam times: both dishes become ready_to_add together, neither
    # confirmed, so both have an outstanding add-notification to clear.
    await manager.async_start_session([_fish(10), _peas(10)])
    cancelled_events = async_capture_events(hass, EVENT_SESSION_CANCELLED)
    assert manager.state is not None
    dish_ids = {d.id for d in manager.state.dishes}

    await manager.async_cancel_session()

    assert manager.state is None
    assert len(cancelled_events) == 1
    assert set(cancelled_events[0].data["dish_ids"]) == dish_ids
    assert "steamtime.session" not in hass_storage
    assert "steamtime.history" not in hass_storage  # cancellation writes no history


async def test_cancel_session_with_no_session_running_warns(
    hass: HomeAssistant, caplog: pytest.LogCaptureFixture
) -> None:
    manager = await _make_manager(hass)
    await manager.async_cancel_session()
    assert "no session running" in caplog.text


async def test_full_lifecycle_via_timer_confirm_then_done_then_completed(
    hass: HomeAssistant, hass_storage: dict[str, Any]
) -> None:
    manager = await _make_manager(hass)
    add_events = async_capture_events(hass, EVENT_ADD_DISH)
    done_events = async_capture_events(hass, EVENT_DISH_DONE)
    completed_events = async_capture_events(hass, EVENT_SESSION_COMPLETED)

    await manager.async_start_session([_fish(1)])
    assert manager.state is not None
    dish_id = add_events[0].data["dish_id"]

    confirmed_at = manager.state.dishes[0].planned_add_at
    await manager.async_confirm_dish(dish_id, confirmed_at)
    assert manager.state is not None
    assert manager.state.dishes[0].status is DishStatus.COOKING

    done_at = manager.state.dishes[0].done_at
    assert done_at is not None

    # Fire the armed timer a moment past doneAt, as if real time had passed.
    async_fire_time_changed(hass, datetime.fromtimestamp(done_at + 1, tz=UTC))
    await hass.async_block_till_done()

    assert manager.state is None
    assert len(done_events) == 1
    assert len(completed_events) == 1
    history_id = completed_events[0].data["history_id"]
    assert history_id is not None
    assert "steamtime.session" not in hass_storage
    assert hass_storage["steamtime.history"]["data"][0]["id"] == history_id


async def test_completion_writes_history_before_clearing_the_live_session(
    hass: HomeAssistant, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A crash between the two must never lose a completed session (design §10).

    The history entry is the only durable record once the live session is
    gone, so it must be written first — verified here by call-order, not
    just by both eventually happening.
    """
    manager = await _make_manager(hass)
    call_order: list[str] = []

    original_add_entry = HistoryStore.async_add_entry
    original_clear = SessionStore.async_clear

    async def spy_add_entry(self: HistoryStore, **kwargs: object) -> str:
        call_order.append("history_add_entry")
        return await original_add_entry(self, **kwargs)  # type: ignore[arg-type]

    async def spy_clear(self: SessionStore) -> None:
        call_order.append("session_clear")
        await original_clear(self)

    monkeypatch.setattr(HistoryStore, "async_add_entry", spy_add_entry)
    monkeypatch.setattr(SessionStore, "async_clear", spy_clear)

    await manager.async_start_session([_fish(1)])
    assert manager.state is not None
    dish_id = manager.state.dishes[0].id
    confirmed_at = manager.state.dishes[0].planned_add_at
    await manager.async_confirm_dish(dish_id, confirmed_at)
    done_at = manager.state.dishes[0].done_at
    assert done_at is not None

    async_fire_time_changed(hass, datetime.fromtimestamp(done_at + 1, tz=UTC))
    await hass.async_block_till_done()

    assert call_order == ["history_add_entry", "session_clear"]
