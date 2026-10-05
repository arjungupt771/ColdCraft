import json

import pytest

from app.ai import prompts
from app.ai.composer import compose_email, compose_followup
from app.ai.errors import AIInvalidResponseError
from app.core.config import settings
from tests.conftest import EMAIL, FOLLOWUP, FakeProvider, make_client
from app.ai import client as ai_client_module

KW = dict(company_name="Acme", role_title="Backend Engineer", required_skills=["Python", "Go"], company_research="Pays.",
          user_name="Test User", user_email="test@example.com", user_resume="Built APIs", user_skills=["Python", "Rust"],
          experience_years=3)


async def test_compose_email_returns_validated_result(fake_ai):
    out = await compose_email(**KW)
    assert out.subject == EMAIL["subject"] and out.body == EMAIL["body"]
    assert out.provider == "fake" and out.prompt_version == "email_generation@v2" and out.confidence == 0.9


async def test_prompt_contains_applicant_facts_and_greeting(fake_ai):
    await compose_email(**KW, recipient_name="Priya")
    _, prompt, system = fake_ai.calls[0]
    assert "Dear Priya," in prompt and "Test User" in prompt and "Python" in prompt   # matched skill listed
    assert "career coach" in system


async def test_placeholder_output_is_repaired():
    bad = dict(EMAIL, body=EMAIL["body"].replace("Test User", "[Your Name]"))
    outputs = iter([json.dumps(bad), json.dumps(EMAIL)])
    p = FakeProvider(lambda pr, s: next(outputs))
    ai_client_module.set_client(make_client(p))
    try:
        out = await compose_email(**KW)
    finally:
        ai_client_module.set_client(None)
    assert "[Your Name]" not in out.body and len(p.calls) == 2


async def test_too_long_email_rejected():
    long_body = json.dumps(dict(EMAIL, body="word " * 400))
    ai_client_module.set_client(make_client(FakeProvider(lambda p, s: long_body)))
    try:
        with pytest.raises(AIInvalidResponseError):
            await compose_email(**KW)
    finally:
        ai_client_module.set_client(None)


async def test_confidence_percentage_normalised(fake_ai):
    fake_ai.handler = lambda p, s: json.dumps(dict(EMAIL, confidence=85))
    assert (await compose_email(**KW)).confidence == 0.85


async def test_compose_followup(fake_ai):
    out = await compose_followup("Acme", "Backend Engineer", "June 01, 2026", "Test User", "test@example.com",
                                 sequence_number=2, custom_note="Saw your launch")
    assert out.subject == FOLLOWUP["subject"] and out.prompt_version == "followup@v1"
    prompt = fake_ai.calls[0][1]
    assert "number 2" in prompt and "Saw your launch" in prompt and "Test User" in prompt


def test_prompt_loader_versions_and_pinning(monkeypatch):
    assert prompts.available_versions("email_generation") == ["v1", "v2"]
    assert prompts.load_prompt("email_generation").tag == "email_generation@v2"
    monkeypatch.setattr(settings, "PROMPT_VERSION_EMAIL_GENERATION", "v9")
    with pytest.raises(FileNotFoundError):
        prompts.load_prompt("email_generation")


def test_prompt_render_requires_all_variables():
    p = prompts.load_prompt("email_generation")
    with pytest.raises(KeyError):
        p.render(user_name="x")
