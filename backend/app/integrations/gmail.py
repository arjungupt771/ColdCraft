"""Gmail transport. Pure functions over a token dict — no DB, no encryption (see profile_service).
All Google client calls are blocking; callers should use asyncio.to_thread."""
import base64
import logging
import secrets
import time
from email.message import EmailMessage
from email.policy import SMTP
from typing import Optional

from app.core.config import settings
from app.core.errors import BadRequestError, GmailAuthError, GmailSendError

logger = logging.getLogger(__name__)
SCOPES = ["https://www.googleapis.com/auth/gmail.send", "https://www.googleapis.com/auth/gmail.readonly", "openid", "email"]

_pending_states: dict[str, float] = {}      # OAuth `state` values → expiry (CSRF protection)
_STATE_TTL = 600


def _flow():
    from google_auth_oauthlib.flow import Flow
    return Flow.from_client_config(
        {"web": {"client_id": settings.GMAIL_CLIENT_ID, "client_secret": settings.GMAIL_CLIENT_SECRET,
                 "auth_uri": "https://accounts.google.com/o/oauth2/auth", "token_uri": "https://oauth2.googleapis.com/token",
                 "redirect_uris": [settings.GMAIL_REDIRECT_URI]}},
        scopes=SCOPES, redirect_uri=settings.GMAIL_REDIRECT_URI)


def get_auth_url() -> str:
    now = time.time()
    for s in [s for s, exp in _pending_states.items() if exp < now]:
        _pending_states.pop(s, None)
    state = secrets.token_urlsafe(24)
    _pending_states[state] = now + _STATE_TTL
    url, _ = _flow().authorization_url(access_type="offline", prompt="consent", state=state)
    return url


def consume_state(state: Optional[str]) -> bool:
    exp = _pending_states.pop(state or "", None)
    return exp is not None and exp >= time.time()


def exchange_code(code: str) -> dict:
    flow = _flow()
    flow.fetch_token(code=code)
    c = flow.credentials
    return {"token": c.token, "refresh_token": c.refresh_token, "token_uri": c.token_uri,
            "client_id": c.client_id, "client_secret": c.client_secret, "scopes": list(c.scopes)}


def _build_service(token_dict: dict):
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
    creds = Credentials(
        token=token_dict.get("token"), refresh_token=token_dict.get("refresh_token"),
        token_uri=token_dict.get("token_uri", "https://oauth2.googleapis.com/token"),
        client_id=token_dict.get("client_id"), client_secret=token_dict.get("client_secret"),
        scopes=token_dict.get("scopes", SCOPES))
    return build("gmail", "v1", credentials=creds, cache_discovery=False)


def get_user_email(token_dict: dict) -> Optional[str]:
    try:
        return _build_service(token_dict).users().getProfile(userId="me").execute().get("emailAddress")
    except Exception as e:
        logger.error("Gmail profile error: %s", e)
        return None


def send_email(token_dict: dict, to: str, subject: str, body: str, thread_id: Optional[str] = None) -> tuple[str, str]:
    """Returns (message_id, thread_id). Raises GmailAuthError / GmailSendError (never a raw SDK error)."""
    msg = EmailMessage(policy=SMTP)
    try:
        msg["To"] = to                       # SMTP policy rejects CR/LF → no header injection
        msg["Subject"] = subject
    except ValueError:
        raise BadRequestError("Recipient or subject contains invalid characters")
    msg.set_content(body)
    payload = {"raw": base64.urlsafe_b64encode(msg.as_bytes()).decode()}
    if thread_id:
        payload["threadId"] = thread_id
    try:
        result = _build_service(token_dict).users().messages().send(userId="me", body=payload).execute()
    except Exception as e:
        raise _map_error(e) from e
    return result["id"], result.get("threadId", "")


def _map_error(e: Exception) -> Exception:
    from google.auth.exceptions import RefreshError
    from googleapiclient.errors import HttpError
    if isinstance(e, RefreshError):
        return GmailAuthError()
    if isinstance(e, HttpError):
        status = getattr(e.resp, "status", 0)
        text = str(e).lower()
        if status == 401 or (status == 403 and "rate" not in text and "quota" not in text):
            return GmailAuthError()
        if status in (403, 429):
            return GmailSendError("Gmail rate limit reached — wait a few minutes and retry.")
        if status == 400:
            return GmailSendError("Gmail rejected the message (check the recipient address).")
        return GmailSendError("Gmail had a server problem.", ambiguous=True)
    return GmailSendError("Could not reach Gmail.", ambiguous=True)


def thread_has_reply(token_dict: dict, thread_id: str, my_email: str) -> bool:
    """True if the thread contains a message not sent by `my_email`."""
    svc = _build_service(token_dict)
    thread = svc.users().threads().get(userId="me", id=thread_id, format="metadata", metadataHeaders=["From"]).execute()
    me = (my_email or "").lower()
    for m in thread.get("messages", []):
        sender = next((h["value"] for h in m.get("payload", {}).get("headers", []) if h["name"].lower() == "from"), "")
        if me and me not in sender.lower():
            return True
    return False
