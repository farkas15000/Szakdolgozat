# src/backend/app/services/tmdb.py
"""
TMDB poster lekérdezés szerveroldalon.

Memória cache-t használ hogy ne hívjuk feleslegesen a TMDB API-t
minden kérésnél. A cache TTL 24 óra.

Konfiguráció (.env):
    TMDB_API_KEY=your_api_key_here
    TMDB_POSTER_SIZE=w342   # w92, w154, w185, w342, w500, w780, original
"""

from __future__ import annotations

import logging
import os
import time
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

TMDB_API_KEY     = os.environ.get("TMDB_API_KEY", "")
TMDB_POSTER_SIZE = os.environ.get("TMDB_POSTER_SIZE", "w342")
TMDB_BASE_URL    = "https://api.themoviedb.org/3"
TMDB_IMAGE_BASE  = f"https://image.tmdb.org/t/p/{TMDB_POSTER_SIZE}"
CACHE_TTL        = 60 * 60 * 24  # 24 óra másodpercben

# Egyszerű in-memory cache: {tmdb_id: (poster_url | None, timestamp)}
_cache: dict[str, tuple[Optional[str], float]] = {}


async def get_poster_url(tmdb_id: str) -> Optional[str]:
    """
    Visszaadja a film poster URL-jét, vagy None-t ha nem található.
    Eredményt cache-eli 24 órára.
    """
    if not TMDB_API_KEY:
        logger.warning("TMDB_API_KEY nincs beállítva – poster URL nem elérhető.")
        return None

    # Cache ellenőrzés
    if tmdb_id in _cache:
        url, ts = _cache[tmdb_id]
        if time.time() - ts < CACHE_TTL:
            return url

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(
                f"{TMDB_BASE_URL}/movie/{tmdb_id}",
                params={"api_key": TMDB_API_KEY, "language": "en-US"},
            )
            resp.raise_for_status()
            data = resp.json()

        poster_path: Optional[str] = data.get("poster_path")
        url = f"{TMDB_IMAGE_BASE}{poster_path}" if poster_path else None

    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            logger.debug(f"TMDB: film nem található – tmdb_id={tmdb_id}")
        else:
            logger.warning(f"TMDB HTTP hiba: {e.response.status_code} – tmdb_id={tmdb_id}")
        url = None
    except Exception as e:
        logger.warning(f"TMDB hívás sikertelen: {e} – tmdb_id={tmdb_id}")
        url = None

    _cache[tmdb_id] = (url, time.time())

    return url


async def get_poster_urls_bulk(tmdb_ids: list[str]) -> dict[str, Optional[str]]:
    """
    Több film poster URL-jét kéri le párhuzamosan.
    Cache-elt elemeket nem hívja újra.
    """
    import asyncio

    results: dict[str, Optional[str]] = {}
    to_fetch: list[str] = []

    now = time.time()
    for tid in tmdb_ids:
        if tid in _cache:
            cached_url, ts = _cache[tid]
            if now - ts < CACHE_TTL:
                results[tid] = cached_url
                continue
        to_fetch.append(tid)

    if to_fetch:
        fetched = await asyncio.gather(
            *[get_poster_url(tid) for tid in to_fetch],
            return_exceptions=False,
        )
        for tid, url in zip(to_fetch, fetched):
            results[tid] = url

    return results
