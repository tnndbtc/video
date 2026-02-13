# Core modules for BeatStitch backend
from .config import Settings, get_settings, settings
from .database import Base, get_async_session, async_engine, AsyncSessionLocal
from .rate_limit import (
    RateLimitMiddleware,
    rate_limit_middleware,
    get_rate_limit_category,
    RATE_LIMITS,
    ROUTE_CATEGORIES,
    register_route_category,
)
from .redis import (
    get_redis_connection,
    get_redis_client,
    check_redis_health,
    RedisHealthStatus,
)
from .queue import (
    enqueue_job,
    enqueue_beat_analysis,
    enqueue_timeline_generation,
    enqueue_render_preview,
    enqueue_render_final,
    enqueue_thumbnail_generation,
    update_progress,
    get_progress,
    JOB_TIMEOUTS,
)
from .security import (
    hash_password,
    verify_password,
    create_access_token,
    decode_token,
    get_current_user,
)
from .storage import (
    ALLOWED_EXTENSIONS,
    STORAGE_ROOT,
    sanitize_filename,
    generate_safe_path,
    validate_file_type,
    validate_project_id,
    get_file_category,
    ensure_project_directories,
    get_project_path,
    get_storage_root,
)

__all__ = [
    # Config
    "Settings",
    "get_settings",
    "settings",
    # Database
    "Base",
    "get_async_session",
    "async_engine",
    "AsyncSessionLocal",
    # Rate Limiting
    "RateLimitMiddleware",
    "rate_limit_middleware",
    "get_rate_limit_category",
    "RATE_LIMITS",
    "ROUTE_CATEGORIES",
    "register_route_category",
    # Redis
    "get_redis_connection",
    "get_redis_client",
    "check_redis_health",
    "RedisHealthStatus",
    # Queue
    "enqueue_job",
    "enqueue_beat_analysis",
    "enqueue_timeline_generation",
    "enqueue_render_preview",
    "enqueue_render_final",
    "enqueue_thumbnail_generation",
    "update_progress",
    "get_progress",
    "JOB_TIMEOUTS",
    # Security
    "hash_password",
    "verify_password",
    "create_access_token",
    "decode_token",
    "get_current_user",
    # Storage
    "ALLOWED_EXTENSIONS",
    "STORAGE_ROOT",
    "sanitize_filename",
    "generate_safe_path",
    "validate_file_type",
    "validate_project_id",
    "get_file_category",
    "ensure_project_directories",
    "get_project_path",
    "get_storage_root",
]
