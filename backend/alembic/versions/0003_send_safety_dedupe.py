"""v2.2: recipient provenance + one-live-follow-up-per-application guard.

 - job_applications.recipient_source  ('hunter' | 'guess' | 'user'); NULL for existing rows
 - followups: partial unique index so an application can have only ONE pending/sending follow-up.
   Existing duplicates are resolved first (earliest kept, the rest cancelled) so the migration can't fail.

Revision ID: 0003
Revises: 0002
"""
from alembic import op
import sqlalchemy as sa

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    cols = {c["name"] for c in sa.inspect(bind).get_columns("job_applications")}
    if "recipient_source" not in cols:
        with op.batch_alter_table("job_applications") as batch:
            batch.add_column(sa.Column("recipient_source", sa.String, nullable=True))

    bind.execute(sa.text("""
        UPDATE followups SET status = 'cancelled'
        WHERE status IN ('pending', 'sending') AND id NOT IN (
            SELECT id FROM (
                SELECT id, ROW_NUMBER() OVER (PARTITION BY application_id ORDER BY sequence_number, scheduled_at) AS rn
                FROM followups WHERE status IN ('pending', 'sending')
            ) WHERE rn = 1
        )"""))
    existing = {i["name"] for i in sa.inspect(bind).get_indexes("followups")}
    if "uq_followups_one_active" not in existing:
        op.create_index("uq_followups_one_active", "followups", ["application_id"], unique=True,
                        sqlite_where=sa.text("status IN ('pending', 'sending')"))


def downgrade() -> None:
    op.drop_index("uq_followups_one_active", table_name="followups")
    with op.batch_alter_table("job_applications") as batch:
        batch.drop_column("recipient_source")
