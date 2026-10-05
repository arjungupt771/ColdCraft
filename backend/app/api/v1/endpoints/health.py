from fastapi import APIRouter
from app.schemas.schemas import HealthOut

router = APIRouter()


@router.get("/health", response_model=HealthOut)
async def health():
    return HealthOut(status="ok", version="2.1.0")
