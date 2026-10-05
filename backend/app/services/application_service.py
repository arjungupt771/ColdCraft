import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.schemas import ExtractedJob
from app.core.errors import ConflictError, DuplicateApplicationError, IncompleteJobError, NotFoundError
from app.domain.state_machine import ApplicationStatus as S, TERMINAL, transition
from app.models.models import JobApplication
from app.schemas.schemas import DraftUpdate, JobUpdate
from app.services import dedupe

logger = logging.getLogger(__name__)
EDITABLE = {S.DRAFT.value, S.READY.value}
STUCK_SENDING_MINUTES = 10


def validate_extracted_job(job: ExtractedJob) -> None:
    missing = [label for label, value in (("company name", job.company_name), ("role title", job.role_title),
                                          ("job description", job.jd_text)) if not value]
    if missing:
        raise IncompleteJobError(
            "Could not extract required job information: " + ", ".join(missing)
            + ". If this was a login page, try a screenshot or the company's careers-page URL.")


async def get_application(db: AsyncSession, app_id: str) -> JobApplication:
    app = (await db.execute(select(JobApplication).where(JobApplication.id == app_id))).scalar_one_or_none()
    if not app:
        raise NotFoundError("Application not found")
    return app


async def list_applications(db: AsyncSession) -> list[JobApplication]:
    result = await db.execute(select(JobApplication).order_by(JobApplication.created_at.desc()))
    return list(result.scalars().all())


async def find_duplicate(db: AsyncSession, company: Optional[str], role: Optional[str], url: Optional[str],
                         exclude_id: Optional[str] = None) -> Optional[JobApplication]:
    """Rejected/withdrawn applications don't count: re-applying after those is legitimate."""
    rows = await db.execute(select(JobApplication).where(JobApplication.status.notin_([s.value for s in TERMINAL])))
    return next((r for r in rows.scalars() if r.id != exclude_id and dedupe.is_duplicate(r, company, role, url)), None)


async def raise_if_duplicate(db, company, role, url, exclude_id=None) -> None:
    dup = await find_duplicate(db, company, role, url, exclude_id)
    if dup:
        raise DuplicateApplicationError(
            dup.id, f"You already have an application for {dup.role_title} at {dup.company_name} ({dup.status}).")


def _grounded_name(name: Optional[str], jd_text: str) -> Optional[str]:
    """An AI-extracted recruiter name is kept only if it literally appears in the job text."""
    return name if name and name.lower() in (jd_text or "").lower() else None


async def create_from_job(db: AsyncSession, job: ExtractedJob, source: str, linkedin_job_url: Optional[str] = None,
                          force: bool = False) -> JobApplication:
    validate_extracted_job(job)
    if not force:
        await raise_if_duplicate(db, job.company_name, job.role_title, linkedin_job_url)
    app = JobApplication(
        company_name=job.company_name, role_title=job.role_title, jd_text=job.jd_text,
        required_skills=job.required_skills, company_website=job.company_website,
        recipient_name=_grounded_name(job.recipient_name, job.jd_text), source=source,
        linkedin_job_url=linkedin_job_url, status=S.DRAFT.value,
    )
    db.add(app)
    await db.commit()
    await db.refresh(app)
    return app


async def update_job_details(db: AsyncSession, app_id: str, data: JobUpdate) -> JobApplication:
    """The 'edit / confirm' step: fix extraction mistakes before research and email writing."""
    app = await get_application(db, app_id)
    if app.status != S.DRAFT.value:
        raise ConflictError(f"Job details can only be edited before research (status is {app.status})")
    values = data.model_dump(exclude_none=True)
    await raise_if_duplicate(db, values.get("company_name", app.company_name), values.get("role_title", app.role_title),
                             app.linkedin_job_url, exclude_id=app.id)
    for field in ("company_name", "role_title", "jd_text", "required_skills", "company_website", "recipient_name"):
        if field in values:
            setattr(app, field, values[field])
    if "recipient_email" in values:
        app.recipient_email, app.recipient_source = values["recipient_email"], "user"
    await db.commit()
    await db.refresh(app)
    return app


async def update_draft(db: AsyncSession, app_id: str, data: DraftUpdate) -> JobApplication:
    app = await get_application(db, app_id)
    if app.status not in EDITABLE:
        raise ConflictError(f"Cannot edit the draft of an application that is {app.status}")
    values = data.model_dump(exclude_none=True)
    if "subject" in values:
        app.email_subject = values["subject"]
    if "body" in values:
        app.email_body = values["body"]
    if "recipient_email" in values and values["recipient_email"].lower() != (app.recipient_email or "").lower():
        app.recipient_email, app.recipient_source = values["recipient_email"], "user"
    if "notes" in values:
        app.notes = values["notes"]
    await db.commit()
    await db.refresh(app)
    return app


async def set_status(db: AsyncSession, app_id: str, new_status: str) -> JobApplication:
    """Manual outcome changes (interview / rejected / withdrawn). Cancels pending follow-ups."""
    from app.services import followup_service
    app = await get_application(db, app_id)
    transition(app, new_status)
    await followup_service.cancel_pending(db, app.id)
    await db.commit()
    await db.refresh(app)
    return app


async def delete_application(db: AsyncSession, app_id: str) -> None:
    app = await get_application(db, app_id)
    if app.status == S.SENDING.value:
        raise ConflictError("Cannot delete an application while its email is being sent")
    await db.delete(app)
    await db.commit()


async def recover_stuck_sending(db: AsyncSession) -> int:
    """A crash mid-send leaves SENDING behind. We can't know if Gmail got it, so hand it back to the
    user as READY with a warning instead of leaving it stuck (or silently resending)."""
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=STUCK_SENDING_MINUTES)
    result = await db.execute(
        update(JobApplication).where(JobApplication.status == S.SENDING.value, JobApplication.updated_at < cutoff)
        .values(status=S.READY.value,
                last_error="Sending was interrupted. Check your Gmail Sent folder before sending again."))
    await db.commit()
    return result.rowcount or 0
