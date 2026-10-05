import logging
from dataclasses import dataclass
from typing import Optional

from app.ai.client import get_client
from app.ai import email_checks
from app.ai.prompts import load_prompt
from app.ai.schemas import FollowUpEmail, GeneratedEmail

logger = logging.getLogger(__name__)

TONES = {
    "professional": "Formal but warm. Confident.",
    "friendly": "Conversational and enthusiastic, still professional.",
    "concise": "Ultra-short, max 120 words, zero filler.",
}


@dataclass
class ComposedEmail:
    subject: str
    body: str
    provider: str
    prompt_version: str
    confidence: Optional[float] = None


def _matching_skills(user_skills: list[str], required: list[str]) -> list[str]:
    return [s for s in user_skills if any(s.lower() in r.lower() or r.lower() in s.lower() for r in required)]


async def compose_email(
    company_name: str, role_title: str, required_skills: list, company_research: str,
    user_name: str, user_email: str, user_resume: str, user_skills: list,
    experience_years: int, tone: str = "professional", recipient_name: Optional[str] = None,
    jd_text: str = "",
) -> ComposedEmail:
    prompt = load_prompt("email_generation")
    matched = _matching_skills(user_skills, required_skills)
    greeting = f"Dear {recipient_name}," if recipient_name else "Dear Hiring Manager,"
    low, high = email_checks.word_limits(tone)
    system, user = prompt.render(
        user_name=user_name, user_email=user_email, experience_years=experience_years,
        skills=", ".join((matched or user_skills)[:8]), resume=(user_resume or "")[:1200],
        role_title=role_title, company_name=company_name, requirements=", ".join(required_skills[:10]),
        job_description=(jd_text or "(not provided)")[:2500],
        company_research=(company_research or "")[:600] or "(none)",
        tone_instruction=TONES.get(tone, TONES["professional"]), min_words=low, max_words=high, greeting=greeting,
    )
    # Everything the model is allowed to cite; used to reject invented figures.
    sources = [jd_text or "", company_research or "", user_resume or "", " ".join(user_skills), str(experience_years)]
    result, provider = await get_client().complete_json(
        user, GeneratedEmail, system=system, max_tokens=800, temperature=0.6,
        check=lambda e: email_checks.check_cold_email(
            e.subject, e.body, greeting=greeting, user_name=user_name, user_email=user_email, tone=tone, sources=sources))
    return ComposedEmail(result.subject, result.body, provider, prompt.tag, result.confidence)


async def compose_followup(
    company_name: str, role_title: str, original_sent_at: str, user_name: str, user_email: str,
    sequence_number: int = 1, custom_note: Optional[str] = None, recipient_name: Optional[str] = None,
) -> ComposedEmail:
    prompt = load_prompt("followup")
    greeting = f"Dear {recipient_name}," if recipient_name else "Dear Hiring Manager,"
    system, user = prompt.render(
        company_name=company_name, role_title=role_title, sent_date=original_sent_at,
        user_name=user_name, user_email=user_email, sequence_number=sequence_number,
        custom_note_line=f"Personal note to include: {custom_note}" if custom_note else "", greeting=greeting,
    )
    result, provider = await get_client().complete_json(
        user, FollowUpEmail, system=system, max_tokens=400, temperature=0.7,
        check=lambda e: email_checks.check_followup(e.subject, e.body, greeting=greeting, user_name=user_name, user_email=user_email))
    return ComposedEmail(result.subject, result.body, provider, prompt.tag)
