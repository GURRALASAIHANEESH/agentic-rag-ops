from datetime import timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import get_db
from app.core.security import (
    hash_password, verify_password,
    create_access_token, create_refresh_token,
    decode_token, get_current_user_payload,
    get_user_id_from_payload,
)
from app.core.config import get_settings
from app.core.logging import get_logger
from app.models.user import User, Workspace
from app.schemas.auth import (
    SignupRequest, SignupResponse, LoginRequest,
    RefreshRequest, TokenResponse, UserResponse,
    WorkspaceCreateRequest, WorkspaceResponse,
)

router = APIRouter()
settings = get_settings()
logger = get_logger(__name__)


# ── POST /api/auth/signup ─────────────────────────────────────────────────────

@router.post(
    "/signup",
    response_model=SignupResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new user",
)
async def signup(
    body: SignupRequest,
    db: AsyncSession = Depends(get_db),
):
    # Check duplicate email
    existing = await db.execute(
        select(User).where(User.email == body.email.lower())
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists.",
        )

    # Create user
    user = User(
        email=body.email.lower(),
        full_name=body.full_name,
        hashed_password=hash_password(body.password),
        role="user",
    )
    db.add(user)
    await db.flush()   # get user.id before creating workspace

    # Auto-create a default workspace for the new user
    workspace = Workspace(
        owner_id=user.id,
        name="My Workspace",
        description="Default workspace",
    )
    db.add(workspace)
    await db.commit()
    await db.refresh(user)

    # Issue tokens
    access_token = create_access_token(
        subject=str(user.id),
        role=user.role,
        workspace_id=str(workspace.id),
    )
    refresh_token = create_refresh_token(subject=str(user.id))

    logger.info("user_signup", user_id=str(user.id), email=user.email)

    return SignupResponse(
        user=UserResponse.model_validate(user),
        tokens=TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        ),
    )


# ── POST /api/auth/login ──────────────────────────────────────────────────────

@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Login and receive JWT tokens",
)
async def login(
    body: LoginRequest,
    db: AsyncSession = Depends(get_db),
):
    # Fetch user
    result = await db.execute(
        select(User).where(User.email == body.email.lower())
    )
    user = result.scalar_one_or_none()

    # Use constant-time comparison to prevent timing attacks
    if not user or not verify_password(body.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is deactivated.",
        )

    # Fetch user's first workspace for token claim
    ws_result = await db.execute(
        select(Workspace).where(Workspace.owner_id == user.id).limit(1)
    )
    workspace = ws_result.scalar_one_or_none()

    access_token = create_access_token(
        subject=str(user.id),
        role=user.role,
        workspace_id=str(workspace.id) if workspace else None,
    )
    refresh_token = create_refresh_token(subject=str(user.id))

    logger.info("user_login", user_id=str(user.id))

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


# ── POST /api/auth/refresh ────────────────────────────────────────────────────

@router.post(
    "/refresh",
    response_model=TokenResponse,
    summary="Refresh access token using refresh token",
)
async def refresh_token(
    body: RefreshRequest,
    db: AsyncSession = Depends(get_db),
):
    payload = decode_token(body.refresh_token)

    # Ensure it's actually a refresh token
    if payload.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid token type. Expected refresh token.",
        )

    user_id = get_user_id_from_payload(payload)
    user = await db.get(User, user_id)

    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or deactivated.",
        )

    ws_result = await db.execute(
        select(Workspace).where(Workspace.owner_id == user.id).limit(1)
    )
    workspace = ws_result.scalar_one_or_none()

    new_access = create_access_token(
        subject=str(user.id),
        role=user.role,
        workspace_id=str(workspace.id) if workspace else None,
    )
    new_refresh = create_refresh_token(subject=str(user.id))

    return TokenResponse(
        access_token=new_access,
        refresh_token=new_refresh,
        expires_in=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


# ── GET /api/auth/me ──────────────────────────────────────────────────────────

@router.get(
    "/me",
    response_model=UserResponse,
    summary="Get current authenticated user",
)
async def get_me(
    payload: dict = Depends(get_current_user_payload),
    db: AsyncSession = Depends(get_db),
):
    user_id = get_user_id_from_payload(payload)
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")
    return UserResponse.model_validate(user)


# ── POST /api/auth/workspaces ─────────────────────────────────────────────────

@router.post(
    "/workspaces",
    response_model=WorkspaceResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new workspace",
)
async def create_workspace(
    body: WorkspaceCreateRequest,
    payload: dict = Depends(get_current_user_payload),
    db: AsyncSession = Depends(get_db),
):
    user_id = get_user_id_from_payload(payload)
    workspace = Workspace(
        owner_id=user_id,
        name=body.name,
        description=body.description,
    )
    db.add(workspace)
    await db.commit()
    await db.refresh(workspace)
    return WorkspaceResponse.model_validate(workspace)


# ── GET /api/auth/workspaces ──────────────────────────────────────────────────

@router.get(
    "/workspaces",
    response_model=list[WorkspaceResponse],
    summary="List all workspaces for current user",
)
async def list_workspaces(
    payload: dict = Depends(get_current_user_payload),
    db: AsyncSession = Depends(get_db),
):
    user_id = get_user_id_from_payload(payload)
    result = await db.execute(
        select(Workspace).where(Workspace.owner_id == user_id)
    )
    workspaces = result.scalars().all()
    return [WorkspaceResponse.model_validate(w) for w in workspaces]
