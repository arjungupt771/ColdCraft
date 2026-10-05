"""Item 7: the whole journey through the real HTTP API — only AI, Gmail and the network are faked."""
from datetime import datetime, timedelta, timezone

from sqlalchemy import update
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.models.models import FollowUp

API = "/api/v1"


async def get(client, app_id):
    return (await client.get(f"{API}/applications/{app_id}")).json()


async def setup_profile(client):
    await client.put(f"{API}/profile", json={"name": "Test User", "email": "test@example.com", "skills": ["Python", "FastAPI"],
                                             "experience_years": 3, "resume_text": "Built APIs."})
    from app.integrations import gmail
    gmail._pending_states["s"] = 9e12
    assert (await client.get(f"{API}/gmail/callback", params={"code": "c", "state": "s"})).status_code == 200


async def test_full_journey_from_url_to_followup_and_reply(client, engine, fake_gmail, fake_ai):
    await setup_profile(client)

    # 1. capture → extraction (DRAFT), nothing researched or written yet
    r = await client.post(f"{API}/process-linkedin?research=false", json={"url": "linkedin.com/jobs/view/3812345678"})
    assert r.status_code == 200
    app = r.json()
    assert (app["status"], app["company_name"], app["company_research"], app["email_body"]) == ("DRAFT", "Acme", "", None)

    # 2. edit / confirm the extraction
    r = await client.put(f"{API}/applications/{app['id']}", json={"role_title": "Senior Backend Engineer", "recipient_email": "hr@acme.com"})
    assert r.json()["role_title"] == "Senior Backend Engineer" and r.json()["recipient_source"] == "user"

    # 3. research → READY
    r = await client.post(f"{API}/applications/{app['id']}/research")
    assert r.json()["status"] == "READY" and r.json()["company_research"]
    assert (await client.put(f"{API}/applications/{app['id']}", json={"role_title": "Late edit"})).status_code == 409   # locked now

    # 4. generate → validated → saved
    r = await client.post(f"{API}/generate-email", json={"application_id": app["id"]})
    a = r.json()
    assert a["status"] == "READY" and a["email_body"].startswith("Dear Hiring Manager,") and a["prompt_version"] == "email_generation@v2"
    assert "test@example.com" in a["email_body"].splitlines()[-1] and a["email_confidence"] == 0.9

    # 5. user review: tweak the draft, then send
    r = await client.put(f"{API}/applications/{app['id']}/email", json={"subject": "Reviewed subject"})
    assert r.json()["email_subject"] == "Reviewed subject"
    r = await client.post(f"{API}/send-email", json={"application_id": app["id"], "recipient_email": "hr@acme.com",
                                                     "subject": "Reviewed subject", "body": a["email_body"]})
    assert r.status_code == 200 and r.json()["status"] == "SENT" and r.json()["sent_at"]
    assert len(fake_gmail.sent) == 1 and fake_gmail.sent[0]["subject"] == "Reviewed subject"
    # no second send, no more edits
    assert (await client.post(f"{API}/send-email", json={"application_id": app["id"], "recipient_email": "hr@acme.com",
                                                         "subject": "x", "body": "y"})).status_code == 409
    assert (await client.put(f"{API}/applications/{app['id']}/email", json={"body": "tamper"})).status_code == 409

    # 6. follow-up: schedule → not due yet → time passes → due → send in the same thread
    r = await client.post(f"{API}/followups/schedule", json={"application_id": app["id"], "days_after_send": 5})
    fu = r.json()
    assert fu["status"] == "pending" and fu["body"].startswith("Dear Hiring Manager,")
    assert (await client.post(f"{API}/followups/check-due")).json() == [] and (await get(client, app["id"]))["status"] == "SENT"
    async with async_sessionmaker(engine)() as s:
        await s.execute(update(FollowUp).where(FollowUp.id == fu["id"]).values(scheduled_at=datetime.now(timezone.utc) - timedelta(hours=1)))
        await s.commit()
    assert [d["id"] for d in (await client.post(f"{API}/followups/check-due")).json()] == [fu["id"]]
    assert (await get(client, app["id"]))["status"] == "FOLLOW_UP_DUE"
    r = await client.post(f"{API}/followups/{fu['id']}/send")
    assert r.json()["status"] == "sent" and len(fake_gmail.sent) == 2
    assert fake_gmail.sent[0]["thread_id"] is None and fake_gmail.sent[1]["thread_id"] == "thread-1"   # reply stays in the original thread
    assert (await get(client, app["id"]))["status"] == "FOLLOW_UP_SENT"

    # 7. reply arrives → done: nothing further can be scheduled or sent
    r = await client.post(f"{API}/applications/{app['id']}/mark-replied")
    assert r.json()["status"] == "REPLIED" and r.json()["reply_received"] is True
    assert (await client.post(f"{API}/followups/schedule", json={"application_id": app["id"]})).status_code == 400
    assert (await client.put(f"{API}/applications/{app['id']}/status", json={"status": "INTERVIEW"})).json()["status"] == "INTERVIEW"
    assert len(fake_gmail.sent) == 2


async def test_recapturing_the_same_job_is_blocked_unless_forced(client, fake_ai, fake_web):
    first = await client.post(f"{API}/process-linkedin?research=false", json={"url": "https://careers.acme.com/job/42"})
    assert first.status_code == 200
    calls_after_first = len(fake_ai.calls)
    again = await client.post(f"{API}/process-linkedin?research=false", json={"url": "https://www.careers.acme.com/job/42/?utm=x"})
    assert again.status_code == 409 and again.json()["code"] == "duplicate_application"
    assert again.json()["existing_id"] == first.json()["id"] and len(fake_ai.calls) == calls_after_first      # no AI spend
    forced = await client.post(f"{API}/process-linkedin?research=false&force=true", json={"url": "https://careers.acme.com/job/42"})
    assert forced.status_code == 200 and forced.json()["id"] != first.json()["id"]
    assert len((await client.get(f"{API}/applications")).json()) == 2


async def test_screenshot_journey_reaches_a_sendable_draft(client, fake_gmail, fake_ai, png_b64):
    await setup_profile(client)
    app = (await client.post(f"{API}/process-screenshot?research=false", json={"image_base64": png_b64})).json()
    assert app["source"] == "screenshot" and app["status"] == "DRAFT" and fake_ai.calls[0][0] == "vision"
    # straight from DRAFT: generation researches first, then writes
    a = (await client.post(f"{API}/generate-email", json={"application_id": app["id"]})).json()
    assert a["status"] == "READY" and a["company_research"] and a["email_body"]
    # careers@ was a guess → must be confirmed
    assert a["recipient_source"] == "guess"
    body = {"application_id": a["id"], "recipient_email": a["recipient_email"], "subject": a["email_subject"], "body": a["email_body"]}
    assert (await client.post(f"{API}/send-email", json=body)).status_code == 409
    assert (await client.post(f"{API}/send-email", json={**body, "confirm_unverified": True})).json()["status"] == "SENT"


async def test_failures_midway_never_lose_or_corrupt_the_application(client, fake_ai, fake_web, make_profile):
    from app.ai.errors import AIProviderUnavailableError
    from tests.conftest import default_handler
    await make_profile()
    app = (await client.post(f"{API}/process-linkedin?research=false", json={"url": "https://x.com/job/9"})).json()
    fake_ai.handler = lambda p, s: AIProviderUnavailableError("down", "fake")
    assert (await client.post(f"{API}/generate-email", json={"application_id": app["id"]})).status_code == 503
    kept = await get(client, app["id"])
    assert kept["status"] == "DRAFT" and kept["company_name"] == "Acme" and kept["last_error"]      # still there, retryable
    fake_ai.handler = default_handler
    ok = (await client.post(f"{API}/generate-email", json={"application_id": app["id"]})).json()
    assert ok["status"] == "READY" and ok["last_error"] is None and ok["email_body"]
