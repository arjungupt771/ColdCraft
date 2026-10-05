from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.core.errors import BadRequestError, ConflictError, GmailNotConnectedError, GmailSendError, InvalidTransitionError, NotFoundError
from app.models.models import FollowUp
from app.services import followup_service as svc


async def test_schedule_creates_pending_followup_from_send_date(db, fake_ai, make_profile, make_app):
    await make_profile()
    app = await make_app("SENT")
    fu = await svc.schedule_followup(db, app.id, days_after_send=5, custom_note="Loved the launch")
    assert fu.status == "pending" and fu.sequence_number == 1 and fu.prompt_version == "followup@v1"
    assert abs((fu.scheduled_at.replace(tzinfo=timezone.utc) - (app.sent_at.replace(tzinfo=timezone.utc) + timedelta(days=5)))
               .total_seconds()) < 2
    assert "Loved the launch" in fake_ai.calls[0][1] and "Test User" in fake_ai.calls[0][1]   # real name, not blank
    assert app.followup_scheduled_at is not None


@pytest.mark.parametrize("status", ["DRAFT", "READY", "REPLIED", "REJECTED"])
async def test_schedule_rejected_when_not_awaiting_reply(db, fake_ai, make_profile, make_app, status):
    await make_profile()
    app = await make_app(status)
    with pytest.raises(BadRequestError):
        await svc.schedule_followup(db, app.id)


async def test_schedule_requires_profile(db, fake_ai, make_app):
    app = await make_app("SENT")
    with pytest.raises(BadRequestError):
        await svc.schedule_followup(db, app.id)


async def test_sequence_numbers_and_max_three(db, fake_ai, fake_gmail, make_profile, make_app):
    await make_profile()
    app = await make_app("SENT")
    seqs = []
    for _ in range(3):
        fu = await svc.schedule_followup(db, app.id)
        seqs.append(fu.sequence_number)
        await svc.send_followup(db, fu.id)
    assert seqs == [1, 2, 3]
    with pytest.raises(ConflictError, match="Maximum"):
        await svc.schedule_followup(db, app.id)


async def test_cannot_double_schedule(db, fake_ai, make_profile, make_app):
    await make_profile()
    app = await make_app("SENT")
    await svc.schedule_followup(db, app.id)
    with pytest.raises(ConflictError, match="already scheduled"):
        await svc.schedule_followup(db, app.id)


async def test_cancelled_followups_do_not_use_up_the_cap(db, fake_ai, make_profile, make_app):
    await make_profile()
    app = await make_app("SENT")
    for _ in range(5):                         # schedule + cancel repeatedly
        fu = await svc.schedule_followup(db, app.id)
        assert fu.sequence_number == 1 and await svc.cancel_followup(db, fu.id)


async def test_get_due_only_returns_pending_past_items(db, make_app, make_followup):
    a, b, c = await make_app("SENT"), await make_app("SENT", company_name="B"), await make_app("SENT", company_name="C")
    due = await make_followup(a, due=True)
    await make_followup(b, due=False)
    await make_followup(c, due=True, status="cancelled")
    assert [f.id for f in await svc.get_due_followups(db)] == [due.id]


async def test_check_due_marks_application_follow_up_due(db, make_app, make_followup):
    sent, replied = await make_app("SENT"), await make_app("REPLIED", company_name="Other")
    await make_followup(sent)
    await make_followup(replied)
    await svc.check_due(db)
    await db.refresh(sent)
    await db.refresh(replied)
    assert sent.status == "FOLLOW_UP_DUE" and replied.status == "REPLIED"


async def test_check_due_is_idempotent(db, make_app, make_followup):
    app = await make_app("SENT")
    await make_followup(app)
    await svc.check_due(db)
    await svc.check_due(db)
    await db.refresh(app)
    assert app.status == "FOLLOW_UP_DUE"


async def test_send_followup_threads_and_updates_state(db, fake_gmail, make_profile, make_app, make_followup):
    await make_profile()
    app = await make_app("SENT")
    fu = await make_followup(app)
    await svc.send_followup(db, fu.id)
    await db.refresh(app)
    assert fu.status == "sent" and fu.sent_at and app.status == "FOLLOW_UP_SENT" and app.followup_count == 1
    assert fake_gmail.sent[0]["thread_id"] == "thread-0" and fake_gmail.sent[0]["to"] == "careers@acme.com"


async def test_second_followup_cycles_through_due(db, fake_gmail, make_profile, make_app, make_followup):
    await make_profile()
    app = await make_app("FOLLOW_UP_SENT", followup_count=1)
    fu = await make_followup(app, seq=2)
    await svc.send_followup(db, fu.id)
    await db.refresh(app)
    assert app.status == "FOLLOW_UP_SENT" and app.followup_count == 2


async def test_send_twice_conflicts(db, fake_gmail, make_profile, make_app, make_followup):
    await make_profile()
    fu = await make_followup(await make_app("SENT"))
    await svc.send_followup(db, fu.id)
    with pytest.raises(ConflictError):
        await svc.send_followup(db, fu.id)


async def test_send_requires_gmail(db, make_profile, make_app, make_followup):
    await make_profile(gmail_connected=False)
    fu = await make_followup(await make_app("SENT"))
    with pytest.raises(GmailNotConnectedError):
        await svc.send_followup(db, fu.id)


async def test_send_failure_leaves_state_untouched(db, fake_gmail, make_profile, make_app, make_followup):
    await make_profile()
    app = await make_app("SENT")
    fu = await make_followup(app)
    fake_gmail.fail_send = True
    with pytest.raises(GmailSendError):
        await svc.send_followup(db, fu.id)
    await db.refresh(app)
    await db.refresh(fu)
    assert fu.status == "pending" and fu.sent_at is None and app.status == "SENT"      # retryable


async def test_send_unknown_followup(db):
    with pytest.raises(NotFoundError):
        await svc.send_followup(db, "nope")


async def test_cancel(db, make_app, make_followup):
    fu = await make_followup(await make_app("SENT"))
    assert await svc.cancel_followup(db, fu.id) is True
    assert await svc.cancel_followup(db, fu.id) is False        # already cancelled


async def test_mark_replied_cancels_pending(db, make_app, make_followup):
    app = await make_app("SENT")
    pending = await make_followup(app, due=False, seq=2)
    sent = await make_followup(app, status="sent", seq=1)
    await svc.mark_replied(db, app.id)
    await db.refresh(app)
    rows = {f.id: f.status for f in (await db.execute(select(FollowUp))).scalars()}
    assert app.status == "REPLIED" and app.reply_received and app.reply_received_at
    assert rows[pending.id] == "cancelled" and rows[sent.id] == "sent"


async def test_mark_replied_from_ready_is_illegal(db, make_app):
    app = await make_app("READY")
    with pytest.raises(InvalidTransitionError):
        await svc.mark_replied(db, app.id)


async def test_check_replies_detects_reply_in_thread(db, fake_gmail, make_profile, make_app, make_followup):
    await make_profile()
    waiting = await make_app("SENT", gmail_thread_id="t-reply")
    quiet = await make_app("SENT", gmail_thread_id="t-quiet", company_name="Quiet")
    await make_followup(waiting)
    fake_gmail.replied_threads.add("t-reply")
    assert await svc.check_replies(db) == [waiting.id]
    await db.refresh(waiting)
    await db.refresh(quiet)
    assert waiting.status == "REPLIED" and quiet.status == "SENT"


async def test_auto_send_due(db, fake_gmail, make_profile, make_app, make_followup):
    await make_profile()
    await make_followup(await make_app("SENT"))
    assert await svc.auto_send_due(db) == 1 and len(fake_gmail.sent) == 1
