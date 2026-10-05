import logging
import re

from app.core.errors import UnprocessableError
from dataclasses import dataclass

from app.ai.client import get_client
from app.ai.prompts import load_prompt
from app.ai.schemas import ExtractedJob

logger = logging.getLogger(__name__)


@dataclass
class Extraction:
    job: ExtractedJob
    provider: str
    prompt_version: str


_MAX_TEXT_LENGTH = 12000


def _clean_page_text(page_text: str) -> str:
    if not page_text:
        return ""

    text = page_text.replace("\x00", " ")
    text = text.replace("\r\n", "\n").replace("\r", "\n")

    # Collapse excessive horizontal whitespace.
    text = re.sub(r"[ \t]+", " ", text)

    # Collapse excessive blank lines.
    text = re.sub(r"\n{3,}", "\n\n", text)

    return text.strip()


def _prepare_page_text(page_text: str) -> str:
    text = _clean_page_text(page_text)

    if not text:
        return ""

    if len(text) <= _MAX_TEXT_LENGTH:
        return text

    # Keep both beginning and end because job title/company
    # information can occur in either location.
    head_size = 7000
    tail_size = _MAX_TEXT_LENGTH - head_size

    return (
        text[:head_size]
        + "\n\n[... middle of page omitted ...]\n\n"
        + text[-tail_size:]
    )


async def extract_from_screenshot(
    image_bytes: bytes,
    mime_type: str = "image/png",
) -> Extraction:

    prompt = load_prompt("job_extraction_vision")
    system, user = prompt.render()

    job, provider = await get_client().vision_json(
        image_bytes,
        mime_type,
        user,
        ExtractedJob,
        system=system,
    )

    return Extraction(
        job=job,
        provider=provider,
        prompt_version=prompt.tag,
    )


async def extract_from_text(page_text: str) -> Extraction:
    """Parse fetched job-posting text into structured job data."""

    prepared_text = _prepare_page_text(page_text)

    if not prepared_text:
        raise UnprocessableError("No usable webpage content was available for extraction.")

    prompt = load_prompt("job_extraction")

    system, user = prompt.render(
        content=prepared_text,
    )

    logger.info(
        "Extracting job information from %d characters of page text",
        len(prepared_text),
    )

    job, provider = await get_client().complete_json(
        user,
        ExtractedJob,
        system=system,
        max_tokens=1800,
        temperature=0.1,
    )

    return Extraction(
        job=job,
        provider=provider,
        prompt_version=prompt.tag,
    )