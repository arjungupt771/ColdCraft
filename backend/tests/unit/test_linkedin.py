import pytest

from app.core.errors import BadRequestError
from app.integrations import linkedin, web

WALL = "<html><body>Sign in to LinkedIn. Join now to see who you already know. Create your free account to view this job.</body></html>"
JOB = ("<html><body><h1>Backend Engineer</h1><p>About the job: build APIs.</p><p>Responsibilities include design and review.</p>"
       "<p>Requirements: 3 years of experience with Python. Skills: FastAPI. Apply now. " + "More detail. " * 20 + "</p></body></html>")


@pytest.fixture(autouse=True)
def _public(monkeypatch):
    monkeypatch.setattr(web, "assert_public_url", lambda url: None)


def serve(monkeypatch, html):
    async def fake(url, timeout=15.0):
        return html
    monkeypatch.setattr(web, "fetch_html", fake)


async def test_login_wall_gets_actionable_error(monkeypatch):
    serve(monkeypatch, WALL * 3)
    with pytest.raises(BadRequestError, match="screenshot"):
        await linkedin.fetch_job_page_text("linkedin.com/jobs/view/1")


async def test_real_job_page_passes(monkeypatch):
    serve(monkeypatch, JOB)
    url, text = await linkedin.fetch_job_page_text("careers.acme.com/job/1")
    assert url == "https://careers.acme.com/job/1" and "Backend Engineer" in text


async def test_real_job_page_is_not_truncated_before_extraction(monkeypatch):
    serve(monkeypatch, "<html>job posting</html>")
    monkeypatch.setattr(
        web,
        "html_to_text",
        lambda html: "Responsibilities and requirements. " + "x" * 15000,
    )

    _, text = await linkedin.fetch_job_page_text("careers.acme.com/job/1")

    assert len(text) > 12000


async def test_empty_fetch(monkeypatch):
    serve(monkeypatch, "")
    with pytest.raises(BadRequestError, match="Could not fetch"):
        await linkedin.fetch_job_page_text("https://x.com/job")
