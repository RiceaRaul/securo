"""Recurring goals: a monthly template and the goals it produces.

A period runs from the template's start day to the day before the next one.
Each period gets one ordinary goal (an "instance") that starts at zero. When
the period is over the instance is closed as completed or missed and the next
one is created, until the template is switched off.
"""
import calendar
import uuid
from datetime import date, timedelta
from decimal import Decimal
from typing import Optional

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.app_clock import app_today
from app.models.goal import Goal
from app.models.recurring_goal import RecurringGoal
from app.schemas.goal import RecurringGoalCreate, RecurringGoalRead, RecurringGoalUpdate
from app.services.goal_service import closed_period_status

_OPEN_STATUSES = ("active", "paused")
_CLOSED_STATUSES = ("completed", "missed")


def _start_in_month(year: int, month: int, start_day: int) -> date:
    """The period start falling in a month; short months use their last day."""
    return date(year, month, min(start_day, calendar.monthrange(year, month)[1]))


def _shift_month(year: int, month: int, delta: int) -> tuple[int, int]:
    index = year * 12 + (month - 1) + delta
    return index // 12, index % 12 + 1


def period_containing(day: date, start_day: int) -> tuple[date, date]:
    """First and last day (inclusive) of the period ``day`` falls in."""
    start = _start_in_month(day.year, day.month, start_day)
    if day < start:
        start = _start_in_month(*_shift_month(day.year, day.month, -1), start_day)
    following = _start_in_month(*_shift_month(start.year, start.month, 1), start_day)
    return start, following - timedelta(days=1)


def next_start_after(day: date, start_day: int) -> date:
    """First period start strictly after ``day``."""
    start = _start_in_month(day.year, day.month, start_day)
    if start <= day:
        start = _start_in_month(*_shift_month(day.year, day.month, 1), start_day)
    return start


async def _open_instance(
    session: AsyncSession, recurring_goal_id: uuid.UUID, today: date
) -> Optional[Goal]:
    """The instance whose period has not ended yet, whatever its status."""
    result = await session.execute(
        select(Goal)
        .where(Goal.recurring_goal_id == recurring_goal_id, Goal.period_end >= today)
        .order_by(Goal.period_start.desc())
    )
    return result.scalars().first()


async def _create_instance(
    session: AsyncSession, template: RecurringGoal, start: date, end: date
) -> Goal:
    goal = Goal(
        user_id=template.user_id,
        workspace_id=template.workspace_id,
        name=template.name,
        target_amount=template.target_amount,
        current_amount=Decimal("0.00"),
        initial_amount=Decimal("0.00"),
        currency=template.currency,
        # The period's last day doubles as the deadline, so the goals list
        # shows days remaining and pace without knowing about recurrence.
        target_date=end,
        tracking_type="manual",
        icon=template.icon,
        color=template.color,
        recurring_goal_id=template.id,
        period_start=start,
        period_end=end,
    )
    session.add(goal)
    await session.flush()
    return goal


async def _ensure_current_instance(
    session: AsyncSession, template: RecurringGoal, today: date
) -> bool:
    """Make sure today's period has an instance and move the cursor past it.

    Returns whether an instance had to be created.
    """
    current = await _open_instance(session, template.id, today)
    created = current is None
    if current is None:
        start, end = period_containing(today, template.start_day)
        current = await _create_instance(session, template, start, end)
        template.next_period_start = end + timedelta(days=1)
    elif current.period_end is not None:
        template.next_period_start = current.period_end + timedelta(days=1)
    return created


async def _read(session: AsyncSession, template: RecurringGoal, today: date) -> RecurringGoalRead:
    closed = await session.execute(
        select(Goal.status, func.count())
        .where(
            Goal.recurring_goal_id == template.id,
            Goal.status.in_(_CLOSED_STATUSES),
        )
        .group_by(Goal.status)
    )
    counts: dict[str, int] = {status: count for status, count in closed.all()}
    current = await _open_instance(session, template.id, today)
    read = RecurringGoalRead.model_validate(template)
    read.current_goal_id = current.id if current else None
    read.periods_met = counts.get("completed", 0)
    read.periods_closed = read.periods_met + counts.get("missed", 0)
    return read


async def _get(
    session: AsyncSession, recurring_goal_id: uuid.UUID, workspace_id: uuid.UUID
) -> Optional[RecurringGoal]:
    result = await session.execute(
        select(RecurringGoal).where(
            RecurringGoal.id == recurring_goal_id, RecurringGoal.workspace_id == workspace_id
        )
    )
    return result.scalar_one_or_none()


async def list_recurring_goals(
    session: AsyncSession, workspace_id: uuid.UUID
) -> list[RecurringGoalRead]:
    result = await session.execute(
        select(RecurringGoal)
        .where(RecurringGoal.workspace_id == workspace_id)
        .order_by(RecurringGoal.created_at)
    )
    today = app_today()
    return [await _read(session, template, today) for template in result.scalars().all()]


async def create_recurring_goal(
    session: AsyncSession, workspace_id: uuid.UUID, user_id: uuid.UUID, data: RecurringGoalCreate
) -> RecurringGoalRead:
    today = app_today()
    template = RecurringGoal(
        user_id=user_id,
        workspace_id=workspace_id,
        name=data.name.strip(),
        target_amount=data.target_amount,
        currency=data.currency.upper(),
        start_day=data.start_day,
        icon=data.icon,
        color=data.color,
        next_period_start=today,
    )
    session.add(template)
    await session.flush()
    # The period already under way gets its goal right away rather than
    # waiting for the next start day.
    await _ensure_current_instance(session, template, today)
    await session.commit()
    await session.refresh(template)
    return await _read(session, template, today)


async def update_recurring_goal(
    session: AsyncSession,
    recurring_goal_id: uuid.UUID,
    workspace_id: uuid.UUID,
    data: RecurringGoalUpdate,
) -> Optional[RecurringGoalRead]:
    template = await _get(session, recurring_goal_id, workspace_id)
    if template is None:
        return None
    today = app_today()
    changes = data.model_dump(exclude_unset=True)
    current = await _open_instance(session, template.id, today)

    # Looks follow through to the period under way; the target does not, so a
    # month already in progress keeps the amount it started with.
    for field in ("name", "icon", "color"):
        if field in changes:
            value = changes[field].strip() if field == "name" else changes[field]
            setattr(template, field, value)
            if current is not None:
                setattr(current, field, value)
    if changes.get("target_amount") is not None:
        template.target_amount = changes["target_amount"]

    new_day = changes.get("start_day")
    if new_day is not None and new_day != template.start_day:
        template.start_day = new_day
        template.next_period_start = next_start_after(today, new_day)
        # Stretch or shorten the period under way so it meets the next one
        # with no gap and no overlap.
        if current is not None:
            current.period_end = template.next_period_start - timedelta(days=1)
            current.target_date = current.period_end

    if changes.get("is_active") is not None and changes["is_active"] != template.is_active:
        template.is_active = changes["is_active"]
        if template.is_active:
            await _ensure_current_instance(session, template, today)

    await session.commit()
    await session.refresh(template)
    return await _read(session, template, today)


async def delete_recurring_goal(
    session: AsyncSession,
    recurring_goal_id: uuid.UUID,
    workspace_id: uuid.UUID,
    delete_history: bool = False,
) -> bool:
    template = await _get(session, recurring_goal_id, workspace_id)
    if template is None:
        return False
    if delete_history:
        await session.execute(delete(Goal).where(Goal.recurring_goal_id == template.id))
    else:
        # Kept periods become plain goals. Done here as well as by the foreign
        # key so it does not depend on the database enforcing ON DELETE.
        await session.execute(
            update(Goal).where(Goal.recurring_goal_id == template.id).values(recurring_goal_id=None)
        )
    await session.delete(template)
    await session.commit()
    return True


async def roll_workspace(session: AsyncSession, workspace_id: uuid.UUID, today: date) -> int:
    """Close periods that ended and open the ones that began, for one workspace.

    Safe to run any number of times: a period is created only when the cursor
    has been reached and no instance covers today. Returns how many goals
    were created.
    """
    # Templates that were switched off still get their last period closed.
    ended = await session.execute(
        select(Goal).where(
            Goal.workspace_id == workspace_id,
            Goal.recurring_goal_id.is_not(None),
            Goal.status.in_(_OPEN_STATUSES),
            Goal.period_end < today,
        )
    )
    for goal in ended.scalars().all():
        goal.status = closed_period_status(goal)

    due = await session.execute(
        select(RecurringGoal).where(
            RecurringGoal.workspace_id == workspace_id,
            RecurringGoal.is_active.is_(True),
            RecurringGoal.next_period_start <= today,
        )
    )
    created = 0
    for template in due.scalars().all():
        # After downtime only the period under way is created; the months
        # nobody could have filled in are not added as missed.
        if await _ensure_current_instance(session, template, today):
            created += 1
    await session.commit()
    return created


async def workspaces_with_recurring_goals(session: AsyncSession) -> list[uuid.UUID]:
    templates = select(RecurringGoal.workspace_id)
    instances = select(Goal.workspace_id).where(
        Goal.recurring_goal_id.is_not(None), Goal.status.in_(_OPEN_STATUSES)
    )
    result = await session.execute(templates.union(instances))
    return [row[0] for row in result.all()]
