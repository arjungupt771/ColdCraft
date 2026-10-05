"""Items 5 & 6: application states and the follow-up system behave correctly."""
import itertools
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select, update

from app.core.config import Settings, settings
from app.core.errors import InvalidTransitionError
from app.domain.state_machine import ALLOWED_TRANSITIONS, ApplicationStatus as S, can_transition, transition
from app.models.models import FollowUp, JobApplication
from app.services import followup_service as fu_svc

ALL = list(S)
OUTCOMES = ["REPLIED", "INTERVIEW", "REJECTED", "WITHDRAWN"]


class Obj:
    def __init__(self, status):
        self.status = status


# ── item 5: every possible transition is either allowed by the table or rejected ──
@pytest.mark.parametrize("cur,new", list(itertools.product(ALL, ALL)))
def test_transition_matrix(cur, new):
    allowed = new in ALLOWED_TRANSITIONS[cur]
    assert can_transition(cur, new) is allowed
    obj = Obj(cur.value)
    if allowed:
        transition(obj, new)
        assert obj.status == new.value
    else:
        with pytest.raises(InvalidTransitionError):
            transition(obj, new)
        assert obj.status == cur.value


def test_documented_lifecycle_is_walkable():
    obj = Obj("DRAFT")
    for nxt in ("RESEARCHING", "READY", "SENDING", "SENT", "FOLLOW_UP_DUE", "FOLLOW_UP_SENT", "REPLIED", "INTERVIEW"):
        transition(obj, nxt)


def test_you_cannot_skip_ahead_or_go_back_after_sending():
    for cur, new in [("DRAFT", "SENT"), ("READY", "SENT"), ("DRAFT", "FOLLOW_UP_DUE"), ("SENT", "READY"), ("SENT", "DRAFT"),
                     ("FOLLOW_UP_SENT", "SENT"), ("REPLIED", "FOLLOW_UP_DUE"), ("INTERVIEW", "REPLIED")]:
        assert not can_transition(cur, new), (cur, new)


async def test_invalid_transitions_are_409_over_http(client, make_app):
    app = await make_app("READY")
    assert (await client.post(f"/api/v1/applications/{app.id}/mark-replied")).status_code == 409
    assert (await client.put(f"/api/v1/applications/{app.id}/status", json={"status": "INTERVIEW"})).status_code == 409
    done = await make_app("REJECTED", company_name="Done")
    assert (await client.put(f"/api/v1/applications/{done.id}/status", json={"status": "WITHDRAWN"})).status_code == 409


# ── item 6: no follow-ups once the conversation is over ──
@pytest.mark.parametrize("status", ["READY"] + OUTCOMES)
async def test_cannot_schedule_followup_after_outcome(client, make_profile, make_app, status):
    await make_profile()
    app = await make_app(status)
    assert (await client.post("/api/v1/followups/schedule", json={"application_id": app.id})).status_code == 400


@pytest.mark.parametrize("outcome,via", [("REPLIED", "mark-replied"), ("REJECTED", "status"), ("WITHDRAWN", "status")])
async def test_outcome_cancels_pending_followups_and_blocks_sending(client, make_profile, make_app, make_followup, fake_gmail, outcome, via):
    await make_profile()
    app = await make_app("SENT")
    fu = await make_followup(app, due=True)
    if via == "mark-replied":
        assert (await client.post(f"/api/v1/applications/{app.id}/mark-replied")).status_code == 200
    else:
        assert (await client.put(f"/api/v1/applications/{app.id}/status", json={"status": outcome})).status_code == 200
    assert (await client.get(f"/api/v1/followups/{app.id}")).json()[0]["status"] == "cancelled"
    assert (await client.post(f"/api/v1/followups/{fu.id}/send")).status_code == 409 and not fake_gmail.sent
    assert (await client.get("/api/v1/followups/due")).json() == []


async def test_interview_after_reply_leaves_nothing_to_send(client, make_profile, make_app, make_followup, fake_gmail):
    await make_profile()
    app = await make_app("SENT")
    await make_followup(app)
    await client.post(f"/api/v1/applications/{app.id}/mark-replied")
    assert (await client.put(f"/api/v1/applications/{app.id}/status", json={"status": "INTERVIEW"})).json()["status"] == "INTERVIEW"
    assert (await client.post("/api/v1/followups/check-due")).json() == []
    assert (await client.post("/api/v1/followups/schedule", json={"application_id": app.id})).status_code == 400


async def test_followup_generation_failure_saves_nothing(db, make_profile, make_app, fake_ai):
    from app.ai.errors import AIProviderUnavailableError
    await make_profile()
    app = await make_app("SENT")
    fake_ai.handler = lambda p, s: AIProviderUnavailableError("down", "fake")
    with pytest.raises(Exception):
        await fu_svc.schedule_followup(db, app.id)
    await db.refresh(app)
    assert (await db.execute(select(FollowUp))).first() is None and app.followup_scheduled_at is None


async def test_followup_text_cannot_invent_a_recipient(db, make_profile, make_app, fake_ai):
    import json
    from tests.conftest import FOLLOWUP
    await make_profile()
    app = await make_app("SENT")
    seen = []

    def handler(prompt, system):
        seen.append(prompt)
        body = FOLLOWUP["body"] if len(seen) > 1 else FOLLOWUP["body"].replace("Dear Hiring Manager,", "Dear Sarah,")
        return json.dumps(dict(FOLLOWUP, body=body))
    fake_ai.handler = handler
    fu = await fu_svc.schedule_followup(db, app.id)
    assert fu.body.startswith("Dear Hiring Manager,") and len(seen) == 2          # repaired once


# ── FOLLOWUP_AUTO_SEND=false is the safe default ──
def test_auto_send_defaults_to_off():
    assert Settings(_env_file=None).FOLLOWUP_AUTO_SEND is False


async def test_scheduler_flags_due_followups_but_never_sends_by_default(db, make_profile, make_app, make_followup, fake_gmail, monkeypatch):
    monkeypatch.setattr(settings, "FOLLOWUP_AUTO_SEND", False)
    await make_profile()
    app = await make_app("SENT")
    fu = await make_followup(app)
    await fu_svc.run_scheduler_tick(db)
    await fu_svc.run_scheduler_tick(db)                                           # idempotent
    await db.refresh(app)
    await db.refresh(fu)
    assert app.status == "FOLLOW_UP_DUE" and fu.status == "pending" and fake_gmail.sent == []


async def test_scheduler_sends_only_when_explicitly_enabled(db, make_profile, make_app, make_followup, fake_gmail, monkeypatch):
    monkeypatch.setattr(settings, "FOLLOWUP_AUTO_SEND", True)
    await make_profile()
    app = await make_app("SENT")
    await make_followup(app)
    await fu_svc.run_scheduler_tick(db)
    await db.refresh(app)
    assert len(fake_gmail.sent) == 1 and app.status == "FOLLOW_UP_SENT" and fake_gmail.sent[0]["thread_id"] == "thread-0"


async def test_autosend_never_sends_twice(db, make_profile, make_app, make_followup, fake_gmail, monkeypatch):
    monkeypatch.setattr(settings, "FOLLOWUP_AUTO_SEND", True)
    await make_profile()
    await make_followup(await make_app("SENT"))
    await fu_svc.run_scheduler_tick(db)
    await fu_svc.run_scheduler_tick(db)
    assert len(fake_gmail.sent) == 1


# ── no duplicate follow-ups, even under races ──
async def test_database_itself_refuses_two_live_followups(db, make_app, make_followup):
    from sqlalchemy.exc import IntegrityError
    app = await make_app("SENT")
    await make_followup(app)
    with pytest.raises(IntegrityError):
        await make_followup(app, seq=2)
    await db.rollback()


async def test_concurrent_followup_send_sends_once(engine, make_profile, make_app, make_followup, fake_gmail):
    import asyncio
    from sqlalchemy.ext.asyncio import async_sessionmaker
    await make_profile()
    fu = await make_followup(await make_app("SENT"))
    fake_gmail.delay = 0.15
    maker = async_sessionmaker(engine, expire_on_commit=False)

    async def attempt():
        async with maker() as s:
            return await fu_svc.send_followup(s, fu.id)
    results = await asyncio.gather(attempt(), attempt(), return_exceptions=True)
    assert len(fake_gmail.sent) == 1 and sum(not isinstance(r, Exception) for r in results) == 1


async def test_stuck_followup_is_failed_not_resent(db, make_app, make_followup):
    app = await make_app("SENT")
    stuck = await make_followup(app, status="sending")
    await db.execute(update(FollowUp).where(FollowUp.id == stuck.id).values(sent_at=datetime.now(timezone.utc) - timedelta(minutes=30)))
    await db.commit()
    assert await fu_svc.recover_stuck_followups(db) == 1
    await db.refresh(stuck)
    assert stuck.status == "failed" and (await fu_svc.get_due_followups(db)) == []
