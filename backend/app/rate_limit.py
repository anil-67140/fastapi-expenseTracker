"""Sliding-window rate limiter used as a FastAPI dependency.

    router = APIRouter(dependencies=[Depends(RateLimiter(limit=10, window_seconds=60, scope="auth"))])

State lives in process memory, so it is per-worker. For several instances you
would keep the counters in Redis (INCR + EXPIRE) behind this same interface.
"""
import math
import time
from collections import defaultdict, deque

from fastapi import Request, Response

from app.config import settings
from app.exceptions import RateLimitError

_hits: dict[str, deque[float]] = defaultdict(deque)


def reset_rate_limits() -> None:
    _hits.clear()


class RateLimiter:
    def __init__(self, limit: int, window_seconds: int = 60, scope: str = "api") -> None:
        self.limit = limit
        self.window = window_seconds
        self.scope = scope

    async def __call__(self, request: Request, response: Response) -> None:
        client = request.client.host if request.client else "unknown"
        key = f"{self.scope}:{client}"
        now = time.monotonic()
        hits = _hits[key]
        while hits and hits[0] <= now - self.window:
            hits.popleft()

        if len(hits) >= self.limit:
            retry_after = max(1, math.ceil(hits[0] + self.window - now))
            raise RateLimitError(
                f"Rate limit exceeded. Try again in {retry_after}s.",
                headers={
                    "Retry-After": str(retry_after),
                    "X-RateLimit-Limit": str(self.limit),
                    "X-RateLimit-Remaining": "0",
                },
            )

        hits.append(now)
        response.headers["X-RateLimit-Limit"] = str(self.limit)
        response.headers["X-RateLimit-Remaining"] = str(self.limit - len(hits))


api_limiter = RateLimiter(settings.rate_limit_per_minute, 60, "api")
auth_limiter = RateLimiter(settings.auth_rate_limit_per_minute, 60, "auth")
crawler_limiter = RateLimiter(settings.crawler_rate_limit_per_minute, 60, "crawler")
