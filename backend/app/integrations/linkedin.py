"""Fetches a public job page (LinkedIn, Naukri, Indeed, career pages) as plain text.
Parsing the text into a structured job is the AI layer's job (app.ai.extractor)."""
import logging

from app.core.errors import BadRequestError
from app.integrations import web

logger = logging.getLogger(__name__)

_JOB_WORDS = ("responsibilit", "qualification", "requirement", "experience",
              "skills", "apply", "about the job", "about the role")
_WALL_WORDS = ("sign in", "log in", "join now", "authwall",
               "create your free account", "verify you are human", "enable javascript")


def looks_like_login_wall(text: str) -> bool:
    """True when the fetched page is a sign-in / bot-check page rather than a job posting."""
    t = text.lower()
    has_job = sum(w in t for w in _JOB_WORDS)
    has_wall = any(w in t for w in _WALL_WORDS)
    return has_job < 2 and (has_wall or len(t) < 600)


async def fetch_job_page_text(
    url: str,
    max_chars: int | None = None,
) -> tuple[str, str]:
    """Returns (normalized_url, page_text)."""
    url = web.normalize_url(url)
    try:
        web.assert_public_url(url)
    except ValueError as e:
        raise BadRequestError(str(e))
    html = await web.fetch_html(url)
    if not html:
        raise BadRequestError(f"Could not fetch content from: {url}. The site may block automated access — try a screenshot instead.")
    text = web.html_to_text(html)
    if len(text) < 80:
        raise BadRequestError("The page had no readable text (it may require login). Try a screenshot instead.")
    if looks_like_login_wall(text):
        raise BadRequestError(
            "That page looks like a login or bot-check page, not a job posting (LinkedIn does this often). "
            "Open the job, take a screenshot and use the Screenshot tab, or use the company's own careers page URL.")
    return url, text if max_chars is None else text[:max_chars]
