import base64
import io

import pytest
from cryptography.fernet import Fernet
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from PIL import Image

from app.core import security, uploads
from app.core.config import Settings, settings
from app.core.errors import UploadError
from app.core.middleware import MaxBodySizeMiddleware, RateLimitMiddleware, SecurityHeadersMiddleware
from app.integrations import web


def b64_image(fmt="PNG", size=(32, 32)):
    buf = io.BytesIO()
    Image.new("RGB", size).save(buf, fmt)
    return base64.b64encode(buf.getvalue()).decode()


# ── token encryption ──
def test_encrypt_roundtrip_and_ciphertext_hides_secret():
    token = {"token": "abc", "refresh_token": "SECRET-REFRESH"}
    blob = security.encrypt_json(token)
    assert "SECRET-REFRESH" not in blob and security.decrypt_json(blob) == token


def test_decrypt_with_wrong_key_gives_actionable_error(monkeypatch):
    blob = security.encrypt_json({"a": 1})
    monkeypatch.setattr(settings, "TOKEN_ENCRYPTION_KEY", Fernet.generate_key().decode())
    security.reset_fernet_cache()
    try:
        with pytest.raises(ValueError, match="Reconnect Gmail"):
            security.decrypt_json(blob)
    finally:
        monkeypatch.undo()
        security.reset_fernet_cache()


# ── API token ──
async def test_api_token_dependency(monkeypatch):
    monkeypatch.setattr(settings, "API_TOKEN", "")
    assert await security.require_api_token(None) is None                      # disabled in dev
    monkeypatch.setattr(settings, "API_TOKEN", "s3cret")
    assert await security.require_api_token("s3cret") is None
    for bad in (None, "", "wrong"):
        with pytest.raises(HTTPException) as e:
            await security.require_api_token(bad)
        assert e.value.status_code == 401


# ── settings ──
def test_production_refuses_missing_secrets():
    with pytest.raises(ValueError, match="SECRET_KEY"):
        Settings(_env_file=None, APP_ENV="production")
    ok = Settings(_env_file=None, APP_ENV="production", SECRET_KEY="k", API_TOKEN="t", TOKEN_ENCRYPTION_KEY="e")
    assert ok.SECRET_KEY == "k"


def test_dev_secret_is_random_not_hardcoded():
    a, b = Settings(_env_file=None, APP_ENV="development"), Settings(_env_file=None, APP_ENV="development")
    assert a.SECRET_KEY and a.SECRET_KEY != "dev-secret" and a.SECRET_KEY != b.SECRET_KEY


# ── uploads ──
@pytest.mark.parametrize("fmt", ["PNG", "JPEG", "WEBP"])
def test_valid_images_accepted(fmt):
    raw, mime = uploads.validate_image_b64(b64_image(fmt))
    assert raw and mime == {"PNG": "image/png", "JPEG": "image/jpeg", "WEBP": "image/webp"}[fmt]


def test_data_url_prefix_tolerated():
    assert uploads.validate_image_b64("data:image/png;base64," + b64_image())[1] == "image/png"


@pytest.mark.parametrize("payload", [
    "!!!not base64!!!", base64.b64encode(b"just text, definitely not an image").decode(),
    b64_image("GIF"), b64_image("BMP"),
])
def test_bad_uploads_rejected(payload):
    with pytest.raises(UploadError):
        uploads.validate_image_b64(payload)


def test_oversized_upload_rejected(monkeypatch):
    monkeypatch.setattr(settings, "MAX_UPLOAD_BYTES", 100)
    with pytest.raises(UploadError, match="too large"):
        uploads.validate_image_b64(b64_image(size=(200, 200)))


def test_claimed_png_with_html_payload_rejected():
    with pytest.raises(UploadError):
        uploads.validate_image_b64(base64.b64encode(b"<script>alert(1)</script>").decode())


# ── middleware ──
def _app(*middlewares):
    a = FastAPI()
    for m in middlewares:
        a.add_middleware(m)

    @a.get("/x")
    def x():
        return {"ok": True}

    @a.post("/p")
    def p(data: dict):
        return {"ok": True}
    return TestClient(a)


def test_security_headers():
    r = _app(SecurityHeadersMiddleware).get("/x")
    assert r.headers["x-content-type-options"] == "nosniff" and r.headers["x-frame-options"] == "DENY"
    assert "frame-ancestors" in r.headers["content-security-policy"]


def test_rate_limit(monkeypatch):
    monkeypatch.setattr(settings, "RATE_LIMIT_PER_MINUTE", 3)
    c = _app(RateLimitMiddleware)
    codes = [c.get("/x").status_code for _ in range(5)]
    assert codes == [200, 200, 200, 429, 429]
    assert c.get("/x").headers["retry-after"] == "60"


def test_body_size_cap(monkeypatch):
    monkeypatch.setattr(settings, "MAX_REQUEST_BYTES", 50)
    c = _app(MaxBodySizeMiddleware)
    assert c.post("/p", json={"a": "x" * 500}).status_code == 413
    assert c.post("/p", json={"a": "x"}).status_code == 200


# ── SSRF guard ──
@pytest.mark.parametrize("url", ["http://127.0.0.1/admin", "http://localhost:8000", "http://169.254.169.254/latest/meta-data",
                                 "http://10.0.0.5/x", "ftp://example.com/file", "file:///etc/passwd"])
def test_non_public_urls_blocked(url):
    with pytest.raises(ValueError):
        web.assert_public_url(url)


def test_html_to_text_strips_scripts_and_entities():
    assert web.html_to_text("<script>evil()</script><p>Tom &amp; Jerry</p><style>p{}</style>") == "Tom & Jerry"
