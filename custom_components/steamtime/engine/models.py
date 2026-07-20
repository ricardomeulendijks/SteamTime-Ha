"""
Pure-data models for the SteamTime sequencing engine.

No `homeassistant.*` imports, no I/O, no clocks — every timestamp here is a
caller-supplied epoch UTC second (float). See docs/design.md §3.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class DishStatus(StrEnum):
    """Per-dish lifecycle state (design §3.2)."""

    PENDING = "pending"
    READY_TO_ADD = "ready_to_add"
    COOKING = "cooking"
    DONE = "done"


class SessionStatus(StrEnum):
    """Whole-session lifecycle state."""

    RUNNING = "running"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


@dataclass(frozen=True, slots=True)
class DishSpec:
    """One dish as requested by `start_session`, before sequencing."""

    name_en: str
    steam_minutes: int
    temperature: int
    category: str
    name_nl: str | None = None


@dataclass(slots=True)
class Dish:
    """One dish instance within a live session."""

    id: str
    name_en: str
    steam_minutes: int
    temperature: int
    category: str
    planned_add_at: float
    name_nl: str | None = None
    status: DishStatus = DishStatus.PENDING
    confirmed_at: float | None = None
    done_at: float | None = None


@dataclass(slots=True)
class SessionState:
    """The full live-session state — the engine's only durable payload."""

    session_id: str
    started_at: float
    dishes: list[Dish] = field(default_factory=list)
    status: SessionStatus = SessionStatus.RUNNING


@dataclass(frozen=True, slots=True)
class DishSnapshot:
    """A frozen per-dish record inside a completed-session history entry."""

    id: str
    name_en: str
    steam_minutes: int
    temperature: int
    category: str
    confirmed_at: float | None
    done_at: float | None
    name_nl: str | None = None


@dataclass(frozen=True, slots=True)
class AddAlertEffect:
    """A dish entered `ready_to_add`; the runtime should fire its add event."""

    dish_id: str


@dataclass(frozen=True, slots=True)
class DoneAlertEffect:
    """A dish entered `done`; the runtime should fire its done event."""

    dish_id: str


@dataclass(frozen=True, slots=True)
class SessionCompletedEffect:
    """Every dish is `done`; the runtime should write history and clear state."""

    completed_at: float
    dishes: tuple[DishSnapshot, ...]


@dataclass(frozen=True, slots=True)
class SessionCancelledEffect:
    """The session was cancelled; the runtime should clear state, write nothing."""


Effect = (
    AddAlertEffect | DoneAlertEffect | SessionCompletedEffect | SessionCancelledEffect
)
