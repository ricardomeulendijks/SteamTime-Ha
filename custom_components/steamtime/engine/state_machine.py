"""
The per-dish state machine, `advance`, and session commands (design §3.2-3.4).

Convention: `build_session`, `confirm_dish`, and `cancel_session` only apply
the transition their name describes — they never fire time-based effects
themselves. Callers (the runtime) must follow any of them with `advance(state,
now)` to pick up whatever is immediately due and to learn the next timer
target. This keeps exactly one code path responsible for time-based effects.
"""

from __future__ import annotations

from .models import (
    AddAlertEffect,
    Dish,
    DishSnapshot,
    DishStatus,
    DoneAlertEffect,
    Effect,
    SessionCancelledEffect,
    SessionCompletedEffect,
    SessionState,
    SessionStatus,
)


def advance(state: SessionState, now: float) -> tuple[SessionState, list[Effect]]:
    """
    Fire every transition whose target timestamp is <= `now`.

    Transitions are applied in chronological order of their target timestamp
    (ties broken by dish id). Idempotent: dishes that have already left the
    status a transition reads from are never reconsidered, so replaying the
    same `now` (or an earlier no-op call) changes nothing.
    """
    if state.status is not SessionStatus.RUNNING:
        return state, []

    due: list[tuple[float, str, Dish]] = []
    for dish in state.dishes:
        if dish.status is DishStatus.PENDING and dish.planned_add_at <= now:
            due.append((dish.planned_add_at, "ready", dish))
        elif (
            dish.status is DishStatus.COOKING
            and dish.done_at is not None
            and dish.done_at <= now
        ):
            due.append((dish.done_at, "done", dish))
    due.sort(key=lambda entry: (entry[0], entry[2].id))

    effects: list[Effect] = []
    for _, kind, dish in due:
        if kind == "ready":
            dish.status = DishStatus.READY_TO_ADD
            effects.append(AddAlertEffect(dish_id=dish.id))
        else:
            dish.status = DishStatus.DONE
            effects.append(DoneAlertEffect(dish_id=dish.id))

    if state.dishes and all(dish.status is DishStatus.DONE for dish in state.dishes):
        state.status = SessionStatus.COMPLETED
        completed_at = max(
            dish.done_at for dish in state.dishes if dish.done_at is not None
        )
        snapshot = tuple(
            DishSnapshot(
                id=dish.id,
                name_en=dish.name_en,
                name_nl=dish.name_nl,
                steam_minutes=dish.steam_minutes,
                temperature=dish.temperature,
                category=dish.category,
                confirmed_at=dish.confirmed_at,
                done_at=dish.done_at,
            )
            for dish in state.dishes
        )
        effects.append(
            SessionCompletedEffect(completed_at=completed_at, dishes=snapshot)
        )

    return state, effects


def confirm_dish(
    state: SessionState, dish_id: str, at: float
) -> tuple[SessionState, bool]:
    """
    Move `dish_id` from `ready_to_add` to `cooking`, timed from `at`.

    Returns `(state, warning)`. `warning` is True for a no-op: no session
    running, unknown dish id, or a dish not currently `ready_to_add` — a
    double-tapped confirmation must never raise.
    """
    if state.status is not SessionStatus.RUNNING:
        return state, True

    dish = next((d for d in state.dishes if d.id == dish_id), None)
    if dish is None or dish.status is not DishStatus.READY_TO_ADD:
        return state, True

    dish.status = DishStatus.COOKING
    dish.confirmed_at = at
    dish.done_at = at + dish.steam_minutes * 60
    return state, False


def cancel_session(state: SessionState) -> tuple[SessionState, list[Effect]]:
    """Cancel a running session. Writes nothing to history (design §3.3)."""
    if state.status is not SessionStatus.RUNNING:
        return state, []

    ready_to_add_dish_ids = tuple(
        dish.id for dish in state.dishes if dish.status is DishStatus.READY_TO_ADD
    )
    state.status = SessionStatus.CANCELLED
    return state, [SessionCancelledEffect(ready_to_add_dish_ids=ready_to_add_dish_ids)]
