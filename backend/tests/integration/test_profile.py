from sqlalchemy import text

from app.integrations import gmail


async def test_profile_autocreated_and_updated(client):
    r = await client.get("/api/v1/profile")
    assert r.status_code == 200 and r.json()["gmail_connected"] is False
    r = await client.put("/api/v1/profile", json={"name": "Arjun", "skills": ["Python"], "tone": "friendly"})
    assert r.json()["name"] == "Arjun" and r.json()["skills"] == ["Python"] and r.json()["tone"] == "friendly"


async def test_profile_rejects_unknown_tone(client):
    assert (await client.put("/api/v1/profile", json={"tone": "aggressive"})).status_code == 422


async def test_gmail_token_is_stored_encrypted_and_never_returned(client, engine, fake_gmail):
    gmail._pending_states["good-state"] = 9e12
    r = await client.get("/api/v1/gmail/callback", params={"code": "abc", "state": "good-state"})
    assert r.status_code == 200 and "connected" in r.text.lower()

    async with engine.connect() as conn:
        stored = (await conn.execute(text("select gmail_token_enc from user_profile"))).scalar_one()
    assert stored and "ref-SECRET" not in stored and "refresh_token" not in stored

    profile = (await client.get("/api/v1/profile")).json()
    assert profile["gmail_connected"] is True and "token" not in str(profile).replace("gmail_connected", "")
    assert (await client.get("/api/v1/gmail/status")).json() == {"connected": True, "email": "test@example.com"}


async def test_oauth_state_is_single_use(client, fake_gmail):
    gmail._pending_states["once"] = 9e12
    assert (await client.get("/api/v1/gmail/callback", params={"code": "c", "state": "once"})).status_code == 200
    assert (await client.get("/api/v1/gmail/callback", params={"code": "c", "state": "once"})).status_code == 400


async def test_disconnect(client, make_profile):
    await make_profile()
    assert (await client.get("/api/v1/gmail/status")).json()["connected"] is True
    await client.delete("/api/v1/gmail/disconnect")
    assert (await client.get("/api/v1/gmail/status")).json() == {"connected": False, "email": None}
