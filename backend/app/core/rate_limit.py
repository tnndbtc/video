"""
Rate Limiting Middleware

Provides rate limiting keyed by ACTION CATEGORY (not URL path).
This ensures that different URL paths for the same action type share limits,
preventing bypass via parameterized URLs (e.g., /projects/abc/render vs /projects/xyz/render).
"""

import json
from typing import Callable, Optional

from fastapi import HTTPException, Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from starlette.routing import Match

from .redis import get_redis_connection


# Rate limits by category: (requests, window_seconds)
RATE_LIMITS: dict[str, tuple[int, int]] = {
    "upload": (10, 60),      # 10 requests per minute
    "render": (20, 300),     # 20 requests per 5 minutes (increased for dev)
    "analyze": (10, 60),     # 10 requests per minute
    "default": (500, 60),    # 500 requests per minute (allows for polling)
}

# Map route names to rate limit categories
# Route names are defined in FastAPI endpoint decorators: @router.post("/path", name="route_name")
ROUTE_CATEGORIES: dict[str, str] = {
    # Upload operations
    "upload_media": "upload",
    "upload_audio": "upload",
    "upload_file": "upload",
    "upload_video": "upload",
    "upload_image": "upload",

    # Render operations
    "start_render": "render",
    "render_preview": "render",
    "render_final": "render",
    "queue_render": "render",

    # Analysis operations
    "analyze_audio": "analyze",
    "analyze_beats": "analyze",
    "generate_timeline": "analyze",
    "detect_beats": "analyze",
}


def get_rate_limit_category(request: Request) -> str:
    """
    Determine the rate limit category from the route name, not URL path.

    This ensures that parameterized URLs share rate limits:
    - /projects/abc/render and /projects/xyz/render share the "render" limit
    - /projects/abc/upload and /projects/xyz/upload share the "upload" limit

    Args:
        request: The incoming FastAPI request

    Returns:
        str: Rate limit category name ("upload", "render", "analyze", or "default")

    Example:
        >>> # Request to POST /projects/{id}/render (route name: "start_render")
        >>> category = get_rate_limit_category(request)
        >>> category
        'render'
    """
    # Iterate through all routes to find the matching one
    for route in request.app.routes:
        # Check if this route matches the current request
        match, _ = route.matches(request.scope)

        if match == Match.FULL:
            # Get the route name (set via name= parameter in decorator)
            route_name = getattr(route, "name", None)

            if route_name and route_name in ROUTE_CATEGORIES:
                return ROUTE_CATEGORIES[route_name]

    # Default category if no specific mapping found
    return "default"


def get_rate_limit_key(user_id: str, category: str) -> str:
    """
    Generate a Redis key for rate limiting.

    Key format: ratelimit:{user_id}:{category}

    Args:
        user_id: User identifier (or "anonymous" for unauthenticated requests)
        category: Rate limit category

    Returns:
        str: Redis key for rate limiting
    """
    return f"ratelimit:{user_id}:{category}"


async def check_rate_limit(user_id: str, category: str) -> tuple[bool, int, int]:
    """
    Check if a request is within rate limits.

    Args:
        user_id: User identifier
        category: Rate limit category

    Returns:
        tuple: (is_allowed, current_count, retry_after_seconds)
    """
    limit, window = RATE_LIMITS.get(category, RATE_LIMITS["default"])
    key = get_rate_limit_key(user_id, category)

    redis = get_redis_connection()

    # Get current count
    current = redis.get(key)
    current_count = int(current) if current else 0

    if current_count >= limit:
        # Rate limit exceeded
        ttl = redis.ttl(key)
        return False, current_count, max(ttl, 0)

    # Increment counter using pipeline for atomicity
    pipe = redis.pipeline()
    pipe.incr(key)
    pipe.expire(key, window)
    pipe.execute()

    return True, current_count + 1, 0


async def rate_limit_middleware(request: Request, call_next: Callable) -> Response:
    """
    Rate limiting middleware function.

    Checks rate limits based on user ID + action category, not URL path.
    This prevents rate limit bypass via parameterized URLs.

    Args:
        request: The incoming request
        call_next: The next middleware/handler in the chain

    Returns:
        Response: Either the handler response or a 429 error

    Raises:
        HTTPException: 429 Too Many Requests if rate limit exceeded
    """
    # Get user ID from request state (set by auth middleware)
    # Fall back to IP address for anonymous users
    user_id = getattr(request.state, "user_id", None)

    if user_id is None:
        # Use client IP for anonymous rate limiting
        client_host = request.client.host if request.client else "unknown"
        user_id = f"anon:{client_host}"

    # Get the rate limit category based on route name
    category = get_rate_limit_category(request)

    # Check rate limit
    is_allowed, current_count, retry_after = await check_rate_limit(user_id, category)

    if not is_allowed:
        limit, window = RATE_LIMITS.get(category, RATE_LIMITS["default"])
        # Return JSONResponse instead of raising HTTPException
        # (HTTPException raised in BaseHTTPMiddleware doesn't get caught by FastAPI handlers)
        return JSONResponse(
            status_code=429,
            content={
                "detail": {
                    "error": "rate_limit_exceeded",
                    "message": f"Rate limit exceeded for {category}",
                    "category": category,
                    "limit": limit,
                    "window_seconds": window,
                    "retry_after_seconds": retry_after,
                }
            },
            headers={
                "Retry-After": str(retry_after),
                "X-RateLimit-Limit": str(limit),
                "X-RateLimit-Remaining": "0",
                "X-RateLimit-Reset": str(retry_after),
            },
        )

    # Call the next handler
    response = await call_next(request)

    # Add rate limit headers to response
    limit, window = RATE_LIMITS.get(category, RATE_LIMITS["default"])
    response.headers["X-RateLimit-Limit"] = str(limit)
    response.headers["X-RateLimit-Remaining"] = str(max(0, limit - current_count))
    response.headers["X-RateLimit-Category"] = category

    return response


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Rate limiting middleware class for FastAPI.

    Usage:
        app.add_middleware(RateLimitMiddleware)

    This middleware checks rate limits based on:
    - User ID (from authenticated requests) or IP address (for anonymous)
    - Action category (derived from route name, not URL path)

    Rate limit categories and their limits:
    - upload: 10 requests per minute
    - render: 5 requests per 5 minutes
    - analyze: 10 requests per minute
    - default: 100 requests per minute
    """

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """
        Process the request with rate limiting.

        Args:
            request: The incoming request
            call_next: The next middleware/handler

        Returns:
            Response: The response with rate limit headers
        """
        return await rate_limit_middleware(request, call_next)


def register_route_category(route_name: str, category: str) -> None:
    """
    Register a route name to a rate limit category.

    This allows dynamic registration of rate limit categories for routes
    that aren't known at import time.

    Args:
        route_name: The FastAPI route name
        category: The rate limit category

    Example:
        >>> register_route_category("my_custom_upload", "upload")
    """
    if category not in RATE_LIMITS:
        raise ValueError(f"Unknown category: {category}. Valid categories: {list(RATE_LIMITS.keys())}")

    ROUTE_CATEGORIES[route_name] = category


def get_rate_limit_info(category: str) -> dict:
    """
    Get rate limit information for a category.

    Args:
        category: Rate limit category name

    Returns:
        dict: Rate limit info including limit and window

    Example:
        >>> get_rate_limit_info("upload")
        {'category': 'upload', 'limit': 10, 'window_seconds': 60}
    """
    limit, window = RATE_LIMITS.get(category, RATE_LIMITS["default"])
    return {
        "category": category,
        "limit": limit,
        "window_seconds": window,
    }
