import json

from app.ai import client as ai_client_module
from app.ai.researcher import research_company
from app.integrations import web
from tests.conftest import RESEARCH, FakeProvider, make_client


async def test_research_formats_summary_and_highlights(fake_ai, fake_web):
    r = await research_company("Acme", "acme.com")
    assert r.text.startswith(RESEARCH["summary"]) and "- Open-sourced its ledger service" in r.text
    assert r.prompt_version == "company_research@v1"


async def test_website_context_is_given_to_the_model(fake_ai, fake_web):
    await research_company("Acme", "acme.com")
    assert "Acme is a payments company." in fake_ai.calls[0][1]


async def test_wikipedia_used_without_website(fake_ai, monkeypatch):
    async def wiki(title):
        return "Acme Corp is a widely known company."
    monkeypatch.setattr(web, "wikipedia_extract", wiki)
    await research_company("Acme", None)
    assert "Wikipedia: Acme Corp is a widely known company." in fake_ai.calls[0][1]


async def test_no_context_tells_model_not_to_guess(fake_ai, monkeypatch):
    async def nothing(*a, **k):
        return ""
    monkeypatch.setattr(web, "wikipedia_extract", nothing)
    await research_company("Acme", None)
    assert "omit anything you are unsure of" in fake_ai.calls[0][1]


async def test_too_short_summary_triggers_repair(fake_web):
    outputs = iter([json.dumps({"summary": "short"}), json.dumps(RESEARCH)])
    p = FakeProvider(lambda pr, s: next(outputs))
    ai_client_module.set_client(make_client(p))
    try:
        r = await research_company("Acme")
    finally:
        ai_client_module.set_client(None)
    assert len(p.calls) == 2 and "Acme builds" in r.text
