from app.core.config import settings
from app.integrations import gmail


async def test_health(client):
    r = await client.get("/health")
    assert r.status_code == 200 and r.json()["status"] == "ok"
    assert r.headers["x-content-type-options"] == "nosniff"


async def test_empty_list(client):
    r = await client.get("/api/v1/applications")
    assert r.status_code == 200 and r.json() == []


async def test_process_linkedin_creates_ready_application(client):
    r = await client.post("/api/v1/process-linkedin", json={"url": "linkedin.com/jobs/view/1"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "READY" and body["company_name"] == "Acme" and body["recipient_email"] == "careers@acme.com"
    assert (await client.get(f"/api/v1/applications/{body['id']}")).json()["id"] == body["id"]
    assert len((await client.get("/api/v1/applications")).json()) == 1


async def test_step_by_step_capture_then_research(client):
    r = await client.post("/api/v1/process-linkedin?research=false", json={"url": "https://x.com/job"})
    app = r.json()
    assert app["status"] == "DRAFT" and app["company_research"] == ""
    r = await client.post(f"/api/v1/applications/{app['id']}/research")
    assert r.status_code == 200 and r.json()["status"] == "READY" and r.json()["company_research"]


async def test_process_screenshot_valid(client, png_b64):
    r = await client.post("/api/v1/process-screenshot", json={"image_base64": png_b64})
    assert r.status_code == 200 and r.json()["source"] == "screenshot"


async def test_screenshot_not_an_image_is_422(client):
    import base64
    r = await client.post("/api/v1/process-screenshot", json={"image_base64": base64.b64encode(b"x" * 300).decode()})
    assert r.status_code == 422 and "image" in r.json()["detail"].lower()


async def test_unknown_application_404(client):
    assert (await client.get("/api/v1/applications/nope")).status_code == 404
    assert (await client.post("/api/v1/applications/nope/research")).status_code == 404


async def test_edit_draft(client, make_app):
    app = await make_app("READY")
    r = await client.put(f"/api/v1/applications/{app.id}/email",
                         json={"subject": "New subject", "body": "New body", "recipient_email": "hr@acme.com", "notes": "n"})
    assert r.status_code == 200
    j = r.json()
    assert (j["email_subject"], j["email_body"], j["recipient_email"], j["notes"]) == ("New subject", "New body", "hr@acme.com", "n")


async def test_edit_draft_validates_input(client, make_app):
    app = await make_app("READY")
    assert (await client.put(f"/api/v1/applications/{app.id}/email", json={"recipient_email": "not-an-email"})).status_code == 422
    assert (await client.put(f"/api/v1/applications/{app.id}/email", json={"subject": "x" * 500})).status_code == 422


async def test_cannot_edit_after_sent(client, make_app):
    app = await make_app("SENT")
    r = await client.put(f"/api/v1/applications/{app.id}/email", json={"body": "tamper"})
    assert r.status_code == 409


async def test_mark_replied_flow(client, make_app, make_followup):
    app = await make_app("SENT")
    await make_followup(app, due=False)
    r = await client.post(f"/api/v1/applications/{app.id}/mark-replied")
    assert r.status_code == 200 and r.json()["status"] == "REPLIED" and r.json()["reply_received"] is True
    fus = (await client.get(f"/api/v1/followups/{app.id}")).json()
    assert [f["status"] for f in fus] == ["cancelled"]


async def test_mark_replied_requires_sent(client, make_app):
    app = await make_app("READY")
    r = await client.post(f"/api/v1/applications/{app.id}/mark-replied")
    assert r.status_code == 409 and "READY" in r.json()["detail"]


async def test_outcome_status_transitions(client, make_app):
    app = await make_app("REPLIED")
    assert (await client.put(f"/api/v1/applications/{app.id}/status", json={"status": "INTERVIEW"})).json()["status"] == "INTERVIEW"
    assert (await client.put(f"/api/v1/applications/{app.id}/status", json={"status": "REJECTED"})).json()["status"] == "REJECTED"
    # terminal: nothing leaves REJECTED
    assert (await client.put(f"/api/v1/applications/{app.id}/status", json={"status": "WITHDRAWN"})).status_code == 409


async def test_status_endpoint_only_accepts_manual_outcomes(client, make_app):
    app = await make_app("READY")
    assert (await client.put(f"/api/v1/applications/{app.id}/status", json={"status": "SENT"})).status_code == 422


async def test_delete_application(client, make_app):
    app = await make_app("READY")
    assert (await client.delete(f"/api/v1/applications/{app.id}")).status_code == 204
    assert (await client.get(f"/api/v1/applications/{app.id}")).status_code == 404


async def test_api_token_enforced_when_configured(client, monkeypatch):
    monkeypatch.setattr(settings, "API_TOKEN", "s3cret")
    assert (await client.get("/api/v1/applications")).status_code == 401
    assert (await client.get("/api/v1/applications", headers={"X-API-Token": "wrong"})).status_code == 401
    assert (await client.get("/api/v1/applications", headers={"X-API-Token": "s3cret"})).status_code == 200
    assert (await client.get("/health")).status_code == 200            # health stays open


async def test_oauth_callback_is_exempt_from_token_but_checks_state(client, monkeypatch):
    monkeypatch.setattr(settings, "API_TOKEN", "s3cret")
    r = await client.get("/api/v1/gmail/callback", params={"code": "c", "state": "forged"})
    assert r.status_code == 400 and "state" in r.json()["detail"].lower()      # reached the handler, not a 401


async def test_unhandled_errors_do_not_leak_details(client, monkeypatch):
    from app.services import application_service

    async def boom(*a, **k):
        raise RuntimeError("secret internal path /etc/passwd")
    monkeypatch.setattr(application_service, "list_applications", boom)
    r = await client.get("/api/v1/applications")
    assert r.status_code == 500 and "passwd" not in r.text
