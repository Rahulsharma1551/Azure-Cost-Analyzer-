"""
In-process TTL cache for DB query results.

Two-layer caching strategy:
  1. This module: backend in-memory cache (5 min daily / 30 min monthly)
  2. React Query on the frontend: 60-second stale-time per query key

No external dependencies — just a dict with timestamps.
The cache is per-process and clears on server restart, which is fine for
a single-worker dev/student deployment. Swap the backend to Redis later
if you move to multi-worker production without changing call sites.
"""

import time
from dataclasses import dataclass
from typing import Any

from loguru import logger

# TTL constants (seconds)
TTL_DAILY: int = 5 * 60  # 5 minutes  — daily data changes intraday
TTL_MONTHLY: int = 30 * 60  # 30 minutes — monthly aggregates are stable


@dataclass
class _CacheEntry:
    value: Any
    expires_at: float  # monotonic timestamp


class TTLCache:
    """
    Thread-safe enough for asyncio single-thread use.
    Keys are arbitrary strings; values are any serialisable object.
    """

    def __init__(self) -> None:
        self._store: dict[str, _CacheEntry] = {}

    def get(self, key: str) -> Any | None:
        """Return cached value or None if missing / expired."""
        entry = self._store.get(key)
        if entry is None:
            return None
        if time.monotonic() > entry.expires_at:
            del self._store[key]
            logger.debug(f"Cache expired: {key}")
            return None
        logger.debug(f"Cache hit: {key}")
        return entry.value

    def set(self, key: str, value: Any, ttl: int) -> None:
        """Store value with a TTL in seconds."""
        self._store[key] = _CacheEntry(
            value=value,
            expires_at=time.monotonic() + ttl,
        )
        logger.debug(f"Cache set: {key} (ttl={ttl}s)")

    def invalidate_prefix(self, prefix: str) -> None:
        """Remove all keys that start with prefix."""
        keys = [k for k in self._store if k.startswith(prefix)]
        for k in keys:
            del self._store[k]
        if keys:
            logger.info(f"Cache invalidated {len(keys)} key(s) with prefix '{prefix}'")

    def clear(self) -> None:
        """Wipe entire cache — called after scheduler saves fresh data."""
        count = len(self._store)
        self._store.clear()
        if count:
            logger.info(f"Cache cleared ({count} entries evicted)")

    def size(self) -> int:
        """Current number of live (non-expired) entries."""
        now = time.monotonic()
        return sum(1 for e in self._store.values() if e.expires_at > now)


# Module-level singleton
cost_cache = TTLCache()


def make_cache_key(granularity: str, start_date: str, end_date: str) -> str:
    """
    Canonical cache key for a cost DB query.
    Format: ``<granularity>:<start_date>:<end_date>``
    """
    return f"{granularity}:{start_date}:{end_date}"


def ttl_for(granularity: str) -> int:
    """Return the appropriate TTL (seconds) for a given granularity."""
    return TTL_DAILY if granularity == "daily" else TTL_MONTHLY
