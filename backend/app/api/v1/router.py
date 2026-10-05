from fastapi import APIRouter, Depends

from app.api.v1.endpoints import applications, email, followups, profile, research
from app.core.security import require_api_token

# Everything here requires the API token (when configured).
protected = APIRouter(dependencies=[Depends(require_api_token)])
protected.include_router(profile.router, tags=["profile"])
protected.include_router(research.router, tags=["research"])
protected.include_router(applications.router, tags=["applications"])
protected.include_router(email.router, tags=["email"])
protected.include_router(followups.router, tags=["followups"])

# Public: Google's OAuth redirect cannot send our header; it's guarded by the OAuth `state` instead.
public = APIRouter()
public.include_router(profile.callback_router, tags=["gmail"])

api_router = APIRouter()
api_router.include_router(protected)
api_router.include_router(public)
