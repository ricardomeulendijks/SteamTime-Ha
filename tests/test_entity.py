"""Tests for the shared base entity's device info (design §2, §4)."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceEntryType

from custom_components.steamtime.const import DOMAIN
from custom_components.steamtime.entity import SteamTimeEntity


def test_device_info_ties_entity_to_the_single_steamtime_device() -> None:
    entity = SteamTimeEntity("entry123")

    assert entity.device_info == {
        "identifiers": {(DOMAIN, "entry123")},
        "name": "SteamTime",
        "entry_type": DeviceEntryType.SERVICE,
    }
