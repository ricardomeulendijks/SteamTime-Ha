"""Validate the notify blueprint's structure against real HA (design §7).

This proves the blueprint is well-formed automation YAML — correct trigger/
condition/action schema, every `!input` reference has a matching input
definition — using HA's own blueprint + automation config validation
machinery. It does **not** prove the actionable-notification round trip
actually works on a phone; design §11 flags that as needing manual
end-to-end testing with a real companion app, which no automated test here
can substitute for.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import TYPE_CHECKING, Any

from homeassistant.components.automation.config import (
    ValidationStatus,
    async_validate_config_item,
)

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

_REPO_ROOT = Path(__file__).resolve().parent.parent
_BLUEPRINT_SOURCE = (
    _REPO_ROOT / "blueprints" / "automation" / "steamtime" / "steamtime_notify.yaml"
)


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
            "notify_targets": "notify.my_phone",
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
    await _validate(hass, {"notify_targets": "notify.my_phone"})
