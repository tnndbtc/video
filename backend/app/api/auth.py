"""
Authentication endpoints for BeatStitch.

Provides user registration and login functionality with JWT tokens.
"""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_async_session
from app.core.security import (
    ACCESS_TOKEN_EXPIRE_HOURS,
    create_access_token,
    hash_password,
    verify_password,
)
from app.models.user import User

router = APIRouter()


# =============================================================================
# Pydantic Schemas
# =============================================================================


class UserRegisterRequest(BaseModel):
    """Request schema for user registration."""

    username: str = Field(
        ...,
        min_length=3,
        max_length=50,
        description="Unique username (3-50 characters)",
    )
    password: str = Field(
        ...,
        min_length=8,
        max_length=128,
        description="Password (8-128 characters)",
    )

    @field_validator("username")
    @classmethod
    def validate_username(cls, v: str) -> str:
        """Validate username format."""
        # Strip whitespace
        v = v.strip()
        if not v:
            raise ValueError("Username cannot be empty")
        # Check for valid characters (alphanumeric and underscores)
        if not v.replace("_", "").isalnum():
            raise ValueError(
                "Username can only contain letters, numbers, and underscores"
            )
        return v


class UserRegisterResponse(BaseModel):
    """Response schema for successful registration."""

    id: str
    username: str
    created_at: datetime

    model_config = {"from_attributes": True}


class UserLoginRequest(BaseModel):
    """Request schema for user login."""

    username: str = Field(..., description="Username")
    password: str = Field(..., description="Password")


class UserInfo(BaseModel):
    """User info included in login response."""

    id: str
    username: str


class UserLoginResponse(BaseModel):
    """Response schema for successful login."""

    access_token: str
    token_type: str = "bearer"
    expires_in: int = Field(
        default_factory=lambda: ACCESS_TOKEN_EXPIRE_HOURS * 3600,
        description="Token expiration time in seconds",
    )
    user: UserInfo


class ErrorResponse(BaseModel):
    """Standard error response."""

    error: str
    message: str
    details: Optional[dict] = None


# =============================================================================
# Endpoints
# =============================================================================


@router.post(
    "/register",
    response_model=UserRegisterResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        400: {"model": ErrorResponse, "description": "Validation error"},
    },
)
async def register(
    data: UserRegisterRequest,
    db: AsyncSession = Depends(get_async_session),
) -> UserRegisterResponse:
    """
    Register a new user.

    Creates a new user account with the provided username and password.
    The password is securely hashed before storage.

    Args:
        data: Registration request with username and password
        db: Database session

    Returns:
        Created user information (id, username, created_at)

    Raises:
        HTTPException 400: If username already exists or validation fails
    """
    # Check if username already exists
    result = await db.execute(select(User).where(User.username == data.username))
    existing_user = result.scalar_one_or_none()

    if existing_user is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "validation_error",
                "message": "Username already exists",
                "details": {"field": "username"},
            },
        )

    # Create new user
    user = User(
        username=data.username,
        password_hash=hash_password(data.password),
    )
    db.add(user)
    await db.flush()  # Flush to get the generated ID
    await db.refresh(user)  # Refresh to get all fields

    return UserRegisterResponse(
        id=user.id,
        username=user.username,
        created_at=user.created_at,
    )


@router.post(
    "/login",
    response_model=UserLoginResponse,
    responses={
        400: {"model": ErrorResponse, "description": "Validation error"},
        401: {"model": ErrorResponse, "description": "Invalid credentials"},
    },
)
async def login(
    data: UserLoginRequest,
    db: AsyncSession = Depends(get_async_session),
) -> UserLoginResponse:
    """
    Login and get JWT access token.

    Authenticates user with username and password, returning a JWT token
    for subsequent API requests.

    Args:
        data: Login request with username and password
        db: Database session

    Returns:
        JWT access token and user information

    Raises:
        HTTPException 401: If credentials are invalid
    """
    # Find user by username
    result = await db.execute(select(User).where(User.username == data.username))
    user = result.scalar_one_or_none()

    # Check if user exists and password is correct
    if user is None or not verify_password(data.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "error": "unauthorized",
                "message": "Invalid username or password",
            },
        )

    # Create access token
    access_token = create_access_token(user_id=user.id)

    return UserLoginResponse(
        access_token=access_token,
        token_type="bearer",
        expires_in=ACCESS_TOKEN_EXPIRE_HOURS * 3600,
        user=UserInfo(id=user.id, username=user.username),
    )
