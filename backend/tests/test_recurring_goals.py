import uuid
from contextlib import contextmanager
from datetime import date
from decimal import Decimal
from unittest.mock import patch

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.goal import Goal
from app.models.recurring_goal import RecurringGoal
from app.schemas.goal import GoalUpdate, RecurringGoalCreate, RecurringGoalUpdate
from app.services import goal_service
from app.services.recurring_goal_service import (
    create_recurring_goal,
    delete_recurring_goal,
    list_recurring_goals,
    next_start_after,
    period_containing,
    roll_workspace,
    update_recurring_goal,
    workspaces_with_recurring_goals,
)


@contextmanager
def _today(day: date):
    with patch("app.services.recurring_goal_service.app_today", return_value=day):
        yield


async def _instances(session: AsyncSession, recurring_goal_id: uuid.UUID) -> list[Goal]:
    result = await session.execute(
        select(Goal).where(Goal.recurring_goal_id == recurring_goal_id).order_by(Goal.period_start)
    )
    return list(result.scalars().all())


async def _rent(session, workspace, user, day: date, start_day: int = 10):
    with _today(day):
        return await create_recurring_goal(
            session, workspace.id, user.id,
            RecurringGoalCreate(name="Rent", target_amount=Decimal("500"), currency="EUR", start_day=start_day),
        )


# ---------------------------------------------------------------------------
# Period maths
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("day, start_day, expected", [
    (date(2026, 10, 20), 10, (date(2026, 10, 10), date(2026, 11, 9))),
    (date(2026, 10, 10), 10, (date(2026, 10, 10), date(2026, 11, 9))),
    # Before this month's start day the period began last month.
    (date(2026, 10, 9), 10, (date(2026, 9, 10), date(2026, 10, 9))),
    (date(2026, 1, 5), 10, (date(2025, 12, 10), date(2026, 1, 9))),
    (date(2026, 12, 15), 1, (date(2026, 12, 1), date(2026, 12, 31))),
    # Short months start on their last day.
    (date(2027, 2, 28), 31, (date(2027, 2, 28), date(2027, 3, 30))),
    (date(2027, 2, 27), 31, (date(2027, 1, 31), date(2027, 2, 27))),
    (date(2028, 2, 29), 30, (date(2028, 2, 29), date(2028, 3, 29))),
])
def test_period_containing(day, start_day, expected):
    assert period_containing(day, start_day) == expected


@pytest.mark.parametrize("day, start_day, expected", [
    (date(2026, 10, 12), 15, date(2026, 10, 15)),
    (date(2026, 10, 15), 15, date(2026, 11, 15)),
    (date(2026, 12, 20), 5, date(2027, 1, 5)),
    (date(2027, 1, 31), 31, date(2027, 2, 28)),
])
def test_next_start_after(day, start_day, expected):
    assert next_start_after(day, start_day) == expected


# ---------------------------------------------------------------------------
# Creating
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_covers_the_period_under_way(session: AsyncSession, test_user, test_workspace):
    recurring = await _rent(session, test_workspace, test_user, date(2026, 10, 20))

    assert recurring.is_active is True
    assert recurring.next_period_start == date(2026, 11, 10)
    assert recurring.periods_closed == 0
    [goal] = await _instances(session, recurring.id)
    assert recurring.current_goal_id == goal.id
    assert (goal.period_start, goal.period_end) == (date(2026, 10, 10), date(2026, 11, 9))
    assert goal.target_date == date(2026, 11, 9)
    assert goal.name == "Rent"
    assert goal.target_amount == Decimal("500")
    assert goal.current_amount == Decimal("0")
    assert goal.status == "active"
    assert goal.tracking_type == "manual"


# ---------------------------------------------------------------------------
# Rolling over
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_roll_is_a_noop_inside_the_period(session: AsyncSession, test_user, test_workspace):
    recurring = await _rent(session, test_workspace, test_user, date(2026, 10, 20))

    assert await roll_workspace(session, test_workspace.id, date(2026, 11, 9)) == 0

    [goal] = await _instances(session, recurring.id)
    assert goal.status == "active"


@pytest.mark.asyncio
@pytest.mark.parametrize("saved, outcome", [("500", "completed"), ("650", "completed"), ("499.99", "missed")])
async def test_roll_closes_the_old_period_and_opens_the_next(
    session: AsyncSession, test_user, test_workspace, saved, outcome
):
    recurring = await _rent(session, test_workspace, test_user, date(2026, 10, 20))
    [first] = await _instances(session, recurring.id)
    first.current_amount = Decimal(saved)
    await session.commit()

    assert await roll_workspace(session, test_workspace.id, date(2026, 11, 10)) == 1
    # A second run the same day must not create the period again.
    assert await roll_workspace(session, test_workspace.id, date(2026, 11, 10)) == 0

    first, second = await _instances(session, recurring.id)
    assert first.status == outcome
    assert (second.period_start, second.period_end) == (date(2026, 11, 10), date(2026, 12, 9))
    assert second.current_amount == Decimal("0")
    assert second.status == "active"
    template = await session.get(RecurringGoal, recurring.id)
    assert template is not None
    assert template.next_period_start == date(2026, 12, 10)


@pytest.mark.asyncio
async def test_roll_after_downtime_creates_only_the_current_period(
    session: AsyncSession, test_user, test_workspace
):
    recurring = await _rent(session, test_workspace, test_user, date(2026, 10, 20))

    assert await roll_workspace(session, test_workspace.id, date(2027, 2, 15)) == 1

    first, current = await _instances(session, recurring.id)
    assert first.status == "missed"
    assert (current.period_start, current.period_end) == (date(2027, 2, 10), date(2027, 3, 9))


@pytest.mark.asyncio
async def test_roll_closes_a_paused_instance(session: AsyncSession, test_user, test_workspace):
    recurring = await _rent(session, test_workspace, test_user, date(2026, 10, 20))
    [goal] = await _instances(session, recurring.id)
    goal.status = "paused"
    await session.commit()

    await roll_workspace(session, test_workspace.id, date(2026, 11, 10))

    first, _ = await _instances(session, recurring.id)
    assert first.status == "missed"


@pytest.mark.asyncio
async def test_roll_leaves_ordinary_goals_alone(session: AsyncSession, test_user, test_workspace):
    plain = Goal(
        user_id=test_user.id, workspace_id=test_workspace.id, name="Trip",
        target_amount=Decimal("1000"), current_amount=Decimal("0"), currency="EUR",
        target_date=date(2020, 1, 1),
    )
    session.add(plain)
    await session.commit()

    await roll_workspace(session, test_workspace.id, date(2026, 11, 10))

    await session.refresh(plain)
    assert plain.status == "active"


# ---------------------------------------------------------------------------
# Switching off and on
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_deactivated_goal_stops_generating_but_closes_its_last_period(
    session: AsyncSession, test_user, test_workspace
):
    recurring = await _rent(session, test_workspace, test_user, date(2026, 10, 20))
    with _today(date(2026, 10, 25)):
        updated = await update_recurring_goal(
            session, recurring.id, test_workspace.id, RecurringGoalUpdate(is_active=False)
        )
    assert updated is not None
    assert updated.is_active is False
    assert test_workspace.id in await workspaces_with_recurring_goals(session)

    assert await roll_workspace(session, test_workspace.id, date(2026, 11, 10)) == 0

    [goal] = await _instances(session, recurring.id)
    assert goal.status == "missed"


@pytest.mark.asyncio
async def test_reactivating_creates_the_period_under_way(
    session: AsyncSession, test_user, test_workspace
):
    recurring = await _rent(session, test_workspace, test_user, date(2026, 10, 20))
    with _today(date(2026, 10, 25)):
        await update_recurring_goal(
            session, recurring.id, test_workspace.id, RecurringGoalUpdate(is_active=False)
        )
    await roll_workspace(session, test_workspace.id, date(2027, 1, 20))

    with _today(date(2027, 1, 20)):
        updated = await update_recurring_goal(
            session, recurring.id, test_workspace.id, RecurringGoalUpdate(is_active=True)
        )

    _, current = await _instances(session, recurring.id)
    assert (current.period_start, current.period_end) == (date(2027, 1, 10), date(2027, 2, 9))
    assert updated is not None
    assert updated.current_goal_id == current.id
    assert updated.next_period_start == date(2027, 2, 10)
    assert (updated.periods_closed, updated.periods_met) == (1, 0)


@pytest.mark.asyncio
async def test_reactivating_inside_the_same_period_reuses_its_goal(
    session: AsyncSession, test_user, test_workspace
):
    recurring = await _rent(session, test_workspace, test_user, date(2026, 10, 20))
    for active in (False, True):
        with _today(date(2026, 10, 25)):
            await update_recurring_goal(
                session, recurring.id, test_workspace.id, RecurringGoalUpdate(is_active=active)
            )

    assert len(await _instances(session, recurring.id)) == 1


# ---------------------------------------------------------------------------
# Editing
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_new_target_applies_from_the_next_period(
    session: AsyncSession, test_user, test_workspace
):
    recurring = await _rent(session, test_workspace, test_user, date(2026, 10, 20))
    with _today(date(2026, 10, 25)):
        await update_recurring_goal(
            session, recurring.id, test_workspace.id,
            RecurringGoalUpdate(target_amount=Decimal("550"), name=" Rent and bills "),
        )
    await roll_workspace(session, test_workspace.id, date(2026, 11, 10))

    first, second = await _instances(session, recurring.id)
    assert first.target_amount == Decimal("500")
    assert second.target_amount == Decimal("550")
    # The name is cosmetic and reaches the period under way too.
    assert first.name == second.name == "Rent and bills"


@pytest.mark.asyncio
@pytest.mark.parametrize("new_day, period_end, next_start", [
    (15, date(2026, 11, 14), date(2026, 11, 15)),
    (25, date(2026, 10, 24), date(2026, 10, 25)),
    (5, date(2026, 11, 4), date(2026, 11, 5)),
])
async def test_new_start_day_reshapes_the_period_under_way(
    session: AsyncSession, test_user, test_workspace, new_day, period_end, next_start
):
    recurring = await _rent(session, test_workspace, test_user, date(2026, 10, 20))
    with _today(date(2026, 10, 20)):
        updated = await update_recurring_goal(
            session, recurring.id, test_workspace.id, RecurringGoalUpdate(start_day=new_day)
        )

    [goal] = await _instances(session, recurring.id)
    assert goal.period_start == date(2026, 10, 10)
    assert goal.period_end == goal.target_date == period_end
    assert updated is not None
    assert updated.next_period_start == next_start

    # No gap and no overlap with the period that follows.
    await roll_workspace(session, test_workspace.id, next_start)
    _, following = await _instances(session, recurring.id)
    assert following.period_start == next_start


@pytest.mark.asyncio
async def test_correcting_a_closed_period_recomputes_its_outcome(
    session: AsyncSession, test_user, test_workspace
):
    recurring = await _rent(session, test_workspace, test_user, date(2026, 10, 20))
    await roll_workspace(session, test_workspace.id, date(2026, 11, 10))
    first, _ = await _instances(session, recurring.id)
    assert first.status == "missed"

    read = await goal_service.update_goal(
        session, first.id, test_workspace.id, test_user.id, GoalUpdate(current_amount=Decimal("500"))
    )
    assert read is not None
    assert read.status == "completed"

    read = await goal_service.update_goal(
        session, first.id, test_workspace.id, test_user.id, GoalUpdate(current_amount=Decimal("100"))
    )
    assert read is not None
    assert read.status == "missed"

    # An explicit status is the user's call and is left as given.
    read = await goal_service.update_goal(
        session, first.id, test_workspace.id, test_user.id,
        GoalUpdate(current_amount=Decimal("600"), status="archived"),
    )
    assert read is not None
    assert read.status == "archived"


@pytest.mark.asyncio
async def test_saving_into_the_open_period_does_not_close_it(
    session: AsyncSession, test_user, test_workspace
):
    recurring = await _rent(session, test_workspace, test_user, date(2026, 10, 20))
    [goal] = await _instances(session, recurring.id)

    read = await goal_service.update_goal(
        session, goal.id, test_workspace.id, test_user.id, GoalUpdate(current_amount=Decimal("500"))
    )
    assert read is not None

    assert read.status == "active"
    assert read.recurring_goal_id == recurring.id
    assert read.period_end == date(2026, 11, 9)


# ---------------------------------------------------------------------------
# Deleting
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize("delete_history", [True, False])
async def test_delete_keeps_or_removes_history(
    session: AsyncSession, test_user, test_workspace, delete_history
):
    recurring = await _rent(session, test_workspace, test_user, date(2026, 10, 20))
    await roll_workspace(session, test_workspace.id, date(2026, 11, 10))
    ids = [g.id for g in await _instances(session, recurring.id)]

    assert await delete_recurring_goal(session, recurring.id, test_workspace.id, delete_history)

    assert await session.get(RecurringGoal, recurring.id) is None
    session.expire_all()
    left = (await session.execute(select(Goal).where(Goal.id.in_(ids)))).scalars().all()
    if delete_history:
        assert left == []
    else:
        assert len(left) == 2
        assert all(goal.recurring_goal_id is None for goal in left)


@pytest.mark.asyncio
async def test_other_workspace_cannot_touch_a_recurring_goal(
    session: AsyncSession, test_user, test_workspace
):
    recurring = await _rent(session, test_workspace, test_user, date(2026, 10, 20))
    stranger = uuid.uuid4()

    assert await update_recurring_goal(
        session, recurring.id, stranger, RecurringGoalUpdate(is_active=False)
    ) is None
    assert await delete_recurring_goal(session, recurring.id, stranger, True) is False
    assert await list_recurring_goals(session, stranger) == []
    assert len(await _instances(session, recurring.id)) == 1


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_recurring_goal_api_round_trip(client: AsyncClient, auth_headers: dict):
    created = await client.post(
        "/api/goals/recurring",
        json={"name": "Savings", "target_amount": "200", "currency": "eur", "start_day": 1, "icon": "piggy-bank"},
        headers=auth_headers,
    )
    assert created.status_code == 201
    body = created.json()
    assert body["currency"] == "EUR"
    assert body["current_goal_id"]

    listed = await client.get("/api/goals/recurring", headers=auth_headers)
    assert [r["id"] for r in listed.json()] == [body["id"]]

    # The instance is an ordinary goal: it shows in the list and the summary.
    goals = (await client.get("/api/goals", headers=auth_headers)).json()
    instance = next(g for g in goals if g["id"] == body["current_goal_id"])
    assert instance["recurring_goal_id"] == body["id"]
    assert instance["period_start"] and instance["period_end"]
    assert instance["icon"] == "piggy-bank"
    summary = (await client.get("/api/goals/summary", headers=auth_headers)).json()
    assert body["current_goal_id"] in [g["id"] for g in summary]

    history = await client.get(
        "/api/goals", params={"recurring_goal_id": body["id"]}, headers=auth_headers
    )
    assert [g["id"] for g in history.json()] == [body["current_goal_id"]]

    patched = await client.patch(
        f"/api/goals/recurring/{body['id']}", json={"is_active": False}, headers=auth_headers
    )
    assert patched.status_code == 200
    assert patched.json()["is_active"] is False

    deleted = await client.delete(
        f"/api/goals/recurring/{body['id']}", params={"delete_history": "true"}, headers=auth_headers
    )
    assert deleted.status_code == 204
    assert (await client.get("/api/goals/recurring", headers=auth_headers)).json() == []
    assert (await client.get(f"/api/goals/{body['current_goal_id']}", headers=auth_headers)).status_code == 404


@pytest.mark.asyncio
@pytest.mark.parametrize("payload", [
    {"name": "Rent", "target_amount": "500", "start_day": 0},
    {"name": "Rent", "target_amount": "500", "start_day": 32},
    {"name": "Rent", "target_amount": "0", "start_day": 10},
    {"name": "", "target_amount": "500", "start_day": 10},
])
async def test_recurring_goal_api_rejects_bad_input(client: AsyncClient, auth_headers: dict, payload):
    response = await client.post("/api/goals/recurring", json=payload, headers=auth_headers)
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_recurring_goal_api_unknown_id(client: AsyncClient, auth_headers: dict):
    missing = uuid.uuid4()
    assert (await client.patch(
        f"/api/goals/recurring/{missing}", json={"is_active": False}, headers=auth_headers
    )).status_code == 404
    assert (await client.delete(f"/api/goals/recurring/{missing}", headers=auth_headers)).status_code == 404
