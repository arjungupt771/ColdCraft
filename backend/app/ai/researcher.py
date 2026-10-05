import logging
from dataclasses import dataclass

from app.ai.client import get_client
from app.ai.prompts import load_prompt
from app.ai.schemas import CompanyResearch
from app.integrations import web

logger = logging.getLogger(__name__)


@dataclass
class ResearchResult:
    text: str
    provider: str
    prompt_version: str


async def research_company(company_name: str, company_website: str | None = None) -> ResearchResult:
    context = ""
    if company_website:
        context = await web.fetch_snippet(company_website)
    if not context:
        wiki = await web.wikipedia_extract(company_name)
        context = f"Wikipedia: {wiki}" if wiki else ""

    prompt = load_prompt("company_research")
    system, user = prompt.render(
        company_name=company_name,
        context=f"Context: {context[:2000]}" if context else "Use your training knowledge; omit anything you are unsure of.",
    )
    result, provider = await get_client().complete_json(user, CompanyResearch, system=system, max_tokens=700, temperature=0.4)
    logger.info("Researched '%s' via %s", company_name, provider)
    return ResearchResult(result.as_text(), provider, prompt.tag)
