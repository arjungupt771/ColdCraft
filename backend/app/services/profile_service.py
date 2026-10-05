import asyncio
import logging
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import BadRequestError, GmailNotConnectedError
from app.core.security import decrypt_json, encrypt_json
from app.integrations import gmail
from app.models.models import UserProfile
from app.schemas.schemas import ProfileOut, ProfileUpdate

logger = logging.getLogger(__name__)


async def get_profile(db: AsyncSession) -> Optional[UserProfile]:
    return (await db.execute(select(UserProfile))).scalars().first()


async def get_or_create_profile(db: AsyncSession) -> UserProfile:
    profile = await get_profile(db)
    if not profile:
        profile = UserProfile()
        db.add(profile)
        await db.commit()
        await db.refresh(profile)
    return profile


async def update_profile(db: AsyncSession, data: ProfileUpdate) -> UserProfile:
    profile = await get_or_create_profile(db)
    for field, value in data.model_dump(exclude_none=True).items():
        setattr(profile, field, value)
    await db.commit()
    await db.refresh(profile)
    return profile


async def require_complete_profile(db: AsyncSession) -> UserProfile:
    profile = await get_profile(db)
    if not profile or not (profile.name and profile.email):
        raise BadRequestError("Profile not set up. Add your name and email in the Profile tab first.")
    return profile


def to_out(profile: UserProfile) -> ProfileOut:
    return ProfileOut(
        id=profile.id, name=profile.name or "", email=profile.email or "", phone=profile.phone or "",
        linkedin=profile.linkedin or "", resume_text=profile.resume_text or "", skills=profile.skills or [],
        experience_years=profile.experience_years or 0, tone=profile.tone or "professional",
        gmail_connected=bool(profile.gmail_token_enc))


# ── Gmail credentials (encrypted at rest) ─────────────
def get_gmail_token(profile: Optional[UserProfile]) -> dict:
    if not profile or not profile.gmail_token_enc:
        raise GmailNotConnectedError()
    try:
        return decrypt_json(profile.gmail_token_enc)
    except ValueError as e:
        raise BadRequestError(str(e))


async def connect_gmail(db: AsyncSession, code: str) -> Optional[str]:
    token = await asyncio.to_thread(gmail.exchange_code, code)
    profile = await get_or_create_profile(db)
    profile.gmail_token_enc = encrypt_json(token)
    email = await asyncio.to_thread(gmail.get_user_email, token)
    if email and not profile.email:
        profile.email = email
    await db.commit()
    return email


async def gmail_status(db: AsyncSession) -> tuple[bool, Optional[str]]:
    profile = await get_profile(db)
    if not profile or not profile.gmail_token_enc:
        return False, None
    try:
        token = get_gmail_token(profile)
    except BadRequestError:
        return False, None
    return True, await asyncio.to_thread(gmail.get_user_email, token)


async def disconnect_gmail(db: AsyncSession) -> None:
    profile = await get_profile(db)
    if profile:
        profile.gmail_token_enc = None
        await db.commit()
