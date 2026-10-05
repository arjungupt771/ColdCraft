import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.errors import AIError
from app.ai.researcher import research_company
from app.domain.state_machine import ApplicationStatus as S, transition
from app.integrations import hunter
from app.models.models import JobApplication
from app.services.application_service import get_application

logger = logging.getLogger(__name__)


async def find_recruiter(db: AsyncSession, app: JobApplication) -> None:
    """Fill recipient_email/name if still empty. Never raises: a missing recruiter isn't fatal."""
    if app.recipient_email:
        return
    try:
        info = await hunter.find_recruiter(app.company_name, app.company_website)
    except Exception as e:
        logger.warning("Recruiter lookup failed for %s: %s", app.company_name, e)
        return
    if info:
        app.recipient_email = info.email
        app.recipient_name = app.recipient_name or info.name
        app.recipient_source = info.source                 # 'hunter' (found) or 'guess' (careers@ fallback)


async def research_application(db: AsyncSession, app_id: str) -> JobApplication:
    """DRAFT|READY → RESEARCHING → READY. On failure the app returns to DRAFT with last_error set."""
    app = await get_application(db, app_id)
    transition(app, S.RESEARCHING)
    await db.commit()
    try:
        result = await research_company(app.company_name, app.company_website)
        app.company_research = result.text
        await find_recruiter(db, app)
        app.last_error = None
        transition(app, S.READY)
    except Exception as e:
        # Persist the failed state first (get_db would otherwise roll it back), then surface the error.
        await db.rollback()
        app = await get_application(db, app_id)
        app.last_error = (e.detail if isinstance(e, AIError) else str(e))[:500]
        transition(app, S.DRAFT)
        await db.commit()
        raise
    await db.commit()
    await db.refresh(app)
    return app
