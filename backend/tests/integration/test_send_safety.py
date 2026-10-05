"""Item 4: Gmail send — one email per application, safe failures, clean recipient handling."""
import asyncio
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import update
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.core.errors import ConflictError, GmailAuthError, GmailSendError, SendInProgressError
from app.models.models import JobApplication
from app.services import application_service, email_service

SEND = dict(recipient_email="hr@acme.com", subject="Hello", body="Body text")
URL = "/api/v1/send-email"


async def status_of(client, app_id):
    return (await client.get(f"/api/v1/applications/{app_id}")).json()


async def test_concurrent_double_send_sends_exactly_one_email(engine, make_profile, make_app, fake_gmail):
    await make_profile()
    app = await make_app("READY")
    fake_gmail.delay = 0.15                                    # keep the first send in flight while the second starts
    maker = async_sessionmaker(engine, expire_on_commit=False)

    async def attempt():
        async with maker() as s:
            return await email_service.send_application_email(s, app.id, "hr@acme.com", "Hello", "Body text")
    results = await asyncio.gather(attempt(), attempt(), return_exceptions=True)

    assert len(fake_gmail.sent) == 1                           # the important part
    assert sum(not isinstance(r, Exception) for r in results) == 1
    assert any(isinstance(r, (SendInProgressError, ConflictError)) for r in results)


async def test_sending_state_blocks_a_second_send_and_a_regenerate(client, make_profile, make_app, fake_gmail):
    await make_profile()
    app = await make_app("SENDING")
    r = await client.post(URL, json=dict(SEND, application_id=app.id))
    assert r.status_code == 409 and r.json()["code"] == "send_in_progress" and not fake_gmail.sent
    assert (await client.post("/api/v1/generate-email", json={"application_id": app.id})).status_code == 409
    assert (await client.delete(f"/api/v1/applications/{app.id}")).status_code == 409


async def test_send_twice_in_a_row_only_sends_once(client, make_profile, make_app, fake_gmail):
    await make_profile()
    app = await make_app("READY")
    assert (await client.post(URL, json=dict(SEND, application_id=app.id))).status_code == 200
    assert (await client.post(URL, json=dict(SEND, application_id=app.id))).status_code == 409
    assert len(fake_gmail.sent) == 1


async def test_exact_subject_and_body_are_sent_and_saved(client, make_profile, make_app, fake_gmail):
    await make_profile()
    app = await make_app("READY", email_subject="AI draft", email_body="AI body")
    r = await client.post(URL, json=dict(SEND, application_id=app.id, subject="  My edited subject ", body="My edited body\nline 2"))
    j = r.json()
    assert fake_gmail.sent[0]["subject"] == "My edited subject" and fake_gmail.sent[0]["body"] == "My edited body\nline 2"
    assert (j["email_subject"], j["email_body"], j["status"]) == ("My edited subject", "My edited body\nline 2", "SENT")


async def test_definite_failure_releases_the_claim_for_retry(client, make_profile, make_app, fake_gmail):
    await make_profile()
    app = await make_app("READY")
    fake_gmail.error = GmailSendError("Gmail rejected the message (check the recipient address).")
    r = await client.post(URL, json=dict(SEND, application_id=app.id))
    assert r.status_code == 502 and r.json()["ambiguous"] is False
    assert (await status_of(client, app.id))["status"] == "READY"
    fake_gmail.error = None
    assert (await client.post(URL, json=dict(SEND, application_id=app.id))).json()["status"] == "SENT"


async def test_ambiguous_failure_warns_to_check_sent_folder(client, make_profile, make_app, fake_gmail):
    await make_profile()
    app = await make_app("READY")
    fake_gmail.fail_send = True                                # unknown error (e.g. timeout): Gmail may have sent it
    r = await client.post(URL, json=dict(SEND, application_id=app.id))
    assert r.status_code == 502 and r.json()["ambiguous"] is True and "Sent folder" in r.json()["detail"]
    assert "gmail down" not in r.text and (await status_of(client, app.id))["status"] == "READY"


async def test_revoked_gmail_authorization_tells_user_to_reconnect(client, make_profile, make_app, fake_gmail):
    await make_profile()
    app = await make_app("READY")
    fake_gmail.error = GmailAuthError()
    r = await client.post(URL, json=dict(SEND, application_id=app.id))
    assert r.status_code == 400 and r.json()["code"] == "gmail_auth" and "Profile" in r.json()["detail"]
    assert (await status_of(client, app.id))["status"] == "READY"


async def test_gmail_not_connected_fails_before_claiming(client, make_profile, make_app, fake_gmail):
    await make_profile(gmail_connected=False)
    app = await make_app("READY")
    r = await client.post(URL, json=dict(SEND, application_id=app.id))
    assert r.status_code == 400 and "Profile" in r.json()["detail"] and (await status_of(client, app.id))["status"] == "READY"


@pytest.mark.parametrize("field,value", [("subject", "Hi\r\nBcc: victim@x.com"), ("recipient_email", "a@b.com\nBcc: x@y.com"),
                                         ("recipient_email", "a@b.com, c@d.com"), ("recipient_email", "no-at-sign")])
async def test_header_injection_and_bad_recipients_rejected(client, make_app, fake_gmail, field, value):
    app = await make_app("READY")
    r = await client.post(URL, json=dict(SEND, application_id=app.id, **{field: value}))
    assert r.status_code == 422 and not fake_gmail.sent


def test_gmail_integration_itself_refuses_header_injection():
    from app.core.errors import BadRequestError
    from app.integrations import gmail
    with pytest.raises(BadRequestError):
        gmail.send_email({}, "a@b.com", "Hi\nBcc: x@y.com", "body")


# ── unverified (guessed) recipients ──
async def test_guessed_recipient_needs_explicit_confirmation(client, make_profile, make_app, fake_gmail):
    await make_profile()
    app = await make_app("READY", recipient_email="careers@acme.com", recipient_source="guess")
    r = await client.post(URL, json=dict(SEND, application_id=app.id, recipient_email="careers@acme.com"))
    assert r.status_code == 409 and r.json()["code"] == "unverified_recipient" and not fake_gmail.sent
    ok = await client.post(URL, json=dict(SEND, application_id=app.id, recipient_email="careers@acme.com", confirm_unverified=True))
    assert ok.status_code == 200 and len(fake_gmail.sent) == 1


async def test_typing_a_real_address_needs_no_confirmation_and_is_marked_user(client, make_profile, make_app, fake_gmail):
    await make_profile()
    app = await make_app("READY", recipient_email="careers@acme.com", recipient_source="guess")
    r = await client.post(URL, json=dict(SEND, application_id=app.id))              # hr@acme.com differs from the guess
    assert r.status_code == 200 and r.json()["recipient_source"] == "user"


async def test_hunter_found_address_needs_no_confirmation(client, make_profile, make_app, fake_gmail):
    await make_profile()
    app = await make_app("READY", recipient_email="hr@acme.com", recipient_source="hunter")
    assert (await client.post(URL, json=dict(SEND, application_id=app.id))).status_code == 200


# ── crash recovery ──
async def test_stuck_sending_is_returned_to_ready_with_a_warning(db, make_app):
    stuck = await make_app("SENDING")
    fresh = await make_app("SENDING", company_name="Fresh")
    await db.execute(update(JobApplication).where(JobApplication.id == stuck.id)
                     .values(updated_at=datetime.now(timezone.utc) - timedelta(minutes=30)))
    await db.commit()
    assert await application_service.recover_stuck_sending(db) == 1
    await db.refresh(stuck)
    await db.refresh(fresh)
    assert stuck.status == "READY" and "Sent folder" in stuck.last_error and fresh.status == "SENDING"
