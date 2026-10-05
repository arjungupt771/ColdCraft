"""Baseline: the v2.0 schema (created by Base.metadata.create_all before Alembic existed).

Idempotent on purpose: databases created by the old create_all() already have these tables,
so each table is only created when missing. Fresh installs get it created here.

Revision ID: 0001
Revises:
"""
from alembic import op
import sqlalchemy as sa

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    existing = set(sa.inspect(op.get_bind()).get_table_names())

    if "user_profile" not in existing:
        op.create_table(
            "user_profile",
            sa.Column("id", sa.String, primary_key=True),
            sa.Column("name", sa.String), sa.Column("email", sa.String), sa.Column("phone", sa.String),
            sa.Column("linkedin", sa.String), sa.Column("resume_text", sa.Text), sa.Column("skills", sa.JSON),
            sa.Column("experience_years", sa.Integer), sa.Column("tone", sa.String),
            sa.Column("gmail_token", sa.JSON, nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True)),
        )
    if "job_applications" not in existing:
        op.create_table(
            "job_applications",
            sa.Column("id", sa.String, primary_key=True),
            sa.Column("company_name", sa.String, nullable=False), sa.Column("role_title", sa.String, nullable=False),
            sa.Column("jd_text", sa.Text), sa.Column("required_skills", sa.JSON), sa.Column("company_research", sa.Text),
            sa.Column("source", sa.String), sa.Column("linkedin_job_url", sa.String, nullable=True),
            sa.Column("company_website", sa.String, nullable=True), sa.Column("screenshot_path", sa.String, nullable=True),
            sa.Column("recipient_email", sa.String, nullable=True), sa.Column("recipient_name", sa.String, nullable=True),
            sa.Column("email_subject", sa.String, nullable=True), sa.Column("email_body", sa.Text, nullable=True),
            sa.Column("ai_provider_used", sa.String), sa.Column("status", sa.String),
            sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("gmail_message_id", sa.String, nullable=True), sa.Column("gmail_thread_id", sa.String, nullable=True),
            sa.Column("followup_scheduled_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("followup_sent_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("followup_count", sa.Integer), sa.Column("reply_received", sa.Boolean),
            sa.Column("reply_received_at", sa.DateTime(timezone=True), nullable=True), sa.Column("notes", sa.Text),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True)),
        )
    if "followups" not in existing:
        op.create_table(
            "followups",
            sa.Column("id", sa.String, primary_key=True),
            sa.Column("application_id", sa.String, sa.ForeignKey("job_applications.id"), nullable=False),
            sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("subject", sa.String, nullable=True), sa.Column("body", sa.Text, nullable=True),
            sa.Column("status", sa.String), sa.Column("sequence_number", sa.Integer),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )


def downgrade() -> None:
    op.drop_table("followups")
    op.drop_table("job_applications")
    op.drop_table("user_profile")
