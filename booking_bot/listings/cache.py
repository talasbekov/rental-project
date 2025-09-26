"""Utilities for caching listing search results."""

from __future__ import annotations

import hashlib
from typing import Callable, Dict, Iterable, List

from django.conf import settings
from django.core.cache import cache

CACHE_KEYS_STORAGE_KEY = "search:property_cache_keys"


def _is_cache_enabled() -> bool:
    return getattr(settings, "SEARCH_CACHE_ENABLED", False)


def _build_cache_key(filters: Dict[str, object]) -> str:
    prefix = getattr(settings, "SEARCH_CACHE_PREFIX", "search:properties")
    normalized_parts = [f"{key}={filters[key]}" for key in sorted(filters)]
    fingerprint = "|".join(normalized_parts)
    digest = hashlib.sha1(fingerprint.encode("utf-8")).hexdigest()
    return f"{prefix}:{digest}"


def _register_cache_key(key: str) -> None:
    keys: List[str] | None = cache.get(CACHE_KEYS_STORAGE_KEY)
    if keys is None:
        cache.set(CACHE_KEYS_STORAGE_KEY, [key], None)
        return
    if key in keys:
        return
    keys.append(key)
    cache.set(CACHE_KEYS_STORAGE_KEY, keys, None)


def get_cached_property_ids(
    filters: Dict[str, object], builder: Callable[[], List[int]]
) -> List[int]:
    """Return cached ordered property identifiers for the provided filters."""
    if not _is_cache_enabled():
        return builder()

    key = _build_cache_key(filters)
    cached: List[int] | None = cache.get(key)
    if cached is not None:
        return cached

    result = builder()
    timeout = getattr(settings, "SEARCH_CACHE_TIMEOUT", 120)
    cache.set(key, result, timeout)
    _register_cache_key(key)
    return result


def invalidate_search_cache() -> None:
    """Remove all cached search result entries."""
    keys: List[str] | None = cache.get(CACHE_KEYS_STORAGE_KEY)
    if keys:
        cache.delete_many(keys)
    cache.delete(CACHE_KEYS_STORAGE_KEY)


__all__ = [
    "get_cached_property_ids",
    "invalidate_search_cache",
]
