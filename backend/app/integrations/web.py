import ipaddress
import logging
import re
import socket
from urllib.parse import quote, urlparse

import httpx

logger = logging.getLogger(__name__)

BROWSER_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
MOBILE_UA = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15"
HEADERS = {
    "User-Agent": BROWSER_UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}


def normalize_url(url: str) -> str:
    url = url.strip()
    return url if url.startswith(("http://", "https://")) else "https://" + url


def assert_public_url(url: str) -> None:
    """Refuse non-http(s) URLs and hosts that resolve to private/loopback/link-local addresses."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise ValueError("Only http(s) URLs are supported")
    try:
        infos = socket.getaddrinfo(parsed.hostname, parsed.port or 443, proto=socket.IPPROTO_TCP)
    except socket.gaierror:
        raise ValueError(f"Could not resolve host: {parsed.hostname}")
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
            raise ValueError("URL points to a non-public address")


def html_to_text(html: str) -> str:
    html = re.sub(r"<script[^>]*>.*?</script>", " ", html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r"<style[^>]*>.*?</style>", " ", html, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", html)
    for a, b in (("&amp;", "&"), ("&lt;", "<"), ("&gt;", ">"), ("&nbsp;", " "), ("&#39;", "'"), ("&quot;", '"')):
        text = text.replace(a, b)
    return re.sub(r"\s+", " ", text).strip()


async def fetch_html(url: str, timeout: float = 15.0) -> str:
    """GET a page, retrying with a mobile UA when the site blocks bots. Returns '' on failure."""
    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True, max_redirects=5) as client:
            r = await client.get(url, headers=HEADERS)
            if r.status_code == 200:
                return r.text
            if r.status_code in (403, 999):
                r2 = await client.get(url, headers={**HEADERS, "User-Agent": MOBILE_UA})
                return r2.text if r2.status_code == 200 else ""
    except Exception as e:
        logger.error("Fetch failed for %s: %s", url, e)
    return ""


async def fetch_snippet(url: str, limit: int = 2000) -> str:
    url = normalize_url(url)
    try:
        assert_public_url(url)
    except ValueError:
        return ""
    return html_to_text(await fetch_html(url, timeout=8.0))[:limit]


async def wikipedia_extract(title: str) -> str:
    if not title.strip():
        return ""
    try:
        async with httpx.AsyncClient(timeout=8.0) as c:
            r = await c.get(
                "https://en.wikipedia.org/w/api.php",
                params={"action": "query", "titles": title, "prop": "extracts", "exintro": 1,
                        "explaintext": 1, "format": "json", "exsentences": 5})
            for page in r.json().get("query", {}).get("pages", {}).values():
                extract = page.get("extract", "")
                if extract and len(extract) > 50:
                    return extract[:1500]
    except Exception as e:
        logger.info("Wikipedia lookup failed for %s: %s", title, e)
    return ""
