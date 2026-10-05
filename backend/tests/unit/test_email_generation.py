"""Item 3: email generation is grounded in the real JD, validated, and can't corrupt an application."""
import json

import pytest
from sqlalchemy import update

from app.ai import client as ai_client_module
from app.ai.composer import ComposedEmail, compose_email
from app.ai.errors import AIInvalidResponseError, AIProviderUnavailableError
from app.core.errors import ConflictError
from app.models.models import JobApplication
from app.services import email_service
from tests.conftest import EMAIL, EMAIL_BODY, FakeProvider, make_client

KW = dict(company_name="Acme", role_title="Backend Engineer", required_skills=["Python"], company_research="Acme builds payments.",
          user_name="Test User", user_email="test@example.com", user_resume="Built APIs for 2 years.", user_skills=["Python"],
          experience_years=3, jd_text="Scale payment APIs. Kafka and PostgreSQL experience is a plus.")


def use(handler):
    p = FakeProvider(handler)
    ai_client_module.set_client(make_client(p))
    return p


@pytest.fixture(autouse=True)
def _reset():
    yield
    ai_client_module.set_client(None)


def seq(*bodies):
    it = iter(bodies)
    return lambda p, s: json.dumps(dict(EMAIL, body=next(it)))


GOOD = EMAIL_BODY.format(greeting="Dear Hiring Manager,")


async def test_real_job_description_reaches_the_prompt(fake_ai):
    await compose_email(**KW)
    prompt = fake_ai.calls[0][1]
    assert "Kafka and PostgreSQL" in prompt and "JOB DESCRIPTION" in prompt


async def test_no_research_is_stated_explicitly(fake_ai):
    await compose_email(**{**KW, "company_research": ""})
    assert "COMPANY RESEARCH: (none)" in fake_ai.calls[0][1]


async def test_system_prompt_forbids_invented_facts(fake_ai):
    await compose_email(**KW)
    system = fake_ai.calls[0][2]
    assert "Use ONLY facts" in system and "Never invent" in system


@pytest.mark.parametrize("bad,why", [
    (GOOD.replace("Dear Hiring Manager,", "Dear Sarah,"), "must start exactly with"),          # invented recruiter
    (GOOD.replace("test@example.com", "me@else.com"), "must end with"),                       # wrong sign-off
    (GOOD.replace("production traffic", "production traffic and cut latency by 40%"), "invented figures"),
    (GOOD.replace("Backend Engineer", "Backend Engineer. I hope this email finds you well"), "filler"),
    ("Dear Hiring Manager,\n\nToo short.\n\nBest regards,\nTest User\ntest@example.com", "at least 50"),
    (GOOD + " " + "extra words " * 120, "too long"),                                         # schema hard cap
    (GOOD + " " + "extra words " * 88, "under 200"),                                          # rule: 200-word target
    (GOOD.replace("Best regards", "Best regards, [Your Name]"), "placeholders"),
])
async def test_bad_output_is_repaired_with_the_reason(bad, why):
    p = use(seq(bad, GOOD))
    out = await compose_email(**KW)
    assert out.body == GOOD and len(p.calls) == 2
    assert why in p.calls[1][1]                       # the model is told exactly what was wrong


async def test_unrepairable_output_raises(db):
    use(seq(*[GOOD.replace("Dear Hiring Manager,", "Dear Sarah,")] * 2))
    with pytest.raises(AIInvalidResponseError):
        await compose_email(**KW)


async def test_figures_from_the_job_description_or_resume_are_allowed():
    body = GOOD.replace("production traffic", "production traffic for 2 years with Kafka")      # "2 years" is in the resume
    use(seq(body))
    assert (await compose_email(**KW)).body == body


async def test_concise_tone_has_a_tighter_limit():
    long_for_concise = GOOD + " " + "more words here " * 35                  # fine for 200, too long for concise
    p = use(seq(long_for_concise, GOOD))
    await compose_email(**KW, tone="concise")
    assert len(p.calls) == 2 and "under 120" in p.calls[1][1]


async def test_named_recipient_is_used_only_when_given():
    p = use(lambda pr, s: json.dumps(dict(EMAIL, body=EMAIL_BODY.format(greeting="Dear Priya,"))))
    assert (await compose_email(**KW, recipient_name="Priya")).body.startswith("Dear Priya,")


# ── recruiter names are never invented ──
async def test_ai_extracted_recruiter_name_must_appear_in_the_job_text(db):
    from app.ai.schemas import ExtractedJob
    from app.services.application_service import create_from_job
    base = dict(company_name="Acme", role_title="Engineer", jd_text="Apply to Jane Roe, our recruiter.")
    kept = await create_from_job(db, ExtractedJob(**base, recipient_name="Jane Roe"), "linkedin_url")
    dropped = await create_from_job(db, ExtractedJob(**{**base, "role_title": "Other"}, recipient_name="Sarah Invented"), "linkedin_url")
    assert kept.recipient_name == "Jane Roe" and dropped.recipient_name is None


# ── failure must not corrupt the application ──
async def test_provider_failure_leaves_draft_untouched(db, make_profile, make_app):
    await make_profile()
    app = await make_app("READY", email_subject="Keep subject", email_body="Keep body", prompt_version="email_generation@v1")
    use(lambda p, s: AIProviderUnavailableError("down", "fake"))
    with pytest.raises(Exception):
        await email_service.generate_email(db, app.id)
    await db.refresh(app)
    assert (app.status, app.email_subject, app.email_body, app.prompt_version) == ("READY", "Keep subject", "Keep body", "email_generation@v1")
    assert "fake: AIProviderUnavailableError" in app.last_error or "failed" in app.last_error


async def test_success_clears_the_previous_error(db, make_profile, make_app, fake_ai):
    await make_profile()
    app = await make_app("READY", last_error="old failure")
    app = await email_service.generate_email(db, app.id)
    assert app.last_error is None and app.email_confidence == 0.9


async def test_generation_that_races_a_send_saves_nothing(db, make_profile, make_app, monkeypatch):
    await make_profile()
    app = await make_app("READY", email_body="user edited this")

    async def racing(**kw):                           # a send starts while the model is still writing
        await db.execute(update(JobApplication).where(JobApplication.id == app.id).values(status="SENDING"))
        await db.commit()
        return ComposedEmail("New subject", "model text", "fake", "email_generation@v2", 0.9)
    monkeypatch.setattr(email_service, "compose_email", racing)
    with pytest.raises(ConflictError):
        await email_service.generate_email(db, app.id)
    await db.refresh(app)
    assert app.email_body == "user edited this" and app.status == "SENDING"
