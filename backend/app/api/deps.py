"""
Common dependencies for BeatStitch API endpoints.

Provides reusable FastAPI dependencies for database sessions,
authentication, and other shared functionality.
"""

from typing import AsyncGenerator

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_async_session
from app.core.security import get_current_user
from app.models.user import User


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Database session dependency.

    Provides an async database session for route handlers.
    The session is automatically committed on success or
    rolled back on exception.

    Usage:
        @router.get("/items")
        async def get_items(db: AsyncSession = Depends(get_db)):
            ...
    """
    async for session in get_async_session():
        yield session


async def get_current_active_user(
    current_user: User = Depends(get_current_user),
) -> User:
    """
    Get the current authenticated user.

    This dependency extracts the JWT token from the Authorization header,
    validates it, and returns the corresponding User object.

    Usage:
        @router.get("/profile")
        async def get_profile(user: User = Depends(get_current_active_user)):
            return {"username": user.username}

    Raises:
        HTTPException 401: If token is invalid, expired, or user not found
    """
    return current_user


# Re-export commonly used dependencies for convenience
__all__ = [
    "get_db",
    "get_current_active_user",
    "get_current_user",
]
