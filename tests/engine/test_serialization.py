"""Round-trip tests for dict serialization (design §3, §5)."""

from __future__ import annotations

from custom_components.steamtime.engine import (
    SessionStatus,
    advance,
    build_session,
    confirm_dish,
    session_from_dict,
    session_to_dict,
)

from .conftest import T0, dish


def test_round_trip_preserves_full_state() -> None:
    state = build_session(
        "s1",
        [dish("Potatoes", 20, temperature=100), dish("Peas", 10, temperature=95)],
        now=T0,
    )
    state, _ = advance(state, T0)
    state, _ = confirm_dish(state, "d1", T0 + 5)

    data = session_to_dict(state)
    restored = session_from_dict(data)

    assert restored == state
    assert session_to_dict(restored) == data


def test_round_trip_is_plain_json_safe_types() -> None:
    state = build_session("s1", [dish("Potatoes", 20)], now=T0)
    data = session_to_dict(state)

    def assert_plain(value: object) -> None:
        if isinstance(value, dict):
            for v in value.values():
                assert_plain(v)
        elif isinstance(value, list):
            for v in value:
                assert_plain(v)
        else:
            assert value is None or isinstance(value, (str, int, float))

    assert_plain(data)
    assert data["status"] == SessionStatus.RUNNING.value
