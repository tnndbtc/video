"""
Redis Connection Management

Provides Redis connection pool/client with:
- Connection from REDIS_URL environment variable
- Connection health check functionality
- Connection pooling for efficient resource usage
"""

import os
from dataclasses import dataclass
from typing import Optional
from redis import Redis, ConnectionPool
from redis.exceptions import ConnectionError, TimeoutError


# Module-level connection pool singleton
_connection_pool: Optional[ConnectionPool] = None


def get_redis_url() -> str:
    """
    Get Redis URL from environment variable.

    Returns:
        str: Redis URL, defaults to redis://localhost:6379/0
    """
    return os.environ.get("REDIS_URL", "redis://localhost:6379/0")


def get_connection_pool() -> ConnectionPool:
    """
    Get or create the Redis connection pool singleton.

    Returns:
        ConnectionPool: Redis connection pool instance
    """
    global _connection_pool

    if _connection_pool is None:
        redis_url = get_redis_url()
        _connection_pool = ConnectionPool.from_url(
            redis_url,
            max_connections=10,
            decode_responses=True,  # Return strings instead of bytes
        )

    return _connection_pool


def get_redis_connection() -> Redis:
    """
    Get a Redis connection from the connection pool.

    This is the preferred way to get a Redis connection as it
    uses connection pooling for efficient resource management.

    Returns:
        Redis: Redis client instance

    Example:
        >>> redis = get_redis_connection()
        >>> redis.set("key", "value")
        >>> redis.get("key")
        'value'
    """
    pool = get_connection_pool()
    return Redis(connection_pool=pool)


def get_redis_client() -> Redis:
    """
    Alias for get_redis_connection() for backward compatibility.

    Returns:
        Redis: Redis client instance
    """
    return get_redis_connection()


@dataclass
class RedisHealthStatus:
    """Health status for Redis connection."""
    healthy: bool
    latency_ms: Optional[float] = None
    error: Optional[str] = None
    info: Optional[dict] = None


def check_redis_health(timeout: float = 5.0) -> RedisHealthStatus:
    """
    Check the health of the Redis connection.

    Performs a PING command and measures latency.
    Optionally retrieves basic Redis server info.

    Args:
        timeout: Connection timeout in seconds

    Returns:
        RedisHealthStatus: Health status including latency and any errors

    Example:
        >>> status = check_redis_health()
        >>> if status.healthy:
        ...     print(f"Redis OK, latency: {status.latency_ms}ms")
        ... else:
        ...     print(f"Redis unhealthy: {status.error}")
    """
    import time

    try:
        redis_url = get_redis_url()
        # Create a fresh connection for health check with timeout
        client = Redis.from_url(
            redis_url,
            socket_timeout=timeout,
            socket_connect_timeout=timeout,
            decode_responses=True,
        )

        # Measure PING latency
        start = time.perf_counter()
        pong = client.ping()
        latency_ms = (time.perf_counter() - start) * 1000

        if not pong:
            return RedisHealthStatus(
                healthy=False,
                error="PING returned False",
            )

        # Get basic server info
        info = client.info(section="server")

        return RedisHealthStatus(
            healthy=True,
            latency_ms=round(latency_ms, 2),
            info={
                "redis_version": info.get("redis_version"),
                "uptime_in_seconds": info.get("uptime_in_seconds"),
            },
        )

    except ConnectionError as e:
        return RedisHealthStatus(
            healthy=False,
            error=f"Connection failed: {str(e)}",
        )
    except TimeoutError as e:
        return RedisHealthStatus(
            healthy=False,
            error=f"Connection timeout: {str(e)}",
        )
    except Exception as e:
        return RedisHealthStatus(
            healthy=False,
            error=f"Unexpected error: {str(e)}",
        )


def close_connection_pool() -> None:
    """
    Close and reset the connection pool.

    Useful for cleanup during testing or shutdown.
    """
    global _connection_pool

    if _connection_pool is not None:
        _connection_pool.disconnect()
        _connection_pool = None
