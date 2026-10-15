"""Safe web crawling: fetch pages concurrently and extract useful data with BeautifulSoup.

Security notes (great interview material):
* SSRF: a "fetch this URL for me" feature can be abused to reach internal
  services (localhost, 10.x.x.x, cloud metadata at 169.254.169.254). We resolve
  the hostname and refuse anything that is not a public IP, and we re-check on
  every redirect (redirects are followed manually).
* Size/time limits: bodies are capped and requests have a timeout.
* CPU-bound HTML parsing runs in a worker thread so the event loop stays free.
"""
import asyncio
import ipaddress
import re
import socket

import httpx
from bs4 import BeautifulSoup

from app.exceptions import AppError, BadRequestError
from app.schemas import CrawlResult

MAX_BYTES = 1_000_000
MAX_REDIRECTS = 3
CONCURRENCY = 3
USER_AGENT = "ExpenseTrackerBot/1.0 (+learning project)"

PRICE_RE = re.compile(
    r"(?:USD|US\$|\$|€|£|₹|Rs\.?|PKR)\s?\d{1,3}(?:,\d{3})*(?:\.\d{1,2})?"
    r"|\d{1,3}(?:,\d{3})*(?:\.\d{1,2})?\s?(?:USD|EUR|GBP|PKR)\b"
)


async def assert_public_url(url: str) -> None:
    parsed = httpx.URL(url)
    if parsed.scheme not in {"http", "https"} or not parsed.host:
        raise BadRequestError("Only http(s) URLs are allowed.")
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    try:
        infos = await asyncio.get_running_loop().getaddrinfo(parsed.host, port, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise BadRequestError(f"Could not resolve host '{parsed.host}'.") from exc
    # NOTE: a determined attacker could still try DNS rebinding between this check and
    # the actual request; pinning the resolved IP in a custom transport closes that gap.
    for info in infos:
        if not ipaddress.ip_address(info[4][0]).is_global:
            raise BadRequestError("URL points to a private or reserved address.")


async def fetch_html(client: httpx.AsyncClient, url: str) -> tuple[int, str]:
    current = url
    for _ in range(MAX_REDIRECTS + 1):
        await assert_public_url(current)
        async with client.stream(
            "GET",
            current,
            headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml"},
            follow_redirects=False,
            timeout=10.0,
        ) as response:
            if response.is_redirect and response.headers.get("location"):
                current = str(httpx.URL(current).join(response.headers["location"]))
                continue
            if "html" not in response.headers.get("content-type", "").lower():
                raise BadRequestError("URL did not return an HTML page.")
            body = bytearray()
            async for chunk in response.aiter_bytes():
                body.extend(chunk)
                if len(body) > MAX_BYTES:
                    break
            return response.status_code, bytes(body).decode(response.encoding or "utf-8", errors="replace")
    raise BadRequestError("Too many redirects.")


def parse_html(html: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")
    description = None
    for attrs in ({"name": "description"}, {"property": "og:description"}):
        tag = soup.find("meta", attrs=attrs)
        if tag and tag.get("content"):
            description = tag["content"].strip()[:300]
            break
    headings = [h.get_text(" ", strip=True) for h in soup.find_all(["h1", "h2"])][:5]
    text = soup.get_text(" ", strip=True)
    prices = list(dict.fromkeys(PRICE_RE.findall(text)))[:5]
    return {
        "title": soup.title.get_text(strip=True)[:200] if soup.title else None,
        "description": description,
        "headings": [h[:150] for h in headings],
        "link_count": len(soup.find_all("a", href=True)),
        "price_hints": prices,
    }


async def crawl_one(client: httpx.AsyncClient, url: str, semaphore: asyncio.Semaphore) -> CrawlResult:
    async with semaphore:  # at most CONCURRENCY pages in flight
        try:
            status, html = await fetch_html(client, url)
            data = await asyncio.to_thread(parse_html, html)
            return CrawlResult(url=url, ok=True, status_code=status, **data)
        except AppError as exc:
            return CrawlResult(url=url, ok=False, error=exc.message)
        except httpx.TimeoutException:
            return CrawlResult(url=url, ok=False, error="The page took too long to respond.")
        except httpx.HTTPError:
            return CrawlResult(url=url, ok=False, error="Could not fetch the page.")


async def crawl_many(client: httpx.AsyncClient, urls: list[str]) -> list[CrawlResult]:
    """Crawl several URLs concurrently with asyncio.gather; one failure never sinks the batch."""
    semaphore = asyncio.Semaphore(CONCURRENCY)
    return list(await asyncio.gather(*(crawl_one(client, u, semaphore) for u in urls)))
