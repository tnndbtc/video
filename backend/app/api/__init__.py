"""
BeatStitch API routes package.

Contains all API endpoint routers for the application.
"""

from fastapi import APIRouter

from .auth import router as auth_router
from .audio import router as audio_router
from .edit_request import router as edit_request_router
from .media import router as media_router
from .projects import router as projects_router
from .timeline import router as timeline_router
from .render import router as render_router

# Main API router that includes all sub-routers
api_router = APIRouter()

# Include auth routes
api_router.include_router(auth_router, prefix="/auth", tags=["auth"])

# Include projects routes
api_router.include_router(projects_router, prefix="/projects", tags=["projects"])

# Include audio routes (nested under projects)
api_router.include_router(audio_router, prefix="/projects", tags=["audio"])

# Include media routes (some under /projects, some under /media)
api_router.include_router(media_router, tags=["media"])

# Include timeline routes (nested under projects)
api_router.include_router(timeline_router, prefix="/projects", tags=["timeline"])

# Include render routes (nested under projects)
api_router.include_router(render_router, prefix="/projects", tags=["render"])

# Include EditRequest (EDL v1) routes (nested under projects)
api_router.include_router(edit_request_router, prefix="/projects", tags=["edl"])

__all__ = [
    "api_router",
    "auth_router",
    "audio_router",
    "edit_request_router",
    "media_router",
    "projects_router",
    "timeline_router",
    "render_router",
]
