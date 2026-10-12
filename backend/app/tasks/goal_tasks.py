import asyncio
import logging

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.app_clock import get_timezone, get_workspace_timezone, today_in, use_resolved_timezone
from app.core.config import get_settings
from app.services import recurring_goal_service
from app.worker import celery_app

logger = logging.getLogger(__name__)


def _make_session_maker():
    """Create a fresh engine+session for the Celery worker event loop."""
    settings = get_settings()
    engine = create_async_engine(settings.database_url)
    return engine, async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def _roll_all() -> int:
    """Close ended periods and open new ones for every workspace."""
    engine, session_maker = _make_session_maker()
    try:
        total = 0
        async with session_maker() as session:
            operation_timezone = await get_timezone(session, fresh=True)
            workspace_ids = await recurring_goal_service.workspaces_with_recurring_goals(session)

        with use_resolved_timezone(operation_timezone):
            for workspace_id in workspace_ids:
                try:
                    async with session_maker() as session:
                        # A period turns over at the workspace's own midnight.
                        today = today_in(await get_workspace_timezone(session, workspace_id))
                        total += await recurring_goal_service.roll_workspace(
                            session, workspace_id, today
                        )
                except Exception:
                    logger.exception("Failed to roll recurring goals for workspace %s", workspace_id)
    finally:
        await engine.dispose()
    return total


@celery_app.task(name="app.tasks.goal_tasks.roll_recurring_goals")
def roll_recurring_goals() -> dict:
    """Celery task: advance recurring goals to the current period."""
    total = asyncio.run(_roll_all())
    logger.info("Recurring goals rolled: %d goals created", total)
    return {"created": total}
