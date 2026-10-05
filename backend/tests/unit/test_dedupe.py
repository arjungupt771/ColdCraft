"""Item 8: duplicate applications are caught before any AI cost, and can be overridden deliberately."""
import pytest

from app.ai.schemas import ExtractedJob
from app.core.errors import ConflictError, DuplicateApplicationError
from app.schemas.schemas import JobUpdate
from app.services import application_pipeline as pipeline, application_service as svc
from app.services.dedupe import job_url_key, norm_company


@pytest.mark.parametrize("a,b", [
    ("https://www.linkedin.com/jobs/view/3812345678/?trackingId=abc&refId=x", "linkedin.com/jobs/view/3812345678"),
    ("https://linkedin.com/jobs/view/senior-engineer-at-acme-3812345678", "https://www.linkedin.com/jobs/view/3812345678"),
    ("https://linkedin.com/jobs/collections/?currentJobId=3812345678", "https://linkedin.com/jobs/view/3812345678"),
    ("https://careers.acme.com/job/42/?utm_source=x#apply", "http://careers.acme.com/job/42"),
    ("https://www.accenture.com/jobdetails?id=14750155_en&src=a", "https://accenture.com/jobdetails?src=b&id=14750155_en"),
])
def test_same_job_same_key(a, b):
    assert job_url_key(a) == job_url_key(b) is not None


def test_different_jobs_different_keys():
    assert job_url_key("https://accenture.com/jobdetails?id=1") != job_url_key("https://accenture.com/jobdetails?id=2")
    assert job_url_key("https://linkedin.com/jobs/view/3812345678") != job_url_key("https://linkedin.com/jobs/view/3812345679")
    assert job_url_key("") is None and job_url_key(None) is None


def test_company_suffixes_ignored():
    assert norm_company("Acme Pvt. Ltd.") == norm_company("ACME") == "acme"


def job(company="Acme", role="Backend Engineer"):
    return ExtractedJob(company_name=company, role_title=role, jd_text="Build APIs")


async def test_same_url_is_a_duplicate_even_with_different_text(db, make_app):
    await make_app("READY", linkedin_job_url="https://linkedin.com/jobs/view/3812345678")
    with pytest.raises(DuplicateApplicationError) as e:
        await svc.create_from_job(db, job("Other Co", "Other Role"), "linkedin_url", "https://www.linkedin.com/jobs/view/3812345678?x=1")
    assert e.value.extra["code"] == "duplicate_application" and e.value.extra["existing_id"]


async def test_same_company_and_role_is_a_duplicate(db, make_app):
    await make_app("SENT", company_name="Acme Inc.", role_title="Backend  Engineer")
    with pytest.raises(DuplicateApplicationError, match="SENT"):
        await svc.create_from_job(db, job("acme", "backend engineer"), "screenshot")


async def test_different_role_or_company_is_fine(db, make_app):
    await make_app("READY")
    await svc.create_from_job(db, job(role="Frontend Engineer"), "screenshot")
    await svc.create_from_job(db, job(company="Globex"), "screenshot")


@pytest.mark.parametrize("status", ["REJECTED", "WITHDRAWN"])
async def test_closed_applications_do_not_block_reapplying(db, make_app, status):
    await make_app(status)
    assert (await svc.create_from_job(db, job(), "screenshot")).status == "DRAFT"


async def test_force_overrides(db, make_app):
    await make_app("READY")
    assert (await svc.create_from_job(db, job(), "screenshot", force=True)).id


async def test_url_duplicate_stops_before_fetch_and_ai(db, fake_ai, fake_web, make_app, monkeypatch):
    await make_app("READY", linkedin_job_url="https://linkedin.com/jobs/view/3812345678")
    fetched = []

    async def spy(url, max_chars=4000):
        fetched.append(url)
        return url, "text"
    monkeypatch.setattr(pipeline, "fetch_job_page_text", spy)
    with pytest.raises(DuplicateApplicationError):
        await pipeline.process_job_url(db, "linkedin.com/jobs/view/3812345678?trk=1")
    assert fetched == [] and fake_ai.calls == []                         # no network, no tokens spent


async def test_pipeline_catches_same_role_found_at_a_new_url(db, fake_ai, fake_web, make_app):
    await make_app("READY", company_name="Acme", role_title="Backend Engineer", linkedin_job_url="https://acme.com/old")
    with pytest.raises(DuplicateApplicationError):
        await pipeline.process_job_url(db, "https://acme.com/new-posting")      # extraction yields Acme / Backend Engineer
    assert (await pipeline.process_job_url(db, "https://acme.com/new-posting", research=False, force=True)).status == "DRAFT"


# ── edit / confirm step ──
async def test_edit_job_details_in_draft(db, make_app):
    app = await make_app("DRAFT")
    app = await svc.update_job_details(db, app.id, JobUpdate(role_title="Staff Engineer", required_skills=["Go"], recipient_email="hr@acme.com"))
    assert (app.role_title, app.required_skills, app.recipient_email, app.recipient_source) == ("Staff Engineer", ["Go"], "hr@acme.com", "user")


@pytest.mark.parametrize("status", ["READY", "SENT"])
async def test_job_details_locked_after_research(db, make_app, status):
    app = await make_app(status)
    with pytest.raises(ConflictError, match="before research"):
        await svc.update_job_details(db, app.id, JobUpdate(role_title="X"))


async def test_edit_that_creates_a_duplicate_is_rejected(db, make_app):
    await make_app("READY", company_name="Acme", role_title="Backend Engineer")
    draft = await make_app("DRAFT", company_name="Acme", role_title="Something Else")
    with pytest.raises(DuplicateApplicationError):
        await svc.update_job_details(db, draft.id, JobUpdate(role_title="Backend Engineer"))
    assert (await svc.update_job_details(db, draft.id, JobUpdate(jd_text="New JD"))).jd_text == "New JD"   # itself is not a dup
