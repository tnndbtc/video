"""
Application Configuration

Settings class using pydantic-settings for environment variable loading.
Defines resource limits and application configuration.
"""

import os
from functools import lru_cache
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Application settings loaded from environment variables.

    All settings can be overridden via environment variables.
    For example, MAX_UPLOAD_SIZE can be set via MAX_UPLOAD_SIZE env var.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Application
    app_name: str = Field(default="BeatStitch API", description="Application name")
    debug: bool = Field(default=False, description="Debug mode")
    version: str = Field(default="0.1.0", description="API version")

    # Security
    secret_key: str = Field(
        default="change-me-in-production-min-32-chars",
        description="Secret key for JWT signing (min 32 characters)",
    )
    access_token_expire_hours: int = Field(
        default=24,
        description="Access token expiration time in hours",
    )

    # Database
    database_url: str = Field(
        default="postgresql+asyncpg://beatstitch:beatstitch@localhost:5432/beatstitch",
        description="Database connection URL",
    )

    # Redis
    redis_url: str = Field(
        default="redis://localhost:6379/0",
        description="Redis connection URL",
    )

    # Storage
    storage_path: str = Field(
        default="/data",
        alias="STORAGE_PATH",
        description="Root path for file storage",
    )

    # Resource Limits
    max_upload_size: int = Field(
        default=500 * 1024 * 1024,  # 500MB
        description="Maximum upload file size in bytes (default: 500MB)",
    )
    max_media_per_project: int = Field(
        default=50,
        description="Maximum number of media files per project",
    )
    max_projects_per_user: int = Field(
        default=20,
        description="Maximum number of projects per user",
    )
    max_video_duration: int = Field(
        default=600,  # 10 minutes
        description="Maximum video duration in seconds (default: 10 minutes)",
    )

    # CORS
    cors_origins: str = Field(
        default="http://localhost:3000",
        description="Comma-separated list of allowed CORS origins",
    )

    @property
    def cors_origins_list(self) -> list[str]:
        """Parse CORS origins from comma-separated string to list."""
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def storage_root(self) -> str:
        """Alias for storage_path for consistency with design docs."""
        return self.storage_path


@lru_cache()
def get_settings() -> Settings:
    """
    Get cached application settings instance.

    Uses lru_cache to ensure settings are only loaded once per process.

    Returns:
        Settings: Application settings instance

    Example:
        >>> settings = get_settings()
        >>> print(settings.max_upload_size)
        524288000
    """
    return Settings()


# Convenience function for direct access
settings = get_settings()
