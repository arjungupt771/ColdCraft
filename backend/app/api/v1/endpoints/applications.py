from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.schemas.schemas import ApplicationOut, DraftUpdate, JobUpdate, StatusUpdate
from app.services import application_service, followup_service

router = APIRouter(prefix="/applications")


@router.get("", response_model=list[ApplicationOut])
async def list_applications(db: AsyncSession = Depends(get_db)):
    return await application_service.list_applications(db)


@router.get("/{app_id}", response_model=ApplicationOut)
async def get_application(app_id: str, db: AsyncSession = Depends(get_db)):
    return await application_service.get_application(db, app_id)


@router.put("/{app_id}", response_model=ApplicationOut)
async def update_job_details(app_id: str, body: JobUpdate, db: AsyncSession = Depends(get_db)):
    """Edit the extracted job (DRAFT only) before research and email generation."""
    return await application_service.update_job_details(db, app_id, body)


@router.put("/{app_id}/email", response_model=ApplicationOut)
async def update_email_draft(app_id: str, body: DraftUpdate, db: AsyncSession = Depends(get_db)):
    return await application_service.update_draft(db, app_id, body)


@router.put("/{app_id}/status", response_model=ApplicationOut)
async def update_status(app_id: str, body: StatusUpdate, db: AsyncSession = Depends(get_db)):
    return await application_service.set_status(db, app_id, body.status)


@router.post("/{app_id}/mark-replied", response_model=ApplicationOut)
async def mark_replied(app_id: str, db: AsyncSession = Depends(get_db)):
    return await followup_service.mark_replied(db, app_id)


@router.delete("/{app_id}", status_code=204)
async def delete_application(app_id: str, db: AsyncSession = Depends(get_db)):
    await application_service.delete_application(db, app_id)
