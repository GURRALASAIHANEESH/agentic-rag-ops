# app/services/rate_limiter.py

from __future__ import annotations

import time
from dataclasses import dataclass
from functools import lru_cache

import redis.asyncio as aioredis
import structlog

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Redis client singleton
# ─────────────────────────────────────────────────────────────────────────────

@lru_cache(maxsize=1)
def get_redis_client() -> aioredis.Redis:
    """
    Returns a single shared async Redis client for the process lifetime.
    Uses connection pooling internally — safe for concurrent async use.
    decode_responses=True so all keys/values are native Python strings.
    """
    cfg = get_settings()
    client = aioredis.from_url(
        cfg.REDIS_URL,
        encoding="utf-8",
        decode_responses=True,
        socket_connect_timeout=2,
        socket_timeout=2,
        retry_on_timeout=True,
    )
    logger.info("rate_limiter.redis_client_created", url=cfg.REDIS_URL)
    return client


# ─────────────────────────────────────────────────────────────────────────────
# DTOs
# ─────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class RateLimitResult:
    """
    Returned by RateLimiter.check_and_increment() on every call.

    allowed         — True if the request should proceed
    rpm_current     — requests made in the current 60s window
    rpm_limit       — workspace rpm ceiling
    daily_current   — requests made today (UTC midnight reset)
    daily_limit     — workspace daily ceiling
    retry_after_s   — seconds until the window resets (only meaningful when allowed=False)
    """
    allowed: bool
    rpm_current: int
    rpm_limit: int
    daily_current: int
    daily_limit: int
    retry_after_s: int


# ─────────────────────────────────────────────────────────────────────────────
# Rate Limiter Service
# ─────────────────────────────────────────────────────────────────────────────

class RateLimiter:
    """
    Per-workspace rate limiter backed by Redis.

    Two independent counters per workspace:
        rpm   — sliding 60-second window using a Redis key with 60s TTL
        daily — calendar-day counter using a Redis key with TTL until UTC midnight

    Algorithm: Increment-then-check (atomic INCR + EXPIRE via pipeline).
    This is the standard Redis rate limiting pattern — O(1) per check,
    no Lua scripts needed, no race conditions on the increment itself.

    Key schema:
        rl:rpm:{workspace_id}    TTL = 60s
        rl:day:{workspace_id}    TTL = seconds until next UTC midnight
    """

    def __init__(self) -> None:
        self._redis = get_redis_client()

    async def check_and_increment(
        self,
        workspace_id: str,
        rpm_limit: int,
        daily_limit: int,
        rate_limit_enabled: bool,
    ) -> RateLimitResult:
        """
        Atomically increments both counters and checks limits.

        If rate_limit_enabled is False for this workspace, returns allowed=True
        immediately without touching Redis — zero overhead for unlimited workspaces.

        Args:
            workspace_id:        UUID string of the workspace
            rpm_limit:           Max requests per 60s (from workspaces.rate_limit_rpm)
            daily_limit:         Max requests per day (from workspaces.rate_limit_daily)
            rate_limit_enabled:  Master switch from workspaces.rate_limit_enabled

        Returns:
            RateLimitResult — middleware raises 429 if allowed=False
        """
        if not rate_limit_enabled:
            return RateLimitResult(
                allowed=True,
                rpm_current=0,
                rpm_limit=rpm_limit,
                daily_current=0,
                daily_limit=daily_limit,
                retry_after_s=0,
            )

        rpm_key   = f"rl:rpm:{workspace_id}"
        daily_key = f"rl:day:{workspace_id}"
        seconds_until_midnight = _seconds_until_utc_midnight()

        try:
            # Pipeline: two INCRs + two conditional EXPIREs in one round-trip
            async with self._redis.pipeline(transaction=False) as pipe:
                pipe.incr(rpm_key)
                pipe.incr(daily_key)
                pipe.expire(rpm_key,   60,                    nx=True)  # nx=True: only set TTL on first increment
                pipe.expire(daily_key, seconds_until_midnight, nx=True)
                results = await pipe.execute()

            rpm_current:   int = int(results[0])
            daily_current: int = int(results[1])

        except Exception as exc:
            # Redis unavailable — fail open (allow request) and log
            # Never block users because the rate limit store is down
            logger.error(
                "rate_limiter.redis_error",
                workspace_id=workspace_id,
                error=str(exc),
                decision="fail_open",
            )
            return RateLimitResult(
                allowed=True,
                rpm_current=0,
                rpm_limit=rpm_limit,
                daily_current=0,
                daily_limit=daily_limit,
                retry_after_s=0,
            )

        # Determine which limit was hit (rpm takes priority in error message)
        rpm_exceeded   = rpm_current   > rpm_limit
        daily_exceeded = daily_current > daily_limit
        allowed        = not rpm_exceeded and not daily_exceeded

        retry_after_s = 60 if rpm_exceeded else (seconds_until_midnight if daily_exceeded else 0)

        log = logger.bind(
            workspace_id=workspace_id,
            rpm_current=rpm_current,
            rpm_limit=rpm_limit,
            daily_current=daily_current,
            daily_limit=daily_limit,
            allowed=allowed,
        )

        if not allowed:
            log.warning(
                "rate_limiter.limit_exceeded",
                reason="rpm" if rpm_exceeded else "daily",
                retry_after_s=retry_after_s,
            )
        else:
            log.debug("rate_limiter.allowed")

        return RateLimitResult(
            allowed=allowed,
            rpm_current=rpm_current,
            rpm_limit=rpm_limit,
            daily_current=daily_current,
            daily_limit=daily_limit,
            retry_after_s=retry_after_s,
        )

    async def get_current_usage(self, workspace_id: str) -> dict[str, int]:
        """
        Returns current counter values without incrementing.
        Used by a status/debug endpoint — not in the hot query path.
        """
        rpm_key   = f"rl:rpm:{workspace_id}"
        daily_key = f"rl:day:{workspace_id}"

        try:
            async with self._redis.pipeline(transaction=False) as pipe:
                pipe.get(rpm_key)
                pipe.get(daily_key)
                pipe.ttl(rpm_key)
                pipe.ttl(daily_key)
                results = await pipe.execute()

            return {
                "rpm_current":   int(results[0] or 0),
                "daily_current": int(results[1] or 0),
                "rpm_ttl_s":     int(results[2] or 0),
                "daily_ttl_s":   int(results[3] or 0),
            }
        except Exception as exc:
            logger.error("rate_limiter.get_usage_failed", error=str(exc))
            return {"rpm_current": 0, "daily_current": 0, "rpm_ttl_s": 0, "daily_ttl_s": 0}

    async def reset_workspace(self, workspace_id: str) -> None:
        """
        Clears both counters for a workspace.
        Admin operation — not in the hot path.
        """
        rpm_key   = f"rl:rpm:{workspace_id}"
        daily_key = f"rl:day:{workspace_id}"
        await self._redis.delete(rpm_key, daily_key)
        logger.info("rate_limiter.reset", workspace_id=workspace_id)


# ─────────────────────────────────────────────────────────────────────────────
# Module-level singleton accessor
# ─────────────────────────────────────────────────────────────────────────────

@lru_cache(maxsize=1)
def get_rate_limiter() -> RateLimiter:
    """Returns the process-lifetime RateLimiter singleton."""
    return RateLimiter()


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _seconds_until_utc_midnight() -> int:
    """
    Returns integer seconds from now until the next UTC midnight.
    Used as the TTL for the daily counter key.
    Minimum 1 — never sets a zero TTL (which would make the key permanent).
    """
    now = time.time()
    # UTC midnight of the NEXT day
    next_midnight = (int(now) // 86400 + 1) * 86400
    return max(1, next_midnight - int(now))
