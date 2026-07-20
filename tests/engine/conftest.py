"""Shared fixtures for engine tests."""

from __future__ import annotations

import pytest

from custom_components.steamtime.engine import DishSpec

T0 = 1_700_000_000.0


def dish(
    name_en: str,
    minutes: int,
    temperature: int = 100,
    category: str = "vegetables",
) -> DishSpec:
    """Build a `DishSpec` with sensible defaults for tests."""
    return DishSpec(
        name_en=name_en,
        steam_minutes=minutes,
        temperature=temperature,
        category=category,
    )


@pytest.fixture
def now() -> float:
    """A fixed synthetic session-start timestamp."""
    return T0
