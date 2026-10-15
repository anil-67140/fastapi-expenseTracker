"""A tiny in-memory TTL cache (single process).

Interview note: this is the same idea as Redis `SETEX`, just local. With several
workers/instances each process has its own cache, so production would use Redis.
"""
import time
from typing import Any

_MISSING = object()


class TTLCache:
    def __init__(self, max_items: int = 1000) -> None:
        self._store: dict[str, tuple[float, Any]] = {}
        self._max_items = max_items
        self.hits = 0
        self.misses = 0

    def get(self, key: str, default: Any = None) -> Any:
        item = self._store.get(key, _MISSING)
        if item is _MISSING:
            self.misses += 1
            return default
        expires_at, value = item  # type: ignore[misc]
        if expires_at < time.monotonic():
            del self._store[key]
            self.misses += 1
            return default
        self.hits += 1
        return value

    def set(self, key: str, value: Any, ttl: float) -> None:
        if len(self._store) >= self._max_items:
            self._purge_expired()
            if len(self._store) >= self._max_items:  # still full: drop the oldest entry
                self._store.pop(next(iter(self._store)))
        self._store[key] = (time.monotonic() + ttl, value)

    def delete_prefix(self, prefix: str) -> int:
        keys = [k for k in self._store if k.startswith(prefix)]
        for k in keys:
            del self._store[k]
        return len(keys)

    def clear(self) -> None:
        self._store.clear()
        self.hits = self.misses = 0

    def _purge_expired(self) -> None:
        now = time.monotonic()
        for k in [k for k, (exp, _) in self._store.items() if exp < now]:
            del self._store[k]


cache = TTLCache()


def invalidate_user_cache(user_id: int) -> None:
    """Call after any write that changes a user's numbers (expenses, budget)."""
    cache.delete_prefix(f"user:{user_id}:")
