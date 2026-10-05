"""Shared fixtures. Environment is configured BEFORE the app is imported."""
import base64
import io
import json
import os
import re
import time

from cryptography.fernet import Fernet

os.environ.update(
    APP_ENV="test", API_TOKEN="", AUTO_MIGRATE="false", INPROCESS_SCHEDULER="false",
    DATABASE_URL="sqlite+aiosqlite://", TOKEN_ENCRYPTION_KEY=Fernet.generate_key().decode(),
    GROQ_API_KEY="test", RATE_LIMIT_PER_MINUTE="100000", RATE_LIMIT_AI_PER_MINUTE="100000",
)

from datetime import datetime, timedelta, timezone  # noqa: E402

import httpx  # noqa: E402
import pytest  # noqa: E402
import pytest_asyncio  # noqa: E402
from PIL import Image  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from app.ai import client as ai_client_module  # noqa: E402
from app.ai.client import AIClient  # noqa: E402
from app.ai.providers.base import AIProvider  # noqa: E402
from app.core.config import settings  # noqa: E402
from app.core.database import Base, get_db  # noqa: E402
from app.core.security import encrypt_json  # noqa: E402
from app.integrations import gmail, web  # noqa: E402
from app.main import app as fastapi_app  # noqa: E402
from app.models.models import FollowUp, JobApplication, UserProfile  # noqa: E402

# ── canned model outputs ───────────────────────────────
JOB = {"company_name": "Acme", "role_title": "Backend Engineer", "jd_text": "Build and scale payment APIs with Python.",
       "required_skills": ["Python", "FastAPI"], "company_website": "acme.com", "recipient_name": None}
RESEARCH = {"summary": "Acme builds payment infrastructure for small businesses and values engineering rigor and ownership.",
            "highlights": ["Open-sourced its ledger service"]}
EMAIL_BODY = ("{greeting}\n\nI have followed Acme's work on payment infrastructure and built similar FastAPI services in Python "
              "that handle real production traffic. Your posting for a Backend Engineer describes building and scaling payment APIs, "
              "which is exactly the kind of work I enjoy and have practised through several projects. I would welcome a short "
              "conversation about how I could contribute to your team and what the first few months might look like.\n\n"
              "Best regards,\nTest User\ntest@example.com")
EMAIL = {"subject": "Backend Engineer — Python & FastAPI",
         "body": EMAIL_BODY.format(greeting="Dear Hiring Manager,"), "confidence": 0.9}
FOLLOWUP = {"subject": "Following up — Backend Engineer at Acme",
            "body": "Dear Hiring Manager,\n\nJust following up on my application.\n\nBest regards,\nTest User\ntest@example.com"}


def default_handler(prompt: str, system: str):
    s = system.lower()
    if "screenshots of job postings" in s or "job description parser" in s:
        return json.dumps(JOB)
    if "research assistant" in s:
        return json.dumps(RESEARCH)
    if "career coach" in s:
        m = re.search(r"must start with: (.+)", prompt)       # echo the greeting we asked for
        return json.dumps(dict(EMAIL, body=EMAIL_BODY.format(greeting=m.group(1).strip() if m else "Dear Hiring Manager,")))
    if "follow-up" in s:
        return json.dumps(FOLLOWUP)
    return "ok"


class FakeProvider(AIProvider):
    supports_vision = True

    def __init__(self, handler=default_handler, name="fake", vision=True):
        self.name, self.handler, self.supports_vision, self.calls = name, handler, vision, []

    def is_configured(self) -> bool:
        return True

    async def generate(self, prompt, system="", max_tokens=1024, temperature=0.7):
        self.calls.append(("text", prompt, system))
        out = self.handler(prompt, system)
        if isinstance(out, Exception):
            raise out
        return out

    async def generate_vision(self, image_bytes, mime_type, prompt):
        self.calls.append(("vision", prompt, ""))
        out = self.handler(prompt, "screenshots of job postings")
        if isinstance(out, Exception):
            raise out
        return out


async def _no_sleep(_):
    return None


def make_client(*providers) -> AIClient:
    return AIClient(providers=list(providers), sleep=_no_sleep)


@pytest.fixture
def fake_ai():
    provider = FakeProvider()
    ai_client_module.set_client(make_client(provider))
    yield provider
    ai_client_module.set_client(None)


# ── database ───────────────────────────────────────────
@pytest_asyncio.fixture
async def engine():
    eng = create_async_engine("sqlite+aiosqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def db(engine):
    async with async_sessionmaker(engine, expire_on_commit=False)() as session:
        yield session


@pytest_asyncio.fixture
async def client(engine, fake_ai, fake_gmail, fake_web):
    maker = async_sessionmaker(engine, expire_on_commit=False)

    async def override():
        async with maker() as s:
            try:
                yield s
                await s.commit()
            except Exception:
                await s.rollback()
                raise

    fastapi_app.dependency_overrides[get_db] = override
    transport = httpx.ASGITransport(app=fastapi_app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    fastapi_app.dependency_overrides.clear()


# ── external systems ───────────────────────────────────
class FakeGmail:
    def __init__(self):
        self.sent, self.replied_threads, self.fail_send = [], set(), False
        self.delay, self.error = 0.0, None        # delay: widen the race window; error: raise this instead

    def send_email(self, token, to, subject, body, thread_id=None):
        if self.delay:
            time.sleep(self.delay)
        if self.error:
            raise self.error
        if self.fail_send:
            raise RuntimeError("gmail down")
        self.sent.append({"to": to, "subject": subject, "body": body, "thread_id": thread_id})
        return f"msg-{len(self.sent)}", thread_id or f"thread-{len(self.sent)}"

    def thread_has_reply(self, token, thread_id, my_email):
        return thread_id in self.replied_threads


@pytest.fixture
def fake_gmail(monkeypatch):
    g = FakeGmail()
    monkeypatch.setattr(gmail, "send_email", g.send_email)
    monkeypatch.setattr(gmail, "thread_has_reply", g.thread_has_reply)
    monkeypatch.setattr(gmail, "get_user_email", lambda token: "test@example.com")
    monkeypatch.setattr(gmail, "exchange_code", lambda code: {"token": "tok", "refresh_token": "ref-SECRET"})
    return g


@pytest.fixture
def fake_web(monkeypatch):
    """No real network: wiki/site lookups return nothing, job pages return canned text."""
    async def snippet(url, limit=2000):
        return "Acme is a payments company."

    async def wiki(title):
        return ""

    async def job_page(url, max_chars=4000):
        return url if url.startswith("http") else "https://" + url, "Backend Engineer at Acme. " * 20

    monkeypatch.setattr(web, "fetch_snippet", snippet)
    monkeypatch.setattr(web, "wikipedia_extract", wiki)
    from app.services import application_pipeline
    monkeypatch.setattr(application_pipeline, "fetch_job_page_text", job_page)


@pytest.fixture
def png_b64() -> str:
    buf = io.BytesIO()
    Image.new("RGB", (64, 64), "white").save(buf, "PNG")
    return base64.b64encode(buf.getvalue()).decode()


# ── factories ──────────────────────────────────────────
@pytest_asyncio.fixture
async def make_profile(db):
    async def _make(gmail_connected=True, **kw):
        values = dict(name="Test User", email="test@example.com", skills=["Python", "FastAPI"], experience_years=3,
                      resume_text="Built APIs.", tone="professional")
        values.update(kw)
        p = UserProfile(**values)
        if gmail_connected:
            p.gmail_token_enc = encrypt_json({"token": "tok", "refresh_token": "ref"})
        db.add(p)
        await db.commit()
        await db.refresh(p)
        return p
    return _make


@pytest_asyncio.fixture
async def make_app(db):
    async def _make(status="READY", **kw):
        values = dict(company_name="Acme", role_title="Backend Engineer", jd_text="Build APIs", required_skills=["Python"],
                      company_research="Acme builds payments.", recipient_email="careers@acme.com", source="linkedin_url",
                      status=status)
        if status in ("SENT", "FOLLOW_UP_DUE", "FOLLOW_UP_SENT"):
            values.update(sent_at=datetime.now(timezone.utc) - timedelta(days=6), gmail_thread_id="thread-0",
                          email_subject="Hi", email_body="Body")
        values.update(kw)
        a = JobApplication(**values)
        db.add(a)
        await db.commit()
        await db.refresh(a)
        return a
    return _make


@pytest_asyncio.fixture
async def make_followup(db):
    async def _make(app, due=True, status="pending", seq=1):
        fu = FollowUp(application_id=app.id, status=status, sequence_number=seq, subject="Following up", body="Body text here.",
                      scheduled_at=datetime.now(timezone.utc) + timedelta(days=-1 if due else 3))
        db.add(fu)
        await db.commit()
        await db.refresh(fu)
        return fu
    return _make
