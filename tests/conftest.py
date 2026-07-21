"""Shared fixtures for HA-integration-level tests (not tests/engine/)."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.steamtime.const import DOMAIN

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

    from homeassistant.core import HomeAssistant


@pytest.fixture
async def entry(
    hass: HomeAssistant,
    enable_custom_integrations: None,  # noqa: ARG001 - dependency, must run first
) -> AsyncGenerator[MockConfigEntry]:
    """Set up a SteamTime config entry; unload (cancelling timers) afterward.

    Depends on `enable_custom_integrations` directly (rather than via a
    module-level `pytestmark`) so the ordering is guaranteed regardless of
    whether a test requests `entry` as a parameter or via
    `@pytest.mark.usefixtures("entry")` — mixing a module-level usefixtures
    mark with a function-level one for a fixture that itself needs another
    fixture first is an ordering race, not a guarantee.
    """
    config_entry = MockConfigEntry(domain=DOMAIN)
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    yield config_entry
    await hass.config_entries.async_unload(config_entry.entry_id)
    await hass.async_block_till_done()
