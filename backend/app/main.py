"""
BeatStitch Backend API

Main FastAPI application entry point.
"""

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.api import api_router
from app.core.config import get_settings
from app.core.database import async_engine
from app.core.rate_limit import RateLimitMiddleware
from app.core.redis import check_redis_health

# Load settings
settings = get_settings()

app = FastAPI(
    title="BeatStitch API",
    description="Beat-Synced Video Editor Backend",
    version=settings.version,
)


# Request body size limit middleware
@app.middleware("http")
async def limit_request_body_size(request: Request, call_next):
    """
    Middleware to enforce maximum request body size.

    Prevents uploads larger than MAX_UPLOAD_SIZE (default 500MB).
    """
    content_length = request.headers.get("content-length")

    if content_length:
        content_length = int(content_length)
        if content_length > settings.max_upload_size:
            return JSONResponse(
                status_code=413,
                content={
                    "error": "request_entity_too_large",
                    "message": f"Request body too large. Maximum size: {settings.max_upload_size} bytes ({settings.max_upload_size // (1024 * 1024)}MB)",
                    "max_size_bytes": settings.max_upload_size,
                },
            )

    return await call_next(request)


# Rate limiting middleware (keyed by action category, not URL)
app.add_middleware(RateLimitMiddleware)

# CORS configuration (loaded from environment)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=[
        "X-RateLimit-Limit",
        "X-RateLimit-Remaining",
        "X-RateLimit-Category",
        "Retry-After",
    ],
)

# Include API routes
app.include_router(api_router, prefix="/api")


@app.get("/")
async def root():
    """Root endpoint - API info."""
    return {
        "name": "BeatStitch API",
        "version": settings.version,
        "status": "running",
    }


@app.get("/health")
async def health_check():
    """
    Health check endpoint for Docker/orchestration.

    Checks the health of:
    - Database connection
    - Redis connection

    Returns overall status and individual check results.
    """
    checks = {}
    healthy = True

    # Check database connection
    try:
        async with async_engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        checks["database"] = {"status": "healthy"}
    except Exception as e:
        checks["database"] = {"status": "unhealthy", "error": str(e)}
        healthy = False

    # Check Redis connection
    redis_status = check_redis_health()
    if redis_status.healthy:
        checks["redis"] = {
            "status": "healthy",
            "latency_ms": redis_status.latency_ms,
        }
    else:
        checks["redis"] = {
            "status": "unhealthy",
            "error": redis_status.error,
        }
        healthy = False

    return {
        "status": "healthy" if healthy else "unhealthy",
        "checks": checks,
        "version": settings.version,
    }
