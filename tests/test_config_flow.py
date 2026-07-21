"""Tests for the config flow: confirm, then notify preferers (design §8)."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from homeassistant.config_entries import SOURCE_USER
from homeassistant.data_entry_flow import FlowResultType

from custom_components.steamtime.const import (
    CONF_CRITICAL_ADD_ALERTS,
    CONF_NOTIFY_TARGETS,
    DOMAIN,
)

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

pytestmark = pytest.mark.usefixtures("enable_custom_integrations")


async def _register_fake_notify_service(hass: HomeAssistant) -> None:
    async def _handler(_call: object) -> None:
        return

    hass.services.async_register("notify", "mobile_app_test_phone", _handler)


async def test_full_flow_with_notify_target_and_critical_alerts(
    hass: HomeAssistant,
) -> None:
    await _register_fake_notify_service(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input={}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "notify"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={
            CONF_NOTIFY_TARGETS: ["notify.mobile_app_test_phone"],
            CONF_CRITICAL_ADD_ALERTS: True,
        },
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "SteamTime"
    assert result["data"] == {}
    assert result["options"] == {
        CONF_NOTIFY_TARGETS: ["notify.mobile_app_test_phone"],
        CONF_CRITICAL_ADD_ALERTS: True,
    }


async def test_notify_step_can_be_skipped(hass: HomeAssistant) -> None:
    """Leaving notify targets empty is valid (design §8)."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input={}
    )

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input={}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["options"] == {
        CONF_NOTIFY_TARGETS: [],
        CONF_CRITICAL_ADD_ALERTS: False,
    }


async def test_second_flow_aborts_single_instance(hass: HomeAssistant) -> None:
    first = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    first = await hass.config_entries.flow.async_configure(
        first["flow_id"], user_input={}
    )
    await hass.config_entries.flow.async_configure(first["flow_id"], user_input={})

    second = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert second["type"] is FlowResultType.ABORT
    assert second["reason"] == "single_instance_allowed"
