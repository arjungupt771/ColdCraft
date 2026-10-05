"""v2.1: explicit application states, prompt tracking, encrypted Gmail tokens.

 - job_applications: status strings → state-machine values; add prompt_version, email_confidence, last_error
 - followups: add prompt_version
 - user_profile: gmail_token (plaintext JSON) → gmail_token_enc (Fernet-encrypted text)

Revision ID: 0002
Revises: 0001
"""
import json

from alembic import op
import sqlalchemy as sa

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

STATUS_MAP = {
    "researched": "READY", "draft": "READY", "sent": "SENT", "replied": "REPLIED",
    "closed": "WITHDRAWN", "failed": "DRAFT",
}
REVERSE_MAP = {
    "DRAFT": "draft", "RESEARCHING": "draft", "READY": "draft", "SENT": "sent", "FOLLOW_UP_DUE": "sent",
    "FOLLOW_UP_SENT": "sent", "REPLIED": "replied", "INTERVIEW": "replied", "REJECTED": "closed", "WITHDRAWN": "closed",
}


def _columns(table: str) -> set[str]:
    return {c["name"] for c in sa.inspect(op.get_bind()).get_columns(table)}


def upgrade() -> None:
    bind = op.get_bind()

    app_cols = _columns("job_applications")
    with op.batch_alter_table("job_applications") as batch:
        if "prompt_version" not in app_cols:
            batch.add_column(sa.Column("prompt_version", sa.String, nullable=True))
        if "email_confidence" not in app_cols:
            batch.add_column(sa.Column("email_confidence", sa.Float, nullable=True))
        if "last_error" not in app_cols:
            batch.add_column(sa.Column("last_error", sa.Text, nullable=True))

    if "prompt_version" not in _columns("followups"):
        with op.batch_alter_table("followups") as batch:
            batch.add_column(sa.Column("prompt_version", sa.String, nullable=True))

    for old, new in STATUS_MAP.items():
        bind.execute(sa.text("UPDATE job_applications SET status = :new WHERE status = :old"), {"new": new, "old": old})
    bind.execute(sa.text("UPDATE job_applications SET status = 'DRAFT' WHERE status IS NULL"))
    with op.batch_alter_table("job_applications") as batch:
        batch.alter_column("status", existing_type=sa.String, nullable=False, server_default="DRAFT")
        batch.create_index("ix_job_applications_status", ["status"])

    # Move OAuth credentials from plaintext JSON to an encrypted column.
    profile_cols = _columns("user_profile")
    if "gmail_token_enc" not in profile_cols:
        with op.batch_alter_table("user_profile") as batch:
            batch.add_column(sa.Column("gmail_token_enc", sa.Text, nullable=True))
    if "gmail_token" in profile_cols:
        from app.core.security import encrypt_json
        rows = bind.execute(sa.text("SELECT id, gmail_token FROM user_profile WHERE gmail_token IS NOT NULL")).fetchall()
        for row_id, raw in rows:
            try:
                token = json.loads(raw) if isinstance(raw, str) else raw
            except (TypeError, ValueError):
                token = None
            if isinstance(token, dict) and token:
                bind.execute(sa.text("UPDATE user_profile SET gmail_token_enc = :enc WHERE id = :id"),
                             {"enc": encrypt_json(token), "id": row_id})
        with op.batch_alter_table("user_profile") as batch:
            batch.drop_column("gmail_token")


def downgrade() -> None:
    bind = op.get_bind()
    # Tokens are NOT decrypted back to plaintext on downgrade: the user simply reconnects Gmail.
    with op.batch_alter_table("user_profile") as batch:
        batch.add_column(sa.Column("gmail_token", sa.JSON, nullable=True))
        batch.drop_column("gmail_token_enc")

    with op.batch_alter_table("job_applications") as batch:
        batch.drop_index("ix_job_applications_status")
        batch.alter_column("status", existing_type=sa.String, nullable=True, server_default=None)
    for new, old in REVERSE_MAP.items():
        bind.execute(sa.text("UPDATE job_applications SET status = :old WHERE status = :new"), {"new": new, "old": old})
    with op.batch_alter_table("job_applications") as batch:
        batch.drop_column("last_error")
        batch.drop_column("email_confidence")
        batch.drop_column("prompt_version")
    with op.batch_alter_table("followups") as batch:
        batch.drop_column("prompt_version")
