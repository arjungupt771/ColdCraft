import json

import pytest

from app.ai import client as ai_client_module
from app.ai.errors import AIInvalidResponseError, AINotConfiguredError
from app.ai.extractor import (
    _prepare_page_text,
    extract_from_screenshot,
    extract_from_text,
)
from app.ai.schemas import ExtractedJob
from tests.conftest import JOB, FakeProvider, make_client


def use(handler, **kw):
    p = FakeProvider(handler, **kw)
    ai_client_module.set_client(make_client(p))
    return p


@pytest.fixture(autouse=True)
def _reset():
    yield
    ai_client_module.set_client(None)


async def test_extract_from_text(fake_ai):
    ex = await extract_from_text("Backend Engineer at Acme " * 10)
    assert ex.job.company_name == "Acme" and ex.job.required_skills == ["Python", "FastAPI"]
    assert ex.prompt_version == "job_extraction@v1" and ex.provider == "fake"


def test_prepare_page_text_cleans_and_preserves_both_ends():
    prepared = _prepare_page_text(
        "Top\tcontent\r\n\r\n\r\n" + "middle " * 3000 + "Bottom"
    )

    assert prepared.startswith("Top content\n\n")
    assert "[... middle of page omitted ...]" in prepared
    assert prepared.endswith("Bottom")


async def test_extract_from_screenshot_uses_vision(fake_ai):
    ex = await extract_from_screenshot(b"\x89PNG", "image/png")
    assert ex.job.role_title == "Backend Engineer" and fake_ai.calls[0][0] == "vision"
    assert ex.prompt_version == "job_extraction_vision@v1"


async def test_unknown_company_is_not_saved(db):
    use(lambda p, s: json.dumps(dict(JOB, company_name="Unknown")))
    job = (await extract_from_text("page text")).job
    assert job.company_name is None                      # extraction may be incomplete...
    from app.core.errors import UnprocessableError
    from app.services.application_service import create_from_job
    with pytest.raises(UnprocessableError, match="company name"):    # ...but it is never saved (422, not 500)
        await create_from_job(db, job, "linkedin_url")


async def test_messy_fields_are_normalised():
    use(lambda p, s: "```json\n" + json.dumps(dict(JOB, required_skills="Python, Go;Rust", recipient_name="N/A",
                                                  company_website="null")) + "\n```")
    job = (await extract_from_text("x")).job
    assert job.required_skills == ["Python", "Go", "Rust"] and job.recipient_name is None and job.company_website is None


async def test_vision_requires_vision_provider():
    use(lambda p, s: json.dumps(JOB), vision=False)
    with pytest.raises(AINotConfiguredError):
        await extract_from_screenshot(b"img")


def test_schema_truncates_oversized_fields():
    job = ExtractedJob(company_name="A" * 500, role_title="R", jd_text="x" * 50000, required_skills=["s"] * 100)
    assert len(job.company_name) == 200 and len(job.jd_text) == 12000 and len(job.required_skills) == 40
