import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_async_session
from app.core.workspace_context import (
    WorkspaceContext,
    current_workspace,
    current_writable_workspace,
)
from app.schemas.goal import (
    GoalCreate,
    GoalRead,
    GoalSummary,
    GoalUpdate,
    RecurringGoalCreate,
    RecurringGoalRead,
    RecurringGoalUpdate,
)
from app.services import goal_service, recurring_goal_service

router = APIRouter(prefix="/api/goals", tags=["goals"])


@router.get("", response_model=list[GoalRead])
async def list_goals(
    status: Optional[str] = Query(None),
    recurring_goal_id: Optional[uuid.UUID] = Query(None),
    ctx: WorkspaceContext = Depends(current_workspace),
    session: AsyncSession = Depends(get_async_session),
):
    return await goal_service.get_goals(
        session, ctx.workspace.id, ctx.user_id, status, recurring_goal_id
    )


@router.get("/summary", response_model=list[GoalSummary])
async def goal_summary(
    limit: int = Query(3, ge=1, le=10),
    ctx: WorkspaceContext = Depends(current_workspace),
    session: AsyncSession = Depends(get_async_session),
):
    return await goal_service.get_goal_summary(session, ctx.workspace.id, ctx.user_id, limit)


# Declared before the /{goal_id} routes so "recurring" is not read as an id.
@router.get("/recurring", response_model=list[RecurringGoalRead])
async def list_recurring_goals(
    ctx: WorkspaceContext = Depends(current_workspace),
    session: AsyncSession = Depends(get_async_session),
):
    return await recurring_goal_service.list_recurring_goals(session, ctx.workspace.id)


@router.post("/recurring", response_model=RecurringGoalRead, status_code=status.HTTP_201_CREATED)
async def create_recurring_goal(
    data: RecurringGoalCreate,
    ctx: WorkspaceContext = Depends(current_writable_workspace),
    session: AsyncSession = Depends(get_async_session),
):
    return await recurring_goal_service.create_recurring_goal(
        session, ctx.workspace.id, ctx.user_id, data
    )


@router.patch("/recurring/{recurring_goal_id}", response_model=RecurringGoalRead)
async def update_recurring_goal(
    recurring_goal_id: uuid.UUID,
    data: RecurringGoalUpdate,
    ctx: WorkspaceContext = Depends(current_writable_workspace),
    session: AsyncSession = Depends(get_async_session),
):
    recurring = await recurring_goal_service.update_recurring_goal(
        session, recurring_goal_id, ctx.workspace.id, data
    )
    if not recurring:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Recurring goal not found")
    return recurring


@router.delete("/recurring/{recurring_goal_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_recurring_goal(
    recurring_goal_id: uuid.UUID,
    delete_history: bool = Query(False),
    ctx: WorkspaceContext = Depends(current_writable_workspace),
    session: AsyncSession = Depends(get_async_session),
):
    deleted = await recurring_goal_service.delete_recurring_goal(
        session, recurring_goal_id, ctx.workspace.id, delete_history
    )
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Recurring goal not found")


@router.post("", response_model=GoalRead, status_code=status.HTTP_201_CREATED)
async def create_goal(
    data: GoalCreate,
    ctx: WorkspaceContext = Depends(current_writable_workspace),
    session: AsyncSession = Depends(get_async_session),
):
    try:
        return await goal_service.create_goal(session, ctx.workspace.id, ctx.user_id, data)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/{goal_id}", response_model=GoalRead)
async def get_goal(
    goal_id: uuid.UUID,
    ctx: WorkspaceContext = Depends(current_workspace),
    session: AsyncSession = Depends(get_async_session),
):
    goal = await goal_service.get_goal(session, goal_id, ctx.workspace.id, ctx.user_id)
    if not goal:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Goal not found")
    return goal


@router.patch("/{goal_id}", response_model=GoalRead)
async def update_goal(
    goal_id: uuid.UUID,
    data: GoalUpdate,
    ctx: WorkspaceContext = Depends(current_writable_workspace),
    session: AsyncSession = Depends(get_async_session),
):
    try:
        goal = await goal_service.update_goal(session, goal_id, ctx.workspace.id, ctx.user_id, data)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    if not goal:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Goal not found")
    return goal


@router.delete("/{goal_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_goal(
    goal_id: uuid.UUID,
    ctx: WorkspaceContext = Depends(current_writable_workspace),
    session: AsyncSession = Depends(get_async_session),
):
    deleted = await goal_service.delete_goal(session, goal_id, ctx.workspace.id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Goal not found")
