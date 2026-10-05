import asyncio
import logging
from datetime import datetime, timezone

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.composer import compose_email
from app.ai.errors import AIError
from app.core.errors import (
    AppError, ConflictError, GmailSendError, SendInProgressError, UnverifiedRecipientError,
)
from app.domain.state_machine import ApplicationStatus as S, transition
from app.integrations import gmail
from app.models.models import JobApplication
from app.services import profile_service, research_service
from app.services.application_service import get_application

logger = logging.getLogger(__name__)


async def _record_failure(db: AsyncSession, app_id: str, message: str) -> None:
    """Persist the error without touching anything else (the caller re-raises afterwards)."""
    await db.rollback()
    await db.execute(update(JobApplication).where(JobApplication.id == app_id).values(last_error=message[:500]))
    await db.commit()


async def generate_email(db: AsyncSession, app_id: str) -> JobApplication:
    """DRAFT → (research) → generate → validate → save → READY.

    The draft is saved only after the output passes validation, via a guarded UPDATE, so a failed
    or raced generation can never leave a half-written or overwritten email behind.
    """
    app = await get_application(db, app_id)
    if app.status == S.DRAFT.value:
        app = await research_service.research_application(db, app_id)     # DRAFT → RESEARCHING → READY
    if app.status != S.READY.value:
        raise ConflictError(f"Cannot write an email while the application is {app.status}")
    profile = await profile_service.require_complete_profile(db)
    try:
        email = await compose_email(
            company_name=app.company_name, role_title=app.role_title, jd_text=app.jd_text or "",
            required_skills=app.required_skills or [], company_research=app.company_research or "",
            user_name=profile.name, user_email=profile.email, user_resume=profile.resume_text or "",
            user_skills=profile.skills or [], experience_years=profile.experience_years or 0,
            tone=profile.tone or "professional", recipient_name=app.recipient_name)
    except AIError as e:
        await _record_failure(db, app_id, e.detail)
        raise

    result = await db.execute(
        update(JobApplication).where(JobApplication.id == app_id, JobApplication.status == S.READY.value)
        .values(email_subject=email.subject, email_body=email.body, ai_provider_used=email.provider,
                prompt_version=email.prompt_version, email_confidence=email.confidence, last_error=None))
    if result.rowcount != 1:                     # e.g. a send started while the model was writing
        await db.rollback()
        raise ConflictError("The application changed while the email was being written; nothing was saved.")
    await db.commit()
    return await get_application(db, app_id)


async def _claim_for_sending(db: AsyncSession, app_id: str) -> bool:
    """Atomic READY → SENDING. Exactly one concurrent caller gets True."""
    result = await db.execute(
        update(JobApplication).where(JobApplication.id == app_id, JobApplication.status == S.READY.value)
        .values(status=S.SENDING.value, last_error=None))
    await db.commit()
    return result.rowcount == 1


async def send_application_email(db: AsyncSession, app_id: str, recipient_email: str, subject: str, body: str,
                                 confirm_unverified: bool = False) -> JobApplication:
    app = await get_application(db, app_id)
    if app.status == S.SENDING.value:
        raise SendInProgressError()
    if app.status != S.READY.value:
        raise ConflictError(f"Only READY applications can be sent (status is {app.status})")
    profile = await profile_service.get_profile(db)
    token = profile_service.get_gmail_token(profile)             # fail before claiming if Gmail isn't usable

    recipient = recipient_email.strip()
    unchanged = recipient.lower() == (app.recipient_email or "").lower()
    if app.recipient_source == "guess" and unchanged and not confirm_unverified:
        raise UnverifiedRecipientError(recipient)

    if not await _claim_for_sending(db, app_id):
        raise SendInProgressError()                              # lost the race: someone else is sending
    try:
        msg_id, thread_id = await asyncio.to_thread(gmail.send_email, token, recipient, subject, body)
    except Exception as e:
        err = e if isinstance(e, AppError) else GmailSendError(ambiguous=True)
        await db.rollback()
        await db.execute(update(JobApplication).where(JobApplication.id == app_id)
                         .values(status=S.READY.value, last_error=err.detail[:500]))
        await db.commit()
        raise err from e

    app = await get_application(db, app_id)
    app.recipient_email = recipient
    if not unchanged:
        app.recipient_source = "user"
    app.email_subject, app.email_body = subject, body
    app.gmail_message_id, app.gmail_thread_id = msg_id, thread_id
    app.sent_at = datetime.now(timezone.utc)
    app.last_error = None
    transition(app, S.SENT)                                      # SENDING → SENT
    await db.commit()
    await db.refresh(app)
    return app
