"""API-token auth + at-rest encryption for OAuth tokens."""
import json
import logging
import secrets
from pathlib import Path
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken
from fastapi import Header, HTTPException

from app.core.config import settings

logger = logging.getLogger(__name__)
_KEY_FILE = Path(".coldcraft_fernet.key")   # dev only; git-ignored
_fernet: Optional[Fernet] = None


async def require_api_token(x_api_token: Optional[str] = Header(default=None)) -> None:
    """Reject requests without the shared token. Disabled when API_TOKEN is empty (dev)."""
    if not settings.API_TOKEN:
        return
    if not x_api_token or not secrets.compare_digest(x_api_token, settings.API_TOKEN):
        raise HTTPException(status_code=401, detail="Invalid or missing API token")


def _get_fernet() -> Fernet:
    global _fernet
    if _fernet is None:
        key = settings.TOKEN_ENCRYPTION_KEY
        if not key:
            if _KEY_FILE.exists():
                key = _KEY_FILE.read_text().strip()
            else:
                key = Fernet.generate_key().decode()
                _KEY_FILE.write_text(key)
                logger.warning("Generated dev encryption key at %s — set TOKEN_ENCRYPTION_KEY in production", _KEY_FILE)
        _fernet = Fernet(key.encode() if isinstance(key, str) else key)
    return _fernet


def reset_fernet_cache() -> None:
    global _fernet
    _fernet = None


def encrypt_json(data: dict) -> str:
    return _get_fernet().encrypt(json.dumps(data).encode()).decode()


def decrypt_json(blob: str) -> dict:
    try:
        return json.loads(_get_fernet().decrypt(blob.encode()).decode())
    except InvalidToken as e:
        raise ValueError("Stored token cannot be decrypted (key changed?). Reconnect Gmail.") from e
