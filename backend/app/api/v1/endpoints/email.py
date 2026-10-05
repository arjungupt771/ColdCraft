from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.schemas.schemas import ApplicationOut, GenerateEmailRequest, SendEmailRequest
from app.services import email_service

router = APIRouter()


@router.post("/generate-email", response_model=ApplicationOut)
async def generate_email(body: GenerateEmailRequest, db: AsyncSession = Depends(get_db)):
    return await email_service.generate_email(db, body.application_id)


@router.post("/send-email", response_model=ApplicationOut)
async def send_email(body: SendEmailRequest, db: AsyncSession = Depends(get_db)):
    return await email_service.send_application_email(db, body.application_id, body.recipient_email, body.subject, body.body,
                                                   confirm_unverified=body.confirm_unverified)
