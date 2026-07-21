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
from typing import TYPE_CHECKING

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


async def test_notify_blueprint_resolves_to_a_valid_automation(
    hass: HomeAssistant,
) -> None:
    dest_dir = Path(hass.config.path("blueprints", "automation", "steamtime"))

    def _install_blueprint() -> None:
        dest_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy(_BLUEPRINT_SOURCE, dest_dir / "steamtime_notify.yaml")

    await hass.async_add_executor_job(_install_blueprint)

    config = {
        "use_blueprint": {
            "path": "steamtime/steamtime_notify.yaml",
            "input": {
                "notify_targets": "notify.my_phone",
                "critical_add_alerts": True,
                "chime_media_player": "media_player.kitchen",
                "chime_sound_url": "media-source://media_source/local/chime.mp3",
            },
        }
    }

    automation_config = await async_validate_config_item(hass, "steamtime_test", config)

    assert automation_config is not None
    assert automation_config.validation_status is ValidationStatus.OK
