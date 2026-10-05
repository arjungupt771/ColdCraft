"""Pydantic models that every AI response must satisfy before it touches the database."""

import re
from typing import Optional

from pydantic import BaseModel, Field, field_validator


_JUNK = {
    "",
    "unknown",
    "null",
    "none",
    "n/a",
    "na",
    "undefined",
    "not provided",
    "not available",
    "could not be determined",
}

_PLACEHOLDER = re.compile(
    r"""
    \[
        (?:your|company|hiring|recipient|name|insert)[^\]]*
    \]
    |
    \{\{.*?\}\}
    |
    \{user_(?:name|email)\}
    """,
    re.IGNORECASE | re.VERBOSE,
)

_EMAIL = re.compile(
    r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$"
)


def _clean_optional(value):
    if value is None:
        return None

    value = str(value).strip()

    if value.lower() in _JUNK:
        return None

    return value


class ExtractedJob(BaseModel):
    company_name: Optional[str] = None
    role_title: Optional[str] = None
    jd_text: str = ""

    required_skills: list[str] = Field(default_factory=list)
    preferred_skills: list[str] = Field(default_factory=list)

    company_website: Optional[str] = None
    recipient_name: Optional[str] = None
    location: Optional[str] = None
    job_type: Optional[str] = None
    experience_required: Optional[str] = None
    salary: Optional[str] = None

    @field_validator("company_name", "role_title", mode="before")
    @classmethod
    def _required_text(cls, value):
        """
        Normalize missing values.

        Do NOT raise here. AI extraction is allowed to be incomplete.
        The pipeline decides whether company_name/role_title are required
        before continuing.
        """
        if value is None:
            return None

        value = str(value).strip()

        if value.lower() in _JUNK:
            return None

        return value[:200]

    @field_validator("jd_text", mode="before")
    @classmethod
    def _jd(cls, value):
        if not value:
            return ""

        return str(value).strip()[:12000]

    @field_validator(
        "required_skills",
        "preferred_skills",
        mode="before",
    )
    @classmethod
    def _skills(cls, value):
        if value is None:
            return []

        if isinstance(value, str):
            value = re.split(r"[,;\n]", value)

        result = []

        for skill in value:
            skill = str(skill).strip()

            if skill and skill.lower() not in _JUNK:
                result.append(skill)

        return result[:40]

    @field_validator(
        "company_website",
        "recipient_name",
        "location",
        "job_type",
        "experience_required",
        "salary",
        mode="before",
    )
    @classmethod
    def _optional_text(cls, value):
        return _clean_optional(value)


class CompanyResearch(BaseModel):
    summary: str = Field(min_length=40, max_length=2500)
    highlights: list[str] = Field(default_factory=list, max_length=8)

    @field_validator("highlights", mode="before")
    @classmethod
    def _highlights(cls, value):
        if not value:
            return []

        return [
            str(item).strip()
            for item in value
            if str(item).strip()
        ][:8]

    def as_text(self) -> str:
        if not self.highlights:
            return self.summary

        return self.summary + "\n" + "\n".join(
            f"- {highlight}"
            for highlight in self.highlights
        )


class GeneratedEmail(BaseModel):
    subject: str = Field(min_length=3, max_length=120)
    body: str = Field(min_length=60, max_length=2500)
    confidence: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
    )

    @field_validator("subject", mode="before")
    @classmethod
    def _subject(cls, value):
        return str(value or "").strip().strip("\"'")

    @field_validator("body", mode="before")
    @classmethod
    def _body(cls, value):
        return str(value or "").strip()

    @field_validator("body")
    @classmethod
    def _no_placeholders(cls, value):
        if _PLACEHOLDER.search(value):
            raise ValueError("body contains unfilled placeholders")

        if len(value.split()) > 260:
            raise ValueError(
                "body is too long for a cold email"
            )

        return value

    @field_validator("confidence", mode="before")
    @classmethod
    def _confidence(cls, value):
        try:
            number = float(value)
        except (TypeError, ValueError):
            return 0.5

        return number / 100 if number > 1 else number


class FollowUpEmail(BaseModel):
    subject: str = Field(min_length=3, max_length=140)
    body: str = Field(min_length=20, max_length=1200)

    @field_validator("body")
    @classmethod
    def _no_placeholders(cls, value):
        if _PLACEHOLDER.search(value):
            raise ValueError(
                "body contains unfilled placeholders"
            )

        return value.strip()


class RecruiterInfo(BaseModel):
    email: str
    name: Optional[str] = None
    source: str = "guess"
    verified: bool = False

    @field_validator("email")
    @classmethod
    def _email(cls, value):
        value = value.strip().lower()

        if not _EMAIL.match(value):
            raise ValueError("invalid email address")

        return value