import json

import pytest

from app.ai.errors import AIAllProvidersFailedError, AIProviderUnavailableError
from app.ai import client as ai_client_module
from app.core.errors import ConflictError, UploadError
from app.models.models import JobApplication
from app.services import application_pipeline as pipeline, email_service, research_service
from tests.conftest import FakeProvider, default_handler, make_client


async def test_url_pipeline_ends_ready_with_research_and_recruiter(db, fake_ai, fake_web):
    app = await pipeline.process_job_url(db, "linkedin.com/jobs/view/1")
    assert app.status == "READY" and app.source == "linkedin_url"
    assert app.linkedin_job_url == "https://linkedin.com/jobs/view/1"
    assert app.company_name == "Acme" and "payment infrastructure" in app.company_research
    assert app.recipient_email == "careers@acme.com"


async def test_research_can_be_deferred(db, fake_ai, fake_web):
    app = await pipeline.process_job_url(db, "https://x.com/job", research=False)
    assert app.status == "DRAFT" and not app.company_research
    app = await research_service.research_application(db, app.id)
    assert app.status == "READY" and app.company_research


async def test_screenshot_pipeline(db, fake_ai, fake_web, png_b64):
    app = await pipeline.process_screenshot(db, png_b64)
    assert app.status == "READY" and app.source == "screenshot" and fake_ai.calls[0][0] == "vision"


async def test_url_rejects_incomplete_extraction_before_saving(db, fake_ai, fake_web):
    fake_ai.handler = lambda prompt, system: json.dumps(
        {"company_name": "Acme", "role_title": None, "jd_text": "Build APIs"}
    )

    with pytest.raises(ValueError, match="role title"):
        await pipeline.process_job_url(db, "https://x.com/job", research=False)

    assert (await db.execute(JobApplication.__table__.select())).first() is None


async def test_screenshot_rejects_incomplete_extraction_before_saving(
    db, fake_ai, fake_web, png_b64
):
    fake_ai.handler = lambda prompt, system: json.dumps(
        {"company_name": "Acme", "role_title": "Backend Engineer", "jd_text": ""}
    )

    with pytest.raises(ValueError, match="job description"):
        await pipeline.process_screenshot(db, png_b64, research=False)

    assert (await db.execute(JobApplication.__table__.select())).first() is None


async def test_invalid_screenshot_never_reaches_ai(db, fake_ai, fake_web):
    with pytest.raises(UploadError):
        await pipeline.process_screenshot(db, "bm90IGFuIGltYWdl" * 20)
    assert fake_ai.calls == []


async def test_research_failure_returns_to_draft_and_is_retryable(db, fake_web, monkeypatch):
    state = {"fail": True}

    def handler(prompt, system):
        if "research assistant" in system.lower() and state["fail"]:
            return AIProviderUnavailableError("research model down", "fake")
        return default_handler(prompt, system)

    ai_client_module.set_client(make_client(FakeProvider(handler)))
    try:
        with pytest.raises(AIAllProvidersFailedError):
            await pipeline.process_job_url(db, "https://x.com/job")
        saved = (await db.execute(JobApplication.__table__.select())).first()
        assert saved.status == "DRAFT" and "AIProviderUnavailableError" in saved.last_error   # not lost, not stuck RESEARCHING

        state["fail"] = False
        app = await research_service.research_application(db, saved.id)
        assert app.status == "READY" and app.last_error is None
    finally:
        ai_client_module.set_client(None)


async def test_capture_to_draft_email(db, fake_ai, fake_web, make_profile):
    await make_profile()
    app = await pipeline.process_job_url(db, "https://x.com/job", research=False)
    app = await pipeline.capture_to_draft_email(db, app.id)
    assert app.status == "READY" and app.email_body and app.prompt_version == "email_generation@v2"


async def test_generate_from_draft_researches_first(db, fake_ai, fake_web, make_profile):
    """DRAFT → research → generate → validate → save → READY, in one call."""
    await make_profile()
    app = await pipeline.process_job_url(db, "https://x.com/job", research=False)
    assert app.status == "DRAFT" and not app.company_research
    app = await email_service.generate_email(db, app.id)
    assert app.status == "READY" and app.company_research and app.email_body
