async def test_schedule_followup(client, make_profile, make_app):
    await make_profile()
    app = await make_app("SENT")
    r = await client.post("/api/v1/followups/schedule", json={"application_id": app.id, "days_after_send": 7, "custom_note": "hi"})
    assert r.status_code == 200, r.text
    fu = r.json()
    assert fu["status"] == "pending" and fu["sequence_number"] == 1 and fu["subject"]
    assert (await client.get(f"/api/v1/applications/{app.id}")).json()["followup_scheduled_at"]


async def test_schedule_validation(client, make_profile, make_app):
    await make_profile()
    app = await make_app("SENT")
    for days in (0, 61, -3):
        r = await client.post("/api/v1/followups/schedule", json={"application_id": app.id, "days_after_send": days})
        assert r.status_code == 422
    assert (await client.post("/api/v1/followups/schedule", json={"application_id": "nope"})).status_code == 404


async def test_schedule_requires_sent_application(client, make_profile, make_app):
    await make_profile()
    app = await make_app("READY")
    r = await client.post("/api/v1/followups/schedule", json={"application_id": app.id})
    assert r.status_code == 400


async def test_one_live_followup_per_application(client, make_profile, make_app):
    await make_profile()
    app = await make_app("SENT")
    first = await client.post("/api/v1/followups/schedule", json={"application_id": app.id})
    assert first.status_code == 200
    again = await client.post("/api/v1/followups/schedule", json={"application_id": app.id})
    assert again.status_code == 409 and "already scheduled" in again.json()["detail"]


async def test_fourth_followup_blocked(client, make_profile, make_app, fake_gmail):
    await make_profile()
    app = await make_app("SENT")
    for _ in range(3):
        fu = await client.post("/api/v1/followups/schedule", json={"application_id": app.id})
        assert fu.status_code == 200
        assert (await client.post(f"/api/v1/followups/{fu.json()['id']}/send")).status_code == 200
    r = await client.post("/api/v1/followups/schedule", json={"application_id": app.id})
    assert r.status_code == 409 and "Maximum" in r.json()["detail"]


async def test_due_check_and_send_cycle(client, make_profile, make_app, make_followup, fake_gmail):
    await make_profile()
    app = await make_app("SENT")
    fu = await make_followup(app)

    due = (await client.get("/api/v1/followups/due")).json()
    assert [d["id"] for d in due] == [fu.id]

    assert len((await client.post("/api/v1/followups/check-due")).json()) == 1
    assert (await client.get(f"/api/v1/applications/{app.id}")).json()["status"] == "FOLLOW_UP_DUE"

    r = await client.post(f"/api/v1/followups/{fu.id}/send")
    assert r.status_code == 200 and r.json()["status"] == "sent"
    a = (await client.get(f"/api/v1/applications/{app.id}")).json()
    assert a["status"] == "FOLLOW_UP_SENT" and a["followup_count"] == 1
    assert fake_gmail.sent[0]["thread_id"] == "thread-0"
    assert (await client.get("/api/v1/followups/due")).json() == []


async def test_send_without_gmail(client, make_profile, make_app, make_followup):
    await make_profile(gmail_connected=False)
    fu = await make_followup(await make_app("SENT"))
    r = await client.post(f"/api/v1/followups/{fu.id}/send")
    assert r.status_code == 400 and "Gmail" in r.json()["detail"]


async def test_send_twice_is_409(client, make_profile, make_app, make_followup, fake_gmail):
    await make_profile()
    fu = await make_followup(await make_app("SENT"))
    await client.post(f"/api/v1/followups/{fu.id}/send")
    assert (await client.post(f"/api/v1/followups/{fu.id}/send")).status_code == 409


async def test_cancel(client, make_app, make_followup):
    fu = await make_followup(await make_app("SENT"))
    assert (await client.post(f"/api/v1/followups/{fu.id}/cancel")).json() == {"status": "cancelled"}
    assert (await client.get("/api/v1/followups/due")).json() == []
    assert (await client.post(f"/api/v1/followups/{fu.id}/send")).status_code == 409


async def test_list_for_application_is_ordered(client, make_app, make_followup):
    app = await make_app("SENT")
    await make_followup(app, seq=2, due=False)
    await make_followup(app, seq=1, status="sent")
    assert [f["sequence_number"] for f in (await client.get(f"/api/v1/followups/{app.id}")).json()] == [1, 2]
