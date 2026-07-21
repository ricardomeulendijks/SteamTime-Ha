"""Tests for the built-in notification dispatcher (design §7)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.steamtime.const import (
    CONF_CRITICAL_ADD_ALERTS,
    CONF_NOTIFY_TARGETS,
    DOMAIN,
    EVENT_ADD_DISH,
    EVENT_DISH_DONE,
    EVENT_SESSION_CANCELLED,
    EVENT_SESSION_COMPLETED,
)
from custom_components.steamtime.notifications import NotificationDispatcher

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant, ServiceCall


async def _register_recorder(hass: HomeAssistant, service: str) -> list[ServiceCall]:
    calls: list[ServiceCall] = []

    async def _handler(call: ServiceCall) -> None:
        calls.append(call)

    hass.services.async_register("notify", service, _handler)
    return calls


def _entry(hass: HomeAssistant, **options: Any) -> MockConfigEntry:
    entry = MockConfigEntry(domain=DOMAIN, options=options)
    entry.add_to_hass(hass)
    return entry


async def test_no_listeners_registered_when_no_targets_configured(
    hass: HomeAssistant,
) -> None:
    dispatcher = NotificationDispatcher(hass, _entry(hass))
    dispatcher.async_setup()

    hass.bus.async_fire(
        EVENT_ADD_DISH,
        {
            "session_id": "s1",
            "dish_id": "d1",
            "dish_name": "Fish",
            "temperature": 90,
            "steam_minutes": 10,
        },
    )
    await hass.async_block_till_done()

    # No error, and nothing to assert on since there are no targets — the
    # real assertion is that async_unload (called next) has nothing to undo.
    dispatcher.async_unload()


async def test_add_dish_sends_actionable_notification(hass: HomeAssistant) -> None:
    calls = await _register_recorder(hass, "test_phone")
    entry = _entry(hass, **{CONF_NOTIFY_TARGETS: ["notify.test_phone"]})
    dispatcher = NotificationDispatcher(hass, entry)
    dispatcher.async_setup()

    hass.bus.async_fire(
        EVENT_ADD_DISH,
        {
            "session_id": "s1",
            "dish_id": "d1",
            "dish_name": "Fish",
            "temperature": 90,
            "steam_minutes": 10,
        },
    )
    await hass.async_block_till_done()

    assert len(calls) == 1
    data = calls[0].data
    assert data["title"] == "Add to the oven"
    assert data["message"] == "Add Fish to the oven — 90 °C"
    assert data["data"]["tag"] == "steamtime_d1"
    assert data["data"]["actions"][0]["action"] == "steamtime_confirm_d1"
    assert data["data"]["push"]["interruption-level"] == "active"
    assert data["data"]["priority"] == "normal"

    dispatcher.async_unload()


async def test_critical_add_alerts_toggle(hass: HomeAssistant) -> None:
    calls = await _register_recorder(hass, "test_phone")
    entry = _entry(
        hass,
        **{
            CONF_NOTIFY_TARGETS: ["notify.test_phone"],
            CONF_CRITICAL_ADD_ALERTS: True,
        },
    )
    dispatcher = NotificationDispatcher(hass, entry)
    dispatcher.async_setup()

    hass.bus.async_fire(
        EVENT_ADD_DISH,
        {
            "session_id": "s1",
            "dish_id": "d1",
            "dish_name": "Fish",
            "temperature": 90,
            "steam_minutes": 10,
        },
    )
    await hass.async_block_till_done()

    data = calls[0].data["data"]
    assert data["push"]["interruption-level"] == "critical"
    assert data["push"]["sound"]["critical"] == 1
    assert data["priority"] == "high"
    assert data["ttl"] == 0
    assert data["channel"] == "alarm_stream"

    dispatcher.async_unload()


async def test_dish_done_and_session_completed(hass: HomeAssistant) -> None:
    calls = await _register_recorder(hass, "test_phone")
    entry = _entry(hass, **{CONF_NOTIFY_TARGETS: ["notify.test_phone"]})
    dispatcher = NotificationDispatcher(hass, entry)
    dispatcher.async_setup()

    hass.bus.async_fire(
        EVENT_DISH_DONE, {"session_id": "s1", "dish_id": "d1", "dish_name": "Fish"}
    )
    await hass.async_block_till_done()
    hass.bus.async_fire(
        EVENT_SESSION_COMPLETED, {"session_id": "s1", "history_id": "h1"}
    )
    await hass.async_block_till_done()

    assert len(calls) == 2
    assert calls[0].data["message"] == "Fish is done"
    assert calls[0].data["data"]["tag"] == "steamtime_d1"
    assert "complete" in calls[1].data["message"].lower()

    dispatcher.async_unload()


async def test_session_cancelled_clears_tags_then_sends_summary(
    hass: HomeAssistant,
) -> None:
    calls = await _register_recorder(hass, "test_phone")
    entry = _entry(hass, **{CONF_NOTIFY_TARGETS: ["notify.test_phone"]})
    dispatcher = NotificationDispatcher(hass, entry)
    dispatcher.async_setup()

    hass.bus.async_fire(
        EVENT_SESSION_CANCELLED, {"session_id": "s1", "dish_ids": ["d1", "d2"]}
    )
    await hass.async_block_till_done()

    assert len(calls) == 3
    assert calls[0].data == {
        "message": "clear_notification",
        "data": {"tag": "steamtime_d1"},
    }
    assert calls[1].data == {
        "message": "clear_notification",
        "data": {"tag": "steamtime_d2"},
    }
    assert "cancelled" in calls[2].data["message"].lower()

    dispatcher.async_unload()


async def test_confirm_action_calls_confirm_dish_service(hass: HomeAssistant) -> None:
    confirm_calls: list[ServiceCall] = []

    async def _confirm_handler(call: ServiceCall) -> None:
        confirm_calls.append(call)

    hass.services.async_register(DOMAIN, "confirm_dish", _confirm_handler)
    entry = _entry(hass, **{CONF_NOTIFY_TARGETS: ["notify.test_phone"]})
    dispatcher = NotificationDispatcher(hass, entry)
    dispatcher.async_setup()

    hass.bus.async_fire(
        "mobile_app_notification_action", {"action": "steamtime_confirm_d1"}
    )
    await hass.async_block_till_done()

    assert len(confirm_calls) == 1
    assert confirm_calls[0].data["dish_id"] == "d1"

    dispatcher.async_unload()


async def test_confirm_action_ignores_unrelated_actions(hass: HomeAssistant) -> None:
    confirm_calls: list[ServiceCall] = []

    async def _confirm_handler(call: ServiceCall) -> None:
        confirm_calls.append(call)

    hass.services.async_register(DOMAIN, "confirm_dish", _confirm_handler)
    entry = _entry(hass, **{CONF_NOTIFY_TARGETS: ["notify.test_phone"]})
    dispatcher = NotificationDispatcher(hass, entry)
    dispatcher.async_setup()

    hass.bus.async_fire(
        "mobile_app_notification_action", {"action": "some_other_action"}
    )
    await hass.async_block_till_done()

    assert confirm_calls == []

    dispatcher.async_unload()


async def test_unload_stops_further_notifications(hass: HomeAssistant) -> None:
    calls = await _register_recorder(hass, "test_phone")
    entry = _entry(hass, **{CONF_NOTIFY_TARGETS: ["notify.test_phone"]})
    dispatcher = NotificationDispatcher(hass, entry)
    dispatcher.async_setup()
    dispatcher.async_unload()

    hass.bus.async_fire(
        EVENT_SESSION_COMPLETED, {"session_id": "s1", "history_id": "h1"}
    )
    await hass.async_block_till_done()

    assert calls == []
