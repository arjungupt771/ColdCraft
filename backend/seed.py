"""Seed dev data. Run: python seed.py"""
import asyncio
from app.core.database import AsyncSessionLocal
from app.models.models import UserProfile, JobApplication, FollowUp
from datetime import datetime, timezone, timedelta

async def seed():
    # Schema is managed by Alembic: run `alembic upgrade head` (or start the API once) first.

    async with AsyncSessionLocal() as db:
        profile = UserProfile(
            name="Arjun Sharma",
            email="arjun@gmail.com",
            phone="+91 98765 43210",
            linkedin="linkedin.com/in/arjun-sharma",
            resume_text="""Final year B.Tech IT student at VIT Vellore (2026).
3 years experience building web apps and AI integrations.
Built enterprise AI chatbots at Team Computers Pvt Ltd.
Skills: React, TypeScript, Python, FastAPI, Node.js, PostgreSQL, LLMs, Docker.
Oracle Cloud Infrastructure certified (GenAI Professional + AI Foundations).
Projects: NextFlow (LLM pipeline builder), MatchMate (AI football app), ColdCraft.""",
            skills=["React", "TypeScript", "Python", "FastAPI", "PostgreSQL", "Node.js", "LLMs", "Docker", "GenAI"],
            experience_years=3,
            tone="professional",
        )
        db.add(profile)

        now = datetime.now(timezone.utc)

        app1 = JobApplication(
            company_name="Razorpay",
            role_title="Software Engineer - Full Stack",
            jd_text="Build scalable payment infrastructure using React, Node.js, and microservices...",
            required_skills=["React", "Node.js", "TypeScript", "PostgreSQL"],
            company_research="Razorpay is India's leading payments platform processing $90B+ annually. Engineering-first culture, strong open source contributions.",
            source="linkedin_url",
            linkedin_job_url="https://linkedin.com/jobs/view/razorpay-swe",
            recipient_email="careers@razorpay.com",
            email_subject="Full Stack Engineer — React + Node.js — 3 yrs experience",
            email_body="Dear Hiring Manager,\n\nI've been following Razorpay's engineering blog closely — your work on distributed payment systems at scale is genuinely impressive...",
            ai_provider_used="groq",
            status="SENT",
            sent_at=now - timedelta(days=3),
        )
        db.add(app1)
        await db.flush()

        # Add follow-up for app1
        fu1 = FollowUp(
            application_id=app1.id,
            scheduled_at=now + timedelta(days=2),
            subject="Following up — Full Stack Engineer at Razorpay (1st follow-up)",
            body="Dear Hiring Manager,\n\nI wanted to follow up on my application for the Full Stack Engineer role sent last week...",
            status="pending",
            sequence_number=1,
        )
        db.add(fu1)
        app1.followup_scheduled_at = fu1.scheduled_at

        app2 = JobApplication(
            company_name="Zepto",
            role_title="Backend Engineer",
            jd_text="Build the tech powering 10-minute grocery delivery at scale...",
            required_skills=["Python", "FastAPI", "Redis", "PostgreSQL", "Docker"],
            company_research="Zepto is India's fastest growing quick-commerce startup. $1.4B valuation, 10-minute delivery across 10+ cities.",
            source="screenshot",
            recipient_email="tech@zepto.com",
            email_subject="Backend Engineer — Python/FastAPI — Excited about Zepto's scale challenges",
            email_body="Dear Hiring Manager,\n\nZepto's engineering challenges — real-time inventory, sub-second routing, hyper-local delivery orchestration — are exactly the kind of problems I want to work on...",
            ai_provider_used="groq",
            status="READY",
        )
        db.add(app2)

        app3 = JobApplication(
            company_name="Anthropic",
            role_title="GenAI Engineer",
            jd_text="Work on developer tools and integrations for Claude API...",
            required_skills=["Python", "LLMs", "React", "TypeScript", "FastAPI"],
            company_research="Anthropic is an AI safety company building reliable, interpretable AI. Creator of Claude.",
            source="linkedin_url",
            linkedin_job_url="https://linkedin.com/jobs/view/anthropic-genai",
            recipient_email="jobs@anthropic.com",
            ai_provider_used="groq",
            status="READY",
        )
        db.add(app3)

        await db.commit()
        print("Seeded: 1 profile, 3 applications, 1 scheduled follow-up")


if __name__ == "__main__":
    asyncio.run(seed())
