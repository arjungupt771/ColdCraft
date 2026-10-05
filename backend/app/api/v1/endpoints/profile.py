"""Profile + Gmail connection. The OAuth callback lives on `callback_router` because Google's
redirect can't carry our X-API-Token header."""
import logging

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.integrations import gmail
from app.schemas.schemas import GmailAuthURL, GmailStatus, ProfileOut, ProfileUpdate
from app.services import profile_service

router = APIRouter()
callback_router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/profile", response_model=ProfileOut)
async def get_profile(db: AsyncSession = Depends(get_db)):
    return profile_service.to_out(await profile_service.get_or_create_profile(db))


@router.put("/profile", response_model=ProfileOut)
async def update_profile(body: ProfileUpdate, db: AsyncSession = Depends(get_db)):
    return profile_service.to_out(await profile_service.update_profile(db, body))


@router.get("/gmail/auth-url", response_model=GmailAuthURL)
async def get_gmail_auth_url():
    try:
        return GmailAuthURL(auth_url=gmail.get_auth_url())
    except Exception as e:
        logger.error("Gmail auth URL failed: %s", e)
        raise HTTPException(status_code=500, detail="Gmail OAuth is not configured. Check GMAIL_CLIENT_ID / GMAIL_CLIENT_SECRET.")


@router.get("/gmail/status", response_model=GmailStatus)
async def gmail_status(db: AsyncSession = Depends(get_db)):
    connected, email = await profile_service.gmail_status(db)
    return GmailStatus(connected=connected, email=email)


@router.delete("/gmail/disconnect")
async def disconnect_gmail(db: AsyncSession = Depends(get_db)):
    await profile_service.disconnect_gmail(db)
    return {"status": "disconnected"}


@callback_router.get("/gmail/callback", response_class=HTMLResponse)
async def gmail_callback(code: str, state: str = "", db: AsyncSession = Depends(get_db)):
    if not gmail.consume_state(state):
        raise HTTPException(status_code=400, detail="Invalid or expired OAuth state. Start the connection again from ColdCraft.")
    try:
        email = await profile_service.connect_gmail(db, code)
    except Exception as e:
        logger.error("Gmail connect failed: %s", e)
        raise HTTPException(status_code=500, detail="Could not connect Gmail")
    return HTMLResponse(f"<html><body style='font-family:sans-serif;padding:2rem'><h2>Gmail connected ✓</h2>"
                        f"<p>{email or ''}</p><p>You can close this tab and return to ColdCraft.</p></body></html>")
