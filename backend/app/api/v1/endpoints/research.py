from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.schemas.schemas import ApplicationOut, ProcessLinkedInRequest, ProcessScreenshotRequest
from app.services import application_pipeline, research_service

router = APIRouter()


@router.post("/process-screenshot", response_model=ApplicationOut)
async def process_screenshot(body: ProcessScreenshotRequest, research: bool = True, force: bool = False, db: AsyncSession = Depends(get_db)):
    """`research=false` only extracts the job (status DRAFT); call /applications/{id}/research next."""
    return await application_pipeline.process_screenshot(db, body.image_base64, research=research, force=force)


@router.post("/process-linkedin", response_model=ApplicationOut)
async def process_linkedin(body: ProcessLinkedInRequest, research: bool = True, force: bool = False, db: AsyncSession = Depends(get_db)):
    return await application_pipeline.process_job_url(db, body.url, research=research, force=force)


@router.post("/applications/{app_id}/research", response_model=ApplicationOut)
async def research_application(app_id: str, db: AsyncSession = Depends(get_db)):
    """(Re-)runs company research + recruiter lookup. Also the retry path after a failed research."""
    return await research_service.research_application(db, app_id)
