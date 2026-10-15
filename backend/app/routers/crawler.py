"""Web crawling endpoint: preview what is on a web page (title, headings, prices)."""
from fastapi import APIRouter, Depends

from app.dependencies import CurrentUser, HttpClient
from app.rate_limit import api_limiter, crawler_limiter
from app.schemas import CrawlRequest, CrawlResult, error_responses
from app.services.crawler import crawl_many

router = APIRouter(
    prefix="/crawler", tags=["Web crawling"], dependencies=[Depends(api_limiter), Depends(crawler_limiter)]
)


@router.post(
    "/preview",
    response_model=list[CrawlResult],
    summary="Crawl up to 5 pages concurrently",
    description="Fetches each URL (public hosts only), then extracts title, description, headings and price-like text.",
    responses=error_responses(401, 422, 429),
)
async def preview(payload: CrawlRequest, _user: CurrentUser, client: HttpClient) -> list[CrawlResult]:
    return await crawl_many(client, [str(u) for u in payload.urls])
