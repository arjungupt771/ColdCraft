import httpx
import pytest

from app.core.config import settings
from app.integrations import hunter


def mock_hunter(monkeypatch, handler):
    real = httpx.AsyncClient
    monkeypatch.setattr(hunter.httpx, "AsyncClient", lambda *a, **k: real(transport=httpx.MockTransport(handler)))


@pytest.mark.parametrize("url,domain", [
    ("https://www.acme.com/careers", "acme.com"), ("acme.com", "acme.com"), ("http://Jobs.Acme.io:8080/x?y=1", "jobs.acme.io"),
])
def test_extract_domain(url, domain):
    assert hunter.extract_domain(url) == domain


def test_guess_domain():
    assert hunter.guess_domain("Acme & Sons, Inc.") == "acmesonsinc.com" and hunter.guess_domain("!!!") is None


async def test_guess_when_no_api_key(monkeypatch):
    monkeypatch.setattr(settings, "HUNTER_API_KEY", "")
    info = await hunter.find_recruiter("Acme", "https://acme.com")
    assert info.email == "careers@acme.com" and info.source == "guess" and info.verified is False


async def test_no_domain_returns_none(monkeypatch):
    monkeypatch.setattr(settings, "HUNTER_API_KEY", "")
    assert await hunter.find_recruiter("???", None) is None


async def test_hunter_prefers_hr_contact(monkeypatch):
    monkeypatch.setattr(settings, "HUNTER_API_KEY", "key")
    mock_hunter(monkeypatch, lambda req: httpx.Response(200, json={"data": {"emails": [
        {"value": "cto@acme.com", "department": "engineering", "position": "CTO"},
        {"value": "Jane@acme.com", "department": "hr", "position": "Talent Lead", "first_name": "Jane", "last_name": "Roe",
         "verification": {"status": "valid"}},
    ]}}))
    info = await hunter.find_recruiter("Acme", "acme.com")
    assert (info.email, info.name, info.source, info.verified) == ("jane@acme.com", "Jane Roe", "hunter", True)


async def test_hunter_error_falls_back_to_guess(monkeypatch):
    monkeypatch.setattr(settings, "HUNTER_API_KEY", "key")
    mock_hunter(monkeypatch, lambda req: httpx.Response(500))
    info = await hunter.find_recruiter("Acme", "acme.com")
    assert info.source == "guess"


async def test_hunter_skips_malformed_addresses(monkeypatch):
    monkeypatch.setattr(settings, "HUNTER_API_KEY", "key")
    mock_hunter(monkeypatch, lambda req: httpx.Response(200, json={"data": {"emails": [{"value": "not-an-email"}]}}))
    assert (await hunter.find_recruiter("Acme", "acme.com")).source == "guess"
