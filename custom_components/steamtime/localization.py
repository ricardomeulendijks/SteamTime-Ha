"""Dish display-name resolution (design §8)."""

from __future__ import annotations


def resolve_dish_name(name_en: str, name_nl: str | None, language: str) -> str:
    """Return `name_nl` when `language` is Dutch and present, else `name_en`."""
    if language == "nl" and name_nl:
        return name_nl
    return name_en
