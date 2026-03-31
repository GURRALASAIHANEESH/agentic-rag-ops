# app/core/dependencies.py

from __future__ import annotations

import uuid

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.logging import get_logger
from app.core.security import get_current_user_payload, get_user_id_from_payload
from app.models.user import Workspace
from app.services.rate_limiter import RateLimitResult, get_rate_limiter

logger = get_logger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Rate limit helper function
# ─────────────────────────────────────────────────────────────────────────────

async def check_rate_limit(
    workspace_id: uuid.UUID,
    user_id: uuid.UUID,
    db: AsyncSession,
) -> RateLimitResult:
    """
    Standard async function — enforces per-workspace rate limits.
    Call this inline inside your endpoints to avoid FastAPI body parsing conflicts.

    Flow:
        1. Fetch workspace row (rate_limit_rpm, rate_limit_daily, rate_limit_enabled)
        2. Verify the authenticated user owns this workspace (RBAC)
        3. Call RateLimiter.check_and_increment()
        4. If limit exceeded → raise HTTP 429 with Retry-After header
        5. If allowed → return RateLimitResult (endpoint can log/inspect it)
    """
    # ── Fetch workspace and verify ownership ──────────────────────────────
    workspace: Workspace | None = await db.get(Workspace, workspace_id)

    if workspace is None or workspace.owner_id != user_id:
        logger.error(
            "rate_limit.workspace_not_found",
            workspace_id=str(workspace_id),
            user_id=str(user_id),
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Workspace not found or access denied.",
        )

    # ── Check and increment counters ──────────────────────────────────────
    limiter = get_rate_limiter()
    result: RateLimitResult = await limiter.check_and_increment(
        workspace_id=str(workspace_id),
        rpm_limit=workspace.rate_limit_rpm,
        daily_limit=workspace.rate_limit_daily,
        rate_limit_enabled=workspace.rate_limit_enabled,
    )

    # ── Enforce limit ─────────────────────────────────────────────────────
    if not result.allowed:
        logger.warning(
            "rate_limit.request_blocked",
            workspace_id=str(workspace_id),
            user_id=str(user_id),
            rpm_current=result.rpm_current,
            rpm_limit=result.rpm_limit,
            daily_current=result.daily_current,
            daily_limit=result.daily_limit,
            retry_after_s=result.retry_after_s,
        )
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "error":         "rate_limit_exceeded",
                "rpm_current":   result.rpm_current,
                "rpm_limit":     result.rpm_limit,
                "daily_current": result.daily_current,
                "daily_limit":   result.daily_limit,
                "retry_after_s": result.retry_after_s,
            },
            headers={"Retry-After": str(result.retry_after_s)},
        )

    logger.debug(
        "rate_limit.passed",
        workspace_id=str(workspace_id),
        rpm_current=result.rpm_current,
        daily_current=result.daily_current,
    )
    return result