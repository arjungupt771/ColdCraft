import json

from app.ai import client as ai_client_module
from app.ai.errors import AIAuthError, AIProviderUnavailableError
from tests.conftest import FakeProvider, default_handler, make_client


async def test_generate_email_success(client, make_profile, make_app):
    await make_profile()
    app = await make_app("READY")
    r = await client.post("/api/v1/generate-email", json={"application_id": app.id})
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["email_subject"] == "Backend Engineer — Python & FastAPI" and "Dear Hiring Manager" in j["email_body"]
    assert j["prompt_version"] == "email_generation@v2" and j["email_confidence"] == 0.9 and j["status"] == "READY"
    assert j["ai_provider_used"] == "fake"


async def test_regenerate_overwrites(client, make_profile, make_app, fake_ai):
    await make_profile()
    app = await make_app("READY", email_body="old", email_subject="old")
    await client.post("/api/v1/generate-email", json={"application_id": app.id, "regenerate": True})
    assert (await client.get(f"/api/v1/applications/{app.id}")).json()["email_body"] != "old"


async def test_generate_requires_profile(client, make_app):
    app = await make_app("READY")
    r = await client.post("/api/v1/generate-email", json={"application_id": app.id})
    assert r.status_code == 400 and "Profile" in r.json()["detail"]


async def test_generate_requires_ready_state(client, make_profile, make_app):
    await make_profile()
    for status in ("SENT", "SENDING", "REPLIED"):
        app = await make_app(status)
        r = await client.post("/api/v1/generate-email", json={"application_id": app.id})
        assert r.status_code == 409 and status in r.json()["detail"]


async def test_generate_unknown_application(client, make_profile):
    await make_profile()
    assert (await client.post("/api/v1/generate-email", json={"application_id": "nope"})).status_code == 404


async def test_ai_outage_returns_503_with_retryable_flag(client, make_profile, make_app):
    await make_profile()
    app = await make_app("READY")
    ai_client_module.set_client(make_client(FakeProvider(lambda p, s: AIProviderUnavailableError("down", "fake"))))
    r = await client.post("/api/v1/generate-email", json={"application_id": app.id})
    assert r.status_code == 503 and r.json()["retryable"] is True and "AI step failed" in r.json()["detail"]


async def test_fallback_provider_is_recorded(client, make_profile, make_app):
    await make_profile()
    app = await make_app("READY")
    primary = FakeProvider(lambda p, s: AIAuthError("bad key", "groq"), "groq")
    ai_client_module.set_client(make_client(primary, FakeProvider(default_handler, "gemini")))
    r = await client.post("/api/v1/generate-email", json={"application_id": app.id})
    assert r.status_code == 200 and r.json()["ai_provider_used"] == "gemini"


async def test_invalid_ai_output_is_not_saved(client, make_profile, make_app):
    await make_profile()
    app = await make_app("READY", email_body="keep me")
    ai_client_module.set_client(make_client(FakeProvider(lambda p, s: json.dumps({"subject": "x", "body": "too short"}))))
    r = await client.post("/api/v1/generate-email", json={"application_id": app.id})
    assert r.status_code == 502
    assert (await client.get(f"/api/v1/applications/{app.id}")).json()["email_body"] == "keep me"


# ── sending ──
SEND = dict(recipient_email="hr@acme.com", subject="Hello", body="Body text")


async def test_send_success(client, make_profile, make_app, fake_gmail):
    await make_profile()
    app = await make_app("READY")
    r = await client.post("/api/v1/send-email", json=dict(SEND, application_id=app.id))
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["status"] == "SENT" and j["sent_at"] and j["recipient_email"] == "hr@acme.com"
    assert fake_gmail.sent == [{"to": "hr@acme.com", "subject": "Hello", "body": "Body text", "thread_id": None}]


async def test_send_requires_gmail(client, make_profile, make_app, fake_gmail):
    await make_profile(gmail_connected=False)
    app = await make_app("READY")
    r = await client.post("/api/v1/send-email", json=dict(SEND, application_id=app.id))
    assert r.status_code == 400 and "Gmail not connected" in r.json()["detail"] and not fake_gmail.sent


async def test_cannot_send_twice(client, make_profile, make_app, fake_gmail):
    await make_profile()
    app = await make_app("READY")
    await client.post("/api/v1/send-email", json=dict(SEND, application_id=app.id))
    r = await client.post("/api/v1/send-email", json=dict(SEND, application_id=app.id))
    assert r.status_code == 409 and len(fake_gmail.sent) == 1


async def test_cannot_send_unresearched_draft(client, make_profile, make_app, fake_gmail):
    await make_profile()
    app = await make_app("DRAFT")
    assert (await client.post("/api/v1/send-email", json=dict(SEND, application_id=app.id))).status_code == 409


async def test_send_validates_recipient(client, make_app):
    app = await make_app("READY")
    assert (await client.post("/api/v1/send-email", json=dict(SEND, application_id=app.id, recipient_email="nope"))).status_code == 422
    assert (await client.post("/api/v1/send-email", json=dict(SEND, application_id=app.id, subject=""))).status_code == 422


async def test_gmail_failure_keeps_application_ready(client, make_profile, make_app, fake_gmail):
    await make_profile()
    app = await make_app("READY")
    fake_gmail.fail_send = True
    r = await client.post("/api/v1/send-email", json=dict(SEND, application_id=app.id))
    assert r.status_code == 502 and "gmail down" not in r.text and "Sent folder" in r.json()["detail"]
    got = (await client.get(f"/api/v1/applications/{app.id}")).json()
    assert got["status"] == "READY" and "Sent folder" in got["last_error"]      # retryable, nothing marked sent
