"""Validate the notify blueprint's structure against real HA (design §7).

This proves the blueprint is well-formed automation YAML — correct trigger/
condition/action schema, every `!input` reference has a matching input
definition — using HA's own blueprint + automation config validation
machinery.

`test_blueprint_actually_runs_without_errors` goes further: it sets up a
real automation from the blueprint, registers a mock notify service, fires
the actual bus events with realistic payloads, and checks the automation
runs clean. Static schema validation alone missed three real bugs during
manual testing (an undefined template variable, a notify service schema
mismatch, and a shadowed loop variable in the nested repeat) because none
of them surface until the templates are actually rendered and the actions
actually execute — this test exists specifically to catch that class of
bug automatically.

Neither test proves the actionable-notification round trip works on a
phone; design §11 flags that as needing manual end-to-end testing with a
real companion app, which no automated test can substitute for.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import TYPE_CHECKING, Any

from homeassistant.components.automation.config import (
    ValidationStatus,
    async_validate_config_item,
)
from homeassistant.setup import async_setup_component

if TYPE_CHECKING:
    import pytest
    from homeassistant.core import HomeAssistant, ServiceCall

_REPO_ROOT = Path(__file__).resolve().parent.parent
_BLUEPRINT_SOURCE = (
    _REPO_ROOT / "blueprints" / "automation" / "steamtime" / "steamtime_notify.yaml"
)
_NOTIFY_SERVICE = "mobile_app_test_phone"


async def _install_blueprint(hass: HomeAssistant) -> None:
    dest_dir = Path(hass.config.path("blueprints", "automation", "steamtime"))

    def _copy() -> None:
        dest_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy(_BLUEPRINT_SOURCE, dest_dir / "steamtime_notify.yaml")

    await hass.async_add_executor_job(_copy)


async def _validate(hass: HomeAssistant, blueprint_input: dict[str, Any]) -> None:
    config = {
        "use_blueprint": {
            "path": "steamtime/steamtime_notify.yaml",
            "input": blueprint_input,
        }
    }
    automation_config = await async_validate_config_item(hass, "steamtime_test", config)
    assert automation_config is not None
    assert automation_config.validation_status is ValidationStatus.OK


async def test_notify_blueprint_with_all_inputs_set(hass: HomeAssistant) -> None:
    await _install_blueprint(hass)
    await _validate(
        hass,
        {
            "notify_targets": ["notify.mobile_app_my_phone"],
            "critical_add_alerts": True,
            "chime_media_player": "media_player.kitchen",
            "chime_sound_url": "media-source://media_source/local/chime.mp3",
        },
    )


async def test_notify_blueprint_with_only_required_input_set(
    hass: HomeAssistant,
) -> None:
    """The common real-world case: optional fields left blank in the UI.

    A previous version of this blueprint substituted the chime_media_player
    default ("") directly into a `target: entity_id: ...`, which HA's schema
    rejects even when that whole step is never reached at runtime — config
    validation resolves the blueprint's literal defaults and checks the
    resulting static shape regardless of any `if` condition. Caught in
    production by a user leaving the optional chime fields blank; this test
    reproduces that exact input shape so it can't regress silently.
    """
    await _install_blueprint(hass)
    await _validate(hass, {"notify_targets": ["notify.mobile_app_my_phone"]})


async def test_blueprint_actually_runs_without_errors(
    hass: HomeAssistant, caplog: pytest.LogCaptureFixture
) -> None:
    await _install_blueprint(hass)

    calls: list[ServiceCall] = []

    async def _mock_notify(call: ServiceCall) -> None:
        calls.append(call)

    hass.services.async_register("notify", _NOTIFY_SERVICE, _mock_notify)

    assert await async_setup_component(
        hass,
        "automation",
        {
            "automation": [
                {
                    "use_blueprint": {
                        "path": "steamtime/steamtime_notify.yaml",
                        "input": {
                            "notify_targets": [f"notify.{_NOTIFY_SERVICE}"],
                            "critical_add_alerts": True,
                        },
                    }
                }
            ]
        },
    )
    await hass.async_block_till_done()

    hass.bus.async_fire(
        "steamtime_add_dish",
        {
            "session_id": "s1",
            "dish_id": "d1",
            "dish_name": "Fish",
            "temperature": 90,
            "steam_minutes": 10,
        },
    )
    await hass.async_block_till_done()

    hass.bus.async_fire(
        "steamtime_dish_done",
        {"session_id": "s1", "dish_id": "d1", "dish_name": "Fish"},
    )
    await hass.async_block_till_done()

    hass.bus.async_fire(
        "steamtime_session_completed", {"session_id": "s1", "history_id": "h1"}
    )
    await hass.async_block_till_done()

    hass.bus.async_fire(
        "steamtime_session_cancelled", {"session_id": "s1", "dish_ids": ["d2", "d3"]}
    )
    await hass.async_block_till_done()

    assert "Error" not in caplog.text

    # add_dish, dish_done, session_completed (1 each) + session_cancelled
    # (2 clear_notification calls + 1 "Session cancelled" summary) = 6.
    assert len(calls) == 6

    add_call = calls[0].data
    assert add_call["title"] == "Add to the oven"
    assert add_call["message"] == "Add Fish to the oven — 90 °C"
    assert add_call["data"]["tag"] == "steamtime_d1"
    assert add_call["data"]["actions"][0]["action"] == "steamtime_confirm_d1"
    assert add_call["data"]["push"]["interruption-level"] == "critical"

    done_call = calls[1].data
    assert done_call["message"] == "Fish is done"
    assert done_call["data"]["tag"] == "steamtime_d1"
    assert done_call["data"]["priority"] == "high"
    assert done_call["data"]["push"]["interruption-level"] == "time-sensitive"

    completed_call = calls[2].data
    assert "complete" in completed_call["message"].lower()
    assert completed_call["data"]["priority"] == "high"
    assert completed_call["data"]["push"]["interruption-level"] == "time-sensitive"

    clear_calls = [c.data for c in calls[3:5]]
    cleared_tags = {c["data"]["tag"] for c in clear_calls}
    assert cleared_tags == {"steamtime_d2", "steamtime_d3"}
    assert all(c["message"] == "clear_notification" for c in clear_calls)

    cancelled_call = calls[5].data
    assert "cancelled" in cancelled_call["message"].lower()
