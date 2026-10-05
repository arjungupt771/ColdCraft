from pydantic import BaseModel, Field, field_validator
from typing import Literal
from typing import Optional, List
from datetime import datetime


class ProfileUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    linkedin: Optional[str] = None
    resume_text: Optional[str] = None
    skills: Optional[List[str]] = None
    experience_years: Optional[int] = None
    tone: Optional[Literal["professional", "friendly", "concise"]] = None


class ProfileOut(BaseModel):
    id: str
    name: str
    email: str
    phone: str
    linkedin: str
    resume_text: str
    skills: List[str]
    experience_years: int
    tone: str
    gmail_connected: bool = False

    class Config:
        from_attributes = True


class ProcessScreenshotRequest(BaseModel):
    image_base64: str = Field(min_length=100)
    image_type: str = "png"


class ProcessLinkedInRequest(BaseModel):
    url: str = Field(min_length=4, max_length=2048)


class GenerateEmailRequest(BaseModel):
    application_id: str
    regenerate: bool = False


_EMAIL_RE = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"


class SendEmailRequest(BaseModel):
    application_id: str
    recipient_email: str = Field(pattern=_EMAIL_RE, max_length=254)
    subject: str = Field(min_length=1, max_length=200)
    body: str = Field(min_length=1, max_length=10000)
    confirm_unverified: bool = False      # required when the recipient is an unconfirmed careers@ guess

    @field_validator("recipient_email", "subject")
    @classmethod
    def _no_header_injection(cls, v: str) -> str:
        if "\r" in v or "\n" in v:
            raise ValueError("must not contain line breaks")
        return v.strip()


class JobUpdate(BaseModel):
    """Edits to the extracted job, allowed only while the application is still DRAFT."""
    company_name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    role_title: Optional[str] = Field(default=None, min_length=1, max_length=200)
    jd_text: Optional[str] = Field(default=None, min_length=1, max_length=12000)
    required_skills: Optional[List[str]] = Field(default=None, max_length=40)
    company_website: Optional[str] = Field(default=None, max_length=300)
    recipient_name: Optional[str] = Field(default=None, max_length=120)
    recipient_email: Optional[str] = Field(default=None, pattern=_EMAIL_RE, max_length=254)

    @field_validator("company_name", "role_title", "jd_text", "recipient_name", "company_website")
    @classmethod
    def _strip(cls, v):
        return v.strip() if isinstance(v, str) else v


class DraftUpdate(BaseModel):
    subject: Optional[str] = Field(default=None, max_length=200)
    body: Optional[str] = Field(default=None, max_length=10000)
    recipient_email: Optional[str] = Field(default=None, pattern=_EMAIL_RE, max_length=254)
    notes: Optional[str] = Field(default=None, max_length=5000)


class StatusUpdate(BaseModel):
    status: Literal["INTERVIEW", "REJECTED", "WITHDRAWN"]


class FollowUpOut(BaseModel):
    id: str
    application_id: str
    scheduled_at: datetime
    sent_at: Optional[datetime]
    subject: Optional[str]
    body: Optional[str]
    status: str
    sequence_number: int

    class Config:
        from_attributes = True


class ScheduleFollowUpRequest(BaseModel):
    application_id: str
    days_after_send: int = Field(default=5, ge=1, le=60)
    custom_note: Optional[str] = Field(default=None, max_length=500)


class ApplicationOut(BaseModel):
    id: str
    company_name: str
    role_title: str
    jd_text: str
    company_research: str
    required_skills: List[str]
    source: str
    linkedin_job_url: Optional[str]
    recipient_email: Optional[str]
    recipient_name: Optional[str]
    recipient_source: Optional[str] = None
    email_subject: Optional[str]
    email_body: Optional[str]
    ai_provider_used: str
    prompt_version: Optional[str] = None
    email_confidence: Optional[float] = None
    last_error: Optional[str] = None
    company_website: Optional[str] = None
    status: str
    sent_at: Optional[datetime]
    followup_scheduled_at: Optional[datetime]
    followup_sent_at: Optional[datetime]
    followup_count: int
    reply_received: bool
    notes: str
    created_at: datetime

    class Config:
        from_attributes = True


class GmailAuthURL(BaseModel):
    auth_url: str


class GmailStatus(BaseModel):
    connected: bool
    email: Optional[str] = None


class HealthOut(BaseModel):
    status: str
    version: str
