from sqlalchemy import Column, String, Integer, Float, Boolean, DateTime, Text, JSON, ForeignKey, Index, text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import uuid
from app.core.database import Base


def gen_uuid():
    return str(uuid.uuid4())


class UserProfile(Base):
    __tablename__ = "user_profile"

    id = Column(String, primary_key=True, default=gen_uuid)
    name = Column(String, default="")
    email = Column(String, default="")
    phone = Column(String, default="")
    linkedin = Column(String, default="")
    resume_text = Column(Text, default="")
    skills = Column(JSON, default=[])
    experience_years = Column(Integer, default=0)
    tone = Column(String, default="professional")
    # Fernet-encrypted JSON blob of OAuth credentials (never plaintext)
    gmail_token_enc = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class JobApplication(Base):
    __tablename__ = "job_applications"

    id = Column(String, primary_key=True, default=gen_uuid)

    # Job details
    company_name = Column(String, nullable=False)
    role_title = Column(String, nullable=False)
    jd_text = Column(Text, default="")
    required_skills = Column(JSON, default=[])
    company_research = Column(Text, default="")
    source = Column(String, default="screenshot")   # screenshot | linkedin_url | manual

    # LinkedIn URL input (new)
    linkedin_job_url = Column(String, nullable=True)
    company_website = Column(String, nullable=True)
    screenshot_path = Column(String, nullable=True)

    # Generated email
    recipient_email = Column(String, nullable=True)
    recipient_name = Column(String, nullable=True)
    recipient_source = Column(String, nullable=True)     # hunter | guess | user
    email_subject = Column(String, nullable=True)
    email_body = Column(Text, nullable=True)
    ai_provider_used = Column(String, default="groq")
    prompt_version = Column(String, nullable=True)       # e.g. "email_generation@v1"
    email_confidence = Column(Float, nullable=True)      # model self-assessment, 0-1
    last_error = Column(Text, nullable=True)

    # Status
    status = Column(String, default="DRAFT", nullable=False, index=True)  # see app.domain.state_machine
    sent_at = Column(DateTime(timezone=True), nullable=True)
    gmail_message_id = Column(String, nullable=True)
    gmail_thread_id = Column(String, nullable=True)

    # Follow-up (new)
    followup_scheduled_at = Column(DateTime(timezone=True), nullable=True)
    followup_sent_at = Column(DateTime(timezone=True), nullable=True)
    followup_count = Column(Integer, default=0)
    reply_received = Column(Boolean, default=False)
    reply_received_at = Column(DateTime(timezone=True), nullable=True)
    notes = Column(Text, default="")

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    followups = relationship("FollowUp", back_populates="application", cascade="all, delete-orphan")


class FollowUp(Base):
    """Individual follow-up emails scheduled and sent."""
    __tablename__ = "followups"
    __table_args__ = (
        # At most ONE live (pending/sending) follow-up per application, enforced by the database.
        Index("uq_followups_one_active", "application_id", unique=True,
              sqlite_where=text("status IN ('pending', 'sending')")),
    )

    id = Column(String, primary_key=True, default=gen_uuid)
    application_id = Column(String, ForeignKey("job_applications.id"), nullable=False)
    scheduled_at = Column(DateTime(timezone=True), nullable=False)
    sent_at = Column(DateTime(timezone=True), nullable=True)
    subject = Column(String, nullable=True)
    body = Column(Text, nullable=True)
    status = Column(String, default="pending")   # pending | sending | sent | cancelled | failed
    sequence_number = Column(Integer, default=1)  # 1st followup, 2nd followup, etc.
    prompt_version = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    application = relationship("JobApplication", back_populates="followups")
