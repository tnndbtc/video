"""
Pydantic schemas for BeatStitch API.
"""

from .audio import (
    AnalyzeConflictResponse,
    AnalyzeResponse,
    AudioNotFoundError,
    AudioUploadResponse,
    Beat,
    BeatsNotFoundError,
    BeatsResponse,
    BeatsStatusResponse,
)
from .project import (
    ProjectCreate,
    ProjectUpdate,
    ProjectSettings,
    ProjectSettingsUpdate,
    ProjectResponse,
    ProjectListItem,
    ProjectListResponse,
    ProjectStatusResponse,
    ProjectSettingsResponse,
    MediaStatusCounts,
    AudioStatus,
    TimelineStatus,
)
from .timeline import (
    TimelineGenerateResponse,
    TimelineGenerateConflictResponse,
    TimelineGeneratePreconditionResponse,
    TimelineTransition,
    TimelineEffects,
    TimelineSegment,
    TimelineSettingsUsed,
    TimelineResponse,
    TimelineNotFoundResponse,
    TimelineStatusResponse,
)
from .render import (
    RenderRequest,
    RenderResponse,
    RenderJobStatus,
    RenderEdlHashMismatchResponse,
    RenderPreconditionFailedResponse,
    RenderConflictResponse,
    RenderNotFoundResponse,
)

__all__ = [
    # Audio schemas
    "AnalyzeConflictResponse",
    "AnalyzeResponse",
    "AudioNotFoundError",
    "AudioUploadResponse",
    "Beat",
    "BeatsNotFoundError",
    "BeatsResponse",
    "BeatsStatusResponse",
    # Project schemas
    "ProjectCreate",
    "ProjectUpdate",
    "ProjectSettings",
    "ProjectSettingsUpdate",
    "ProjectResponse",
    "ProjectListItem",
    "ProjectListResponse",
    "ProjectStatusResponse",
    "ProjectSettingsResponse",
    "MediaStatusCounts",
    "AudioStatus",
    "TimelineStatus",
    # Timeline schemas
    "TimelineGenerateResponse",
    "TimelineGenerateConflictResponse",
    "TimelineGeneratePreconditionResponse",
    "TimelineTransition",
    "TimelineEffects",
    "TimelineSegment",
    "TimelineSettingsUsed",
    "TimelineResponse",
    "TimelineNotFoundResponse",
    "TimelineStatusResponse",
    # Render schemas
    "RenderRequest",
    "RenderResponse",
    "RenderJobStatus",
    "RenderEdlHashMismatchResponse",
    "RenderPreconditionFailedResponse",
    "RenderConflictResponse",
    "RenderNotFoundResponse",
]
