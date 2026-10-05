"""Duplicate-application detection: same job URL, or same company + same role."""
import re
from typing import Optional
from urllib.parse import parse_qsl, urlparse

# Query params that identify a job on career sites (everything else — tracking junk — is ignored).
_ID_PARAMS = {"currentjobid", "jobid", "job_id", "id", "gh_jid", "reqid", "requisitionid", "jid"}
_SUFFIXES = re.compile(r"\b(inc|llc|ltd|limited|pvt|private|corp|corporation|co|gmbh|plc)\b")


def norm_text(s: Optional[str]) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", (s or "").lower())).strip()


def norm_company(s: Optional[str]) -> str:
    return norm_text(_SUFFIXES.sub(" ", norm_text(s)))


def job_url_key(url: Optional[str]) -> Optional[str]:
    """Canonical key so tracking params, www., trailing slashes and LinkedIn slugs don't hide a duplicate."""
    if not url:
        return None
    p = urlparse(url if "://" in url else "https://" + url)
    host = (p.hostname or "").lower().removeprefix("www.")
    if not host:
        return None
    path = p.path.rstrip("/").lower()
    q = {k.lower(): v for k, v in parse_qsl(p.query)}
    if host.endswith("linkedin.com"):
        m = re.search(r"/jobs/view/(?:[^/]*?-)?(\d{6,})", path)
        job_id = m.group(1) if m else q.get("currentjobid")
        if job_id:
            return f"linkedin.com/jobs/view/{job_id}"
    ids = "&".join(f"{k}={q[k]}" for k in sorted(q) if k in _ID_PARAMS)
    return f"{host}{path}" + (f"?{ids}" if ids else "")


def is_duplicate(row, company: Optional[str], role: Optional[str], url: Optional[str]) -> bool:
    key = job_url_key(url)
    if key and key == job_url_key(row.linkedin_job_url):
        return True
    return bool(company and role and norm_company(company) == norm_company(row.company_name)
                and norm_text(role) == norm_text(row.role_title))
