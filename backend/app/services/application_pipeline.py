"""Orchestration only: coordinates services in the right order. No business rules live here."""
import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.extractor import extract_from_screenshot, extract_from_text
from app.core.uploads import validate_image_b64
from app.integrations.linkedin import fetch_job_page_text
from app.models.models import JobApplication
from app.services import application_service, email_service, research_service

logger = logging.getLogger(__name__)


async def process_screenshot(db: AsyncSession, image_base64: str, research: bool = True, force: bool = False) -> JobApplication:
    """screenshot → validate → OCR/extract → save DRAFT → (research → READY)."""
    image_bytes, mime = validate_image_b64(image_base64)
    extraction = await extract_from_screenshot(image_bytes, mime)
    app = await application_service.create_from_job(db, extraction.job, source="screenshot", force=force)
    return await research_service.research_application(db, app.id) if research else app


async def process_job_url(db: AsyncSession, url: str, research: bool = True, force: bool = False) -> JobApplication:
    """URL → fetch → extract → save DRAFT → (research → READY)."""
    if not force:   # cheap URL check first so a duplicate costs no fetch and no AI call
        await application_service.raise_if_duplicate(db, None, None, url)
    normalized, text = await fetch_job_page_text(url)
    extraction = await extract_from_text(text)
    app = await application_service.create_from_job(db, extraction.job, source="linkedin_url",
                                                      linkedin_job_url=normalized, force=force)
    return await research_service.research_application(db, app.id) if research else app


async def capture_to_draft_email(db: AsyncSession, app_id: str) -> JobApplication:
    """Existing DRAFT/READY application → researched → email written. Used by background tasks."""
    app = await research_service.research_application(db, app_id)
    return await email_service.generate_email(db, app.id)
