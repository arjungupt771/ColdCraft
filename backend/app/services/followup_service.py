"""Follow-up scheduling and the due/send/cancel lifecycle.

Application state flow:  SENT → FOLLOW_UP_DUE → FOLLOW_UP_SENT → (FOLLOW_UP_DUE → …) → REPLIED
"""
import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.composer import compose_followup
from app.core.config import settings
from app.core.errors import AppError, BadRequestError, ConflictError, GmailSendError, NotFoundError
from app.domain.state_machine import ApplicationStatus as S, AWAITING_REPLY, can_transition, transition
from app.integrations import gmail
from app.models.models import FollowUp, JobApplication
from app.services import profile_service
from app.services.application_service import get_application

logger = logging.getLogger(__name__)
MAX_FOLLOWUPS = 3
ACTIVE = ("pending", "sending")
STUCK_SENDING_MINUTES = 10


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _aware(dt: Optional[datetime]) -> Optional[datetime]:
    """SQLite hands back naive datetimes; everything we store is UTC."""
    return dt if dt is None or dt.tzinfo else dt.replace(tzinfo=timezone.utc)


async def _numbered(db: AsyncSession, app_id: str) -> list[FollowUp]:
    """Follow-ups that count toward numbering and the cap (cancelled ones don't)."""
    rows = await db.execute(select(FollowUp).where(FollowUp.application_id == app_id, FollowUp.status != "cancelled"))
    return list(rows.scalars().all())


async def schedule_followup(db: AsyncSession, application_id: str, days_after_send: int = 5,
                            custom_note: Optional[str] = None) -> FollowUp:
    app = await get_application(db, application_id)
    if S(app.status) not in AWAITING_REPLY:
        raise BadRequestError("Can only schedule a follow-up for a sent application that hasn't had a reply")
    profile = await profile_service.require_complete_profile(db)

    existing = await _numbered(db, application_id)
    if any(f.status in ACTIVE for f in existing):
        raise ConflictError("A follow-up is already scheduled for this application. Cancel it first to schedule another.")
    seq = max((f.sequence_number for f in existing), default=0) + 1
    if seq > MAX_FOLLOWUPS:
        raise ConflictError(f"Maximum of {MAX_FOLLOWUPS} follow-ups reached for this application")

    base = _aware(app.sent_at) or utcnow()
    # A follow-up after the 1st is spaced from now, not from the original send.
    anchor = base if seq == 1 else max(base, utcnow())
    scheduled_at = anchor + timedelta(days=days_after_send)

    email = await compose_followup(
        company_name=app.company_name, role_title=app.role_title, original_sent_at=base.strftime("%B %d, %Y"),
        user_name=profile.name, user_email=profile.email, sequence_number=seq,
        custom_note=custom_note, recipient_name=app.recipient_name)

    followup = FollowUp(application_id=application_id, scheduled_at=scheduled_at, subject=email.subject,
                        body=email.body, status="pending", sequence_number=seq, prompt_version=email.prompt_version)
    db.add(followup)
    app.followup_scheduled_at = scheduled_at
    try:
        await db.commit()
    except IntegrityError:                       # lost a race against another schedule request
        await db.rollback()
        raise ConflictError("A follow-up is already scheduled for this application.")
    await db.refresh(followup)
    return followup


async def list_for_application(db: AsyncSession, app_id: str) -> list[FollowUp]:
    result = await db.execute(select(FollowUp).where(FollowUp.application_id == app_id).order_by(FollowUp.sequence_number))
    return list(result.scalars().all())


async def get_due_followups(db: AsyncSession) -> list[FollowUp]:
    result = await db.execute(
        select(FollowUp).where(FollowUp.status == "pending", FollowUp.scheduled_at <= utcnow()).order_by(FollowUp.scheduled_at))
    return list(result.scalars().all())


async def check_due(db: AsyncSession) -> list[FollowUp]:
    """Scheduler entry point: moves applications with due follow-ups to FOLLOW_UP_DUE."""
    due = await get_due_followups(db)
    for fu in due:
        app = await db.get(JobApplication, fu.application_id)
        if app and S(app.status) in (S.SENT, S.FOLLOW_UP_SENT):
            transition(app, S.FOLLOW_UP_DUE)
            logger.info("Follow-up #%s due for %s", fu.sequence_number, app.company_name)
    await db.commit()
    return due


async def send_followup(db: AsyncSession, followup_id: str) -> FollowUp:
    followup = await db.get(FollowUp, followup_id)
    if not followup:
        raise NotFoundError("Follow-up not found")
    if followup.status != "pending":
        raise ConflictError(f"Follow-up is already {followup.status}")
    app = await get_application(db, followup.application_id)
    if S(app.status) not in AWAITING_REPLY:
        raise ConflictError(f"Application is {app.status}; follow-up no longer applies")
    if not app.recipient_email:
        raise BadRequestError("Application has no recipient email")
    profile = await profile_service.get_profile(db)
    token = profile_service.get_gmail_token(profile)

    claim = await db.execute(update(FollowUp).where(FollowUp.id == followup_id, FollowUp.status == "pending")
                             .values(status="sending", sent_at=utcnow()))   # sent_at doubles as the claim time
    await db.commit()
    if claim.rowcount != 1:                      # double click / concurrent worker: someone else has it
        raise ConflictError("Follow-up is already being sent")
    subject, body, to, thread = followup.subject or "", followup.body or "", app.recipient_email, app.gmail_thread_id or None
    try:
        # Reply inside the original thread so the recruiter sees the whole conversation.
        await asyncio.to_thread(gmail.send_email, token, to, subject, body, thread)
    except Exception as e:
        err = e if isinstance(e, AppError) else GmailSendError(ambiguous=True)
        await db.rollback()
        await db.execute(update(FollowUp).where(FollowUp.id == followup_id).values(status="pending", sent_at=None))
        await db.commit()
        raise err from e

    followup = await db.get(FollowUp, followup_id, populate_existing=True)
    app = await get_application(db, followup.application_id)
    now = utcnow()
    followup.status, followup.sent_at = "sent", now
    app.followup_sent_at = now
    app.followup_count = (app.followup_count or 0) + 1
    if S(app.status) != S.FOLLOW_UP_DUE:
        transition(app, S.FOLLOW_UP_DUE)       # explicit lifecycle: (SENT|FOLLOW_UP_SENT) → DUE → FOLLOW_UP_SENT
    transition(app, S.FOLLOW_UP_SENT)
    await db.commit()
    await db.refresh(followup)
    return followup


async def cancel_followup(db: AsyncSession, followup_id: str) -> bool:
    followup = await db.get(FollowUp, followup_id)
    if followup and followup.status == "pending":
        followup.status = "cancelled"
        await db.commit()
        return True
    return False


async def cancel_pending(db: AsyncSession, application_id: str) -> int:
    rows = await db.execute(select(FollowUp).where(FollowUp.application_id == application_id, FollowUp.status == "pending"))
    items = list(rows.scalars().all())
    for fu in items:
        fu.status = "cancelled"
    return len(items)


async def mark_replied(db: AsyncSession, application_id: str) -> JobApplication:
    app = await get_application(db, application_id)
    transition(app, S.REPLIED)
    app.reply_received = True
    app.reply_received_at = utcnow()
    await cancel_pending(db, application_id)
    await db.commit()
    await db.refresh(app)
    return app


async def check_replies(db: AsyncSession) -> list[str]:
    """Poll Gmail threads of applications awaiting a reply; mark the ones that got one."""
    profile = await profile_service.get_profile(db)
    if not profile or not profile.gmail_token_enc:
        return []
    token = profile_service.get_gmail_token(profile)
    rows = await db.execute(select(JobApplication).where(
        JobApplication.status.in_([s.value for s in AWAITING_REPLY]), JobApplication.gmail_thread_id.isnot(None)))
    replied: list[str] = []
    for app in rows.scalars().all():
        try:
            if await asyncio.to_thread(gmail.thread_has_reply, token, app.gmail_thread_id, profile.email or ""):
                await mark_replied(db, app.id)
                replied.append(app.id)
        except Exception as e:
            logger.warning("Reply check failed for %s: %s", app.id, e)
    return replied


async def auto_send_due(db: AsyncSession) -> int:
    sent = 0
    for fu in await get_due_followups(db):
        try:
            await send_followup(db, fu.id)
            sent += 1
        except Exception as e:
            logger.warning("Auto-send of follow-up %s failed: %s", fu.id, e)
            await db.rollback()
    return sent


async def recover_stuck_followups(db: AsyncSession) -> int:
    """A crash mid-send leaves 'sending' behind. We can't tell if it went out, so mark it failed
    (never auto-retried → no duplicate) and free the application to schedule a new one."""
    cutoff = utcnow() - timedelta(minutes=STUCK_SENDING_MINUTES)
    result = await db.execute(update(FollowUp).where(FollowUp.status == "sending", FollowUp.sent_at < cutoff)
                              .values(status="failed"))
    await db.commit()
    return result.rowcount or 0


async def run_scheduler_tick(db: AsyncSession) -> None:
    """One scheduler pass (in-process loop and Celery beat both call this).
    Sending is OFF by default: due follow-ups are only *flagged* unless FOLLOWUP_AUTO_SEND=true."""
    from app.services import application_service
    await application_service.recover_stuck_sending(db)
    await recover_stuck_followups(db)
    await check_due(db)
    if settings.FOLLOWUP_AUTO_SEND:
        await auto_send_due(db)
