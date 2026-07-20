"""Restart-recovery integration test (design §5.2, §9 step 4).

The critical path: start a session, confirm a dish, simulate HA being down
20 minutes past that dish's doneAt, then reload the config entry (the test
harness's equivalent of an `ha core restart`) and confirm the session
picked up exactly where it should — fast-forwarded, nothing lost.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_capture_events,
)

from custom_components.steamtime.const import (
    DOMAIN,
    EVENT_DISH_DONE,
    EVENT_SESSION_COMPLETED,
)
from custom_components.steamtime.engine import DishSpec, DishStatus

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

pytestmark = pytest.mark.usefixtures("enable_custom_integrations")


async def test_restart_recovery_fast_forwards_after_ha_downtime(
    hass: HomeAssistant,
    hass_storage: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = {"now": 1_700_000_000.0}
    monkeypatch.setattr(
        "custom_components.steamtime.session_manager._now", lambda: clock["now"]
    )

    entry = MockConfigEntry(domain=DOMAIN)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    manager = entry.runtime_data.session_manager
    await manager.async_start_session(
        [
            DishSpec(
                name_en="Fish",
                name_nl="Vis",
                steam_minutes=1,
                temperature=90,
                category="fish",
            )
        ]
    )
    assert manager.state is not None
    dish_id = manager.state.dishes[0].id

    await manager.async_confirm_dish(dish_id, clock["now"])
    assert manager.state.dishes[0].status is DishStatus.COOKING
    done_at = manager.state.dishes[0].done_at
    assert done_at is not None

    # HA was "down" for 20 minutes past the dish's doneAt.
    clock["now"] = done_at + 20 * 60

    done_events = async_capture_events(hass, EVENT_DISH_DONE)
    completed_events = async_capture_events(hass, EVENT_SESSION_COMPLETED)

    await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()

    restored_manager = entry.runtime_data.session_manager
    assert restored_manager is not manager  # a genuinely fresh instance
    assert restored_manager.state is None  # completed and cleared, nothing lost
    assert len(done_events) == 1
    assert done_events[0].data["dish_id"] == dish_id
    assert len(completed_events) == 1
    history_id = completed_events[0].data["history_id"]
    assert hass_storage["steamtime.history"]["data"][0]["id"] == history_id
    assert "steamtime.session" not in hass_storage
