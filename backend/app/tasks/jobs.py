"""Background jobs. Each task is a thin wrapper that opens a session and calls a service."""
import asyncio
import logging

from app.core.config import settings
from app.core.database import task_session
from app.services import (
    application_pipeline, email_service, followup_service, research_service,
)
from app.tasks.celery_app import celery

logger = logging.getLogger(__name__)


def _run(coro):
    return asyncio.run(coro)


async def _with_session(fn, *args):
    async with task_session() as db:
        return await fn(db, *args)


@celery.task(name="coldcraft.research_company", autoretry_for=(Exception,), retry_backoff=True, max_retries=2)
def research_company_task(app_id: str) -> str:
    return _run(_with_session(research_service.research_application, app_id)).id


@celery.task(name="coldcraft.find_recruiter")
def find_recruiter_task(app_id: str) -> str | None:
    async def go(db, app_id):
        from app.services.application_service import get_application
        app = await get_application(db, app_id)
        await research_service.find_recruiter(db, app)
        await db.commit()
        return app.recipient_email
    return _run(_with_session(go, app_id))


@celery.task(name="coldcraft.generate_email", autoretry_for=(Exception,), retry_backoff=True, max_retries=2)
def generate_email_task(app_id: str) -> str:
    return _run(_with_session(email_service.generate_email, app_id)).id


@celery.task(name="coldcraft.capture_to_draft_email")
def capture_to_draft_email_task(app_id: str) -> str:
    return _run(_with_session(application_pipeline.capture_to_draft_email, app_id)).id


@celery.task(name="coldcraft.send_email")
def send_email_task(app_id: str, recipient: str, subject: str, body: str) -> str:
    async def go(db, *a):
        return await email_service.send_application_email(db, *a)
    return _run(_with_session(go, app_id, recipient, subject, body)).id


@celery.task(name="coldcraft.send_followup")
def send_followup_task(followup_id: str) -> str:
    return _run(_with_session(followup_service.send_followup, followup_id)).id


@celery.task(name="coldcraft.check_due_followups")
def check_due_followups() -> None:
    """Beat-driven: Scheduler → FOLLOW_UP_DUE → (optionally) worker sends."""
    return _run(_with_session(followup_service.run_scheduler_tick))


@celery.task(name="coldcraft.check_replies")
def check_replies() -> list[str]:
    return _run(_with_session(followup_service.check_replies))
