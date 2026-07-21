"""Tests for the options flow: reconfigure notify prefs after setup (design §8)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.config_entries import ConfigEntryState
from homeassistant.data_entry_flow import FlowResultType

from custom_components.steamtime.const import (
    CONF_CRITICAL_ADD_ALERTS,
    CONF_NOTIFY_TARGETS,
)

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from pytest_homeassistant_custom_component.common import MockConfigEntry


async def test_options_flow_updates_notify_prefs_and_reloads(
    hass: HomeAssistant, entry: MockConfigEntry
) -> None:
    async def _handler(_call: object) -> None:
        return

    hass.services.async_register("notify", "mobile_app_test_phone", _handler)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "init"

    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={
            CONF_NOTIFY_TARGETS: ["notify.mobile_app_test_phone"],
            CONF_CRITICAL_ADD_ALERTS: True,
        },
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options == {
        CONF_NOTIFY_TARGETS: ["notify.mobile_app_test_phone"],
        CONF_CRITICAL_ADD_ALERTS: True,
    }
    # The update listener reloaded the entry so the new options take effect.
    loaded_state = entry.state
    assert loaded_state is ConfigEntryState.LOADED
    assert entry.runtime_data.notification_dispatcher is not None
