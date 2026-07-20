"""
SteamTime sequencing engine — pure Python, no I/O, no `homeassistant.*` imports.

A timestamp-in, state-out state machine (design §3). Everything HA-specific
(storage, timers, events, entities) lives outside this package.
"""

from __future__ import annotations

from .models import (
    AddAlertEffect,
    Dish,
    DishSnapshot,
    DishSpec,
    DishStatus,
    DoneAlertEffect,
    Effect,
    SessionCancelledEffect,
    SessionCompletedEffect,
    SessionState,
    SessionStatus,
)
from .sequencing import build_session
from .serialization import session_from_dict, session_to_dict
from .state_machine import advance, cancel_session, confirm_dish

__all__ = [
    "AddAlertEffect",
    "Dish",
    "DishSnapshot",
    "DishSpec",
    "DishStatus",
    "DoneAlertEffect",
    "Effect",
    "SessionCancelledEffect",
    "SessionCompletedEffect",
    "SessionState",
    "SessionStatus",
    "advance",
    "build_session",
    "cancel_session",
    "confirm_dish",
    "session_from_dict",
    "session_to_dict",
]
