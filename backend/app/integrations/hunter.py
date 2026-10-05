import logging
import re
from typing import Optional

import httpx

from app.ai.schemas import RecruiterInfo
from app.core.config import settings

logger = logging.getLogger(__name__)
HR_KEYWORDS = ("hr", "talent", "recruit", "people")


async def find_recruiter(company_name: str, company_website: Optional[str] = None) -> Optional[RecruiterInfo]:
    """Hunter.io lookup when configured; otherwise a clearly-flagged careers@ guess."""
    domain = extract_domain(company_website) if company_website else guess_domain(company_name)
    if not domain:
        return None
    if settings.HUNTER_API_KEY:
        found = await _hunter_search(domain)
        if found:
            return found
    try:
        return RecruiterInfo(email=f"careers@{domain}", source="guess", verified=False)
    except ValueError:
        return None


async def _hunter_search(domain: str) -> Optional[RecruiterInfo]:
    try:
        async with httpx.AsyncClient(timeout=8.0) as c:
            r = await c.get("https://api.hunter.io/v2/domain-search",
                            params={"domain": domain, "api_key": settings.HUNTER_API_KEY, "department": "hr", "limit": 5})
        r.raise_for_status()
        emails = r.json().get("data", {}).get("emails", [])
    except Exception as e:
        logger.warning("Hunter.io error: %s", e)
        return None
    ranked = sorted(emails, key=lambda e: not any(k in ((e.get("department") or "") + (e.get("position") or "")).lower() for k in HR_KEYWORDS))
    for e in ranked:
        try:
            name = " ".join(x for x in (e.get("first_name"), e.get("last_name")) if x) or None
            return RecruiterInfo(email=e["value"], name=name, source="hunter",
                                 verified=(e.get("verification") or {}).get("status") == "valid")
        except (KeyError, ValueError):
            continue
    return None


def extract_domain(url: str) -> Optional[str]:
    m = re.search(r"(?:https?://)?(?:www\.)?([^/\s:?#]+)", url or "")
    return m.group(1).lower() if m else None


def guess_domain(company_name: str) -> Optional[str]:
    slug = re.sub(r"[^a-z0-9]", "", (company_name or "").lower())
    return f"{slug}.com" if slug else None
