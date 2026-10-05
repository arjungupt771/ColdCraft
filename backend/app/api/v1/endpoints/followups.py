from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.schemas.schemas import FollowUpOut, ScheduleFollowUpRequest
from app.services import followup_service

router = APIRouter(prefix="/followups")


@router.post("/schedule", response_model=FollowUpOut)
async def schedule(body: ScheduleFollowUpRequest, db: AsyncSession = Depends(get_db)):
    return await followup_service.schedule_followup(db, body.application_id, body.days_after_send, body.custom_note)


@router.get("/due", response_model=list[FollowUpOut])
async def due(db: AsyncSession = Depends(get_db)):
    return await followup_service.get_due_followups(db)


@router.post("/check-due", response_model=list[FollowUpOut])
async def check_due(db: AsyncSession = Depends(get_db)):
    """Runs the scheduler's due-check on demand (marks applications FOLLOW_UP_DUE)."""
    return await followup_service.check_due(db)


@router.get("/{app_id}", response_model=list[FollowUpOut])
async def for_application(app_id: str, db: AsyncSession = Depends(get_db)):
    return await followup_service.list_for_application(db, app_id)


@router.post("/{followup_id}/send", response_model=FollowUpOut)
async def send(followup_id: str, db: AsyncSession = Depends(get_db)):
    return await followup_service.send_followup(db, followup_id)


@router.post("/{followup_id}/cancel")
async def cancel(followup_id: str, db: AsyncSession = Depends(get_db)):
    ok = await followup_service.cancel_followup(db, followup_id)
    return {"status": "cancelled" if ok else "not found"}
