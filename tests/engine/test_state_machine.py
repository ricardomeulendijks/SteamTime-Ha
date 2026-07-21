"""Tests for `advance`, `confirm_dish`, and `cancel_session` (design §3.2-3.4)."""

from __future__ import annotations

from custom_components.steamtime.engine import (
    AddAlertEffect,
    DishStatus,
    DoneAlertEffect,
    SessionCancelledEffect,
    SessionCompletedEffect,
    SessionStatus,
    advance,
    build_session,
    cancel_session,
    confirm_dish,
)

from .conftest import T0, dish


def test_late_confirmation_shifts_only_its_own_dish() -> None:
    # d1 = Potatoes (20 min, offset 0), d2 = Peas (10 min, offset 10 min).
    state = build_session("s1", [dish("Potatoes", 20), dish("Peas", 10)], now=T0)
    state, _ = advance(state, T0)  # d1 ready immediately
    state, _ = confirm_dish(state, "d1", T0)  # confirmed on time

    state, effects = advance(state, T0 + 600)  # 10 min later: d2 ready
    assert {e.dish_id for e in effects if isinstance(e, AddAlertEffect)} == {"d2"}

    # d2 confirmed 5 minutes late.
    late_confirm_at = T0 + 600 + 300
    state, warning = confirm_dish(state, "d2", late_confirm_at)
    assert warning is False

    by_id = {d.id: d for d in state.dishes}
    # d1's own doneAt is exactly as planned when it was confirmed on time —
    # d2's late confirmation, arriving after d1's, does not touch it.
    assert by_id["d1"].done_at == T0 + 20 * 60
    # d2's doneAt derives from its own (late) confirmedAt, not the plan.
    assert by_id["d2"].confirmed_at == late_confirm_at
    assert by_id["d2"].done_at == late_confirm_at + 10 * 60


def test_late_first_confirmation_shifts_still_pending_dishes_forward() -> None:
    # d1 = Potatoes (20 min, offset 0), d2 = Peas (10 min, offset 10 min).
    state = build_session("s1", [dish("Potatoes", 20), dish("Peas", 10)], now=T0)
    state, _ = advance(state, T0)  # d1 ready immediately; d2 still pending

    # d1 confirmed 30s late — the walk-to-the-oven delay.
    late_anchor_confirm_at = T0 + 30
    state, warning = confirm_dish(state, "d1", late_anchor_confirm_at)
    assert warning is False

    by_id = {d.id: d for d in state.dishes}
    assert by_id["d1"].done_at == late_anchor_confirm_at + 20 * 60
    # d2's planned_add_at shifts forward by the same 30s so it still becomes
    # ready 10 minutes after d1 actually went in, not 10 minutes after the
    # original (now-stale) session-start anchor.
    assert by_id["d2"].planned_add_at == T0 + 600 + 30
    assert by_id["d2"].status is DishStatus.PENDING


def test_on_time_first_confirmation_does_not_shift_pending_dishes() -> None:
    state = build_session("s1", [dish("Potatoes", 20), dish("Peas", 10)], now=T0)
    state, _ = advance(state, T0)
    state, _ = confirm_dish(state, "d1", T0)  # confirmed exactly on time

    by_id = {d.id: d for d in state.dishes}
    assert by_id["d2"].planned_add_at == T0 + 600


def test_late_anchor_confirmation_does_not_shift_already_ready_dishes() -> None:
    # d2's own offset (5 min) passes before d1 (offset 0, 20 min) is finally
    # confirmed 10 minutes late — d2 is already `ready_to_add` by then and
    # must not be shifted again; its alert already fired.
    state = build_session("s1", [dish("Potatoes", 20), dish("Peas", 15)], now=T0)
    state, _ = advance(state, T0)  # only d1 ready

    state, effects = advance(state, T0 + 300)  # 5 min later: d2 becomes ready
    assert {e.dish_id for e in effects if isinstance(e, AddAlertEffect)} == {"d2"}
    d2_planned_before = next(d for d in state.dishes if d.id == "d2").planned_add_at

    state, _ = confirm_dish(state, "d1", T0 + 600)  # d1 confirmed 10 min late

    by_id = {d.id: d for d in state.dishes}
    assert by_id["d2"].planned_add_at == d2_planned_before
    assert by_id["d2"].status is DishStatus.READY_TO_ADD


def test_tied_offset_zero_dishes_only_shift_pending_once() -> None:
    # d1 (Potatoes, 20 min) and d2 (Fish, 20 min) share offset 0 and are both
    # ready immediately; d3 (Peas, 5 min) has offset 15 min and stays pending.
    state = build_session(
        "s1", [dish("Potatoes", 20), dish("Fish", 20), dish("Peas", 5)], now=T0
    )
    state, _ = advance(state, T0)

    state, _ = confirm_dish(state, "d1", T0 + 60)  # first anchor, 60s late
    by_id = {d.id: d for d in state.dishes}
    assert by_id["d3"].planned_add_at == T0 + 900 + 60

    # d2 (the other offset-0 dish) confirmed later still must not shift d3
    # a second time.
    state, _ = confirm_dish(state, "d2", T0 + 200)
    by_id = {d.id: d for d in state.dishes}
    assert by_id["d3"].planned_add_at == T0 + 900 + 60


def test_confirm_on_non_ready_dish_is_warning_no_op() -> None:
    state = build_session("s1", [dish("Potatoes", 20), dish("Peas", 10)], now=T0)
    state, _ = advance(state, T0)  # only d1 is ready_to_add; d2 still pending

    # d2 is pending, not ready_to_add.
    state, warning = confirm_dish(state, "d2", T0)
    assert warning is True
    assert state.dishes[1].status is DishStatus.PENDING

    # Unknown dish id.
    state, warning = confirm_dish(state, "does-not-exist", T0)
    assert warning is True

    # Double-tapped confirmation on an already-cooking dish.
    state, warning = confirm_dish(state, "d1", T0)
    assert warning is False
    state, warning = confirm_dish(state, "d1", T0 + 1)
    assert warning is True
    assert state.dishes[0].confirmed_at == T0  # unchanged by the second call


def test_confirm_with_no_session_running_is_warning_no_op() -> None:
    state = build_session("s1", [dish("Potatoes", 20)], now=T0)
    state, _ = advance(state, T0)
    state, _ = confirm_dish(state, "d1", T0)
    state, _ = advance(state, T0 + 20 * 60)  # session completes
    assert state.status is SessionStatus.COMPLETED

    state, warning = confirm_dish(state, "d1", T0 + 999)
    assert warning is True


def test_cancellation_writes_nothing_and_stops_further_transitions() -> None:
    state = build_session("s1", [dish("Potatoes", 20)], now=T0)
    state, _ = advance(state, T0)
    state, _ = confirm_dish(state, "d1", T0)

    state, effects = cancel_session(state)
    assert state.status is SessionStatus.CANCELLED
    assert effects == [SessionCancelledEffect(ready_to_add_dish_ids=())]

    # Even though done_at has long passed, a cancelled session never advances.
    state, effects = advance(state, T0 + 10_000)
    assert effects == []
    assert state.dishes[0].status is DishStatus.COOKING


def test_cancellation_reports_ready_to_add_dishes_for_notification_clearing() -> None:
    # d1 (Potatoes, 20 min) and d2 (Fish, 20 min) share offset 0 and both
    # become ready_to_add together; d3 (Peas, 5 min) stays pending. Only d1
    # gets confirmed, so only d2 has an outstanding add-notification to clear
    # (d3 never had one — it hasn't become ready_to_add yet).
    state = build_session(
        "s1", [dish("Potatoes", 20), dish("Fish", 20), dish("Peas", 5)], now=T0
    )
    state, _ = advance(state, T0)
    state, _ = confirm_dish(state, "d1", T0)

    state, effects = cancel_session(state)
    assert effects == [SessionCancelledEffect(ready_to_add_dish_ids=("d2",))]

    # Cancelling an already-cancelled session is a no-op.
    state, effects = cancel_session(state)
    assert effects == []


def test_completion_snapshot_content() -> None:
    state = build_session(
        "s1",
        [dish("Potatoes", 20, temperature=100, category="vegetables")],
        now=T0,
    )
    state, _ = advance(state, T0)
    state, _ = confirm_dish(state, "d1", T0 + 30)  # confirmed 30s late

    state, effects = advance(state, T0 + 30 + 20 * 60)
    completed = [e for e in effects if isinstance(e, SessionCompletedEffect)]
    assert len(completed) == 1
    snapshot = completed[0]
    assert snapshot.completed_at == T0 + 30 + 20 * 60
    assert len(snapshot.dishes) == 1
    dish_snapshot = snapshot.dishes[0]
    assert dish_snapshot.id == "d1"
    assert dish_snapshot.name_en == "Potatoes"
    assert dish_snapshot.steam_minutes == 20
    assert dish_snapshot.temperature == 100
    assert dish_snapshot.category == "vegetables"
    assert dish_snapshot.confirmed_at == T0 + 30
    assert dish_snapshot.done_at == T0 + 30 + 20 * 60
    assert state.status is SessionStatus.COMPLETED


def test_fast_forward_ha_down_20_minutes_transitions_straight_to_done() -> None:
    state = build_session("s1", [dish("Fish", 10)], now=T0)
    state, _ = advance(state, T0)
    state, _ = confirm_dish(state, "d1", T0)
    assert state.dishes[0].status is DishStatus.COOKING

    # HA was down for 20 minutes; dish's 10-minute cook finished long ago.
    restart_now = T0 + 20 * 60
    state, effects = advance(state, restart_now)

    assert state.dishes[0].status is DishStatus.DONE
    done_effects = [e for e in effects if isinstance(e, DoneAlertEffect)]
    assert len(done_effects) == 1
    assert done_effects[0].dish_id == "d1"
    completed_effects = [e for e in effects if isinstance(e, SessionCompletedEffect)]
    assert len(completed_effects) == 1
    assert completed_effects[0].completed_at == T0 + 10 * 60  # not `restart_now`


def test_idempotent_replay_of_same_advance_call() -> None:
    state = build_session("s1", [dish("Fish", 10), dish("Peas", 5)], now=T0)

    state, effects_first = advance(state, T0)
    assert len(effects_first) == 1  # only d1 (offset 0) is ready

    # Replaying the exact same `now` must change nothing further.
    state, effects_replay = advance(state, T0)
    assert effects_replay == []

    # Replaying an earlier-than-current-progress `now` is also a no-op.
    state, effects_replay_past = advance(state, T0 - 100)
    assert effects_replay_past == []
