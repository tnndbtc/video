"""
File Storage & Security

Provides secure file path handling with:
- Path traversal prevention
- Filename sanitization
- File type validation
- UUID validation for project IDs
"""

import os
import re
from pathlib import Path
from uuid import UUID, uuid4

from .config import get_settings


# Allowed file extensions by category
ALLOWED_EXTENSIONS: dict[str, set[str]] = {
    "image": {".jpg", ".jpeg", ".png", ".gif", ".webp"},
    "video": {".mp4", ".mov", ".avi", ".mkv", ".webm"},
    "audio": {".mp3", ".wav", ".flac", ".aac", ".m4a", ".ogg"},
}

# Valid storage categories
VALID_CATEGORIES: set[str] = {"media", "audio", "image", "video"}


def get_storage_root() -> Path:
    """
    Get the storage root path from configuration.

    Returns:
        Path: Resolved storage root path

    Raises:
        ValueError: If storage path is not configured or invalid
    """
    settings = get_settings()
    storage_path = settings.storage_path

    if not storage_path:
        raise ValueError("STORAGE_PATH environment variable not set")

    return Path(storage_path).resolve()


# Module-level constant for convenience (lazy-loaded on first access)
def _get_storage_root_cached() -> Path:
    """Get storage root with error handling for module initialization."""
    try:
        return get_storage_root()
    except Exception:
        # Default fallback for testing/development
        return Path("/data").resolve()


STORAGE_ROOT = _get_storage_root_cached()


def _mkdir_world_writable(path: Path) -> None:
    """
    Create a directory (and all parents) with world-writable permissions (0o777).
    Required for multi-container setups where backend creates dirs and worker writes to them.
    """
    path.mkdir(parents=True, exist_ok=True)
    os.chmod(path, 0o777)


def sanitize_filename(filename: str) -> str:
    """
    Sanitize a filename to prevent path traversal and other security issues.

    - Strips directory components (basename only)
    - Removes null bytes
    - Removes characters that are problematic on various filesystems
    - Limits filename length to 100 characters (excluding extension)

    Args:
        filename: Original filename to sanitize

    Returns:
        str: Sanitized filename safe for filesystem use

    Example:
        >>> sanitize_filename("../../../etc/passwd")
        'passwd'
        >>> sanitize_filename("my<file>name.mp4")
        'myfilename.mp4'
        >>> sanitize_filename("a" * 200 + ".mp4")
        'aaaa...aaa.mp4'  # truncated to 100 chars + extension
    """
    # Get only the base filename (prevents ../.. attacks)
    filename = os.path.basename(filename)

    # Remove null bytes (can bypass security checks)
    filename = filename.replace("\x00", "")

    # Remove characters problematic on Windows/Unix/URLs
    # < > : " / \ | ? * are forbidden on Windows
    # Also remove control characters and other problematic chars
    filename = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "", filename)

    # Split name and extension
    name, ext = os.path.splitext(filename)

    # Remove leading/trailing dots and spaces from name
    name = name.strip(". ")

    # Limit name length (preserve extension)
    name = name[:100]

    # If name is empty after sanitization, generate a random one
    if not name:
        name = uuid4().hex[:8]

    return f"{name}{ext}"


def validate_project_id(project_id: str) -> bool:
    """
    Validate that a project ID is a valid UUID.

    Args:
        project_id: Project ID string to validate

    Returns:
        bool: True if valid UUID, False otherwise

    Example:
        >>> validate_project_id("550e8400-e29b-41d4-a716-446655440000")
        True
        >>> validate_project_id("../malicious")
        False
    """
    try:
        UUID(project_id)
        return True
    except (ValueError, TypeError):
        return False


def generate_safe_path(project_id: str, category: str, filename: str) -> Path:
    """
    Generate a safe filesystem path for storing uploaded files.

    The path is structured as:
        {STORAGE_ROOT}/uploads/{project_id}/{category}/{uuid}_{sanitized_filename}

    Security measures:
    - Validates project_id is a valid UUID
    - Validates category is in allowed list
    - Sanitizes filename to prevent path traversal
    - Adds UUID prefix to prevent filename collisions
    - Verifies final path is within storage root

    Args:
        project_id: UUID string identifying the project
        category: File category ("media", "audio", "image", "video")
        filename: Original filename from upload

    Returns:
        Path: Safe absolute path for storing the file

    Raises:
        ValueError: If project_id is invalid, category is invalid,
                   or path traversal is detected

    Example:
        >>> path = generate_safe_path(
        ...     "550e8400-e29b-41d4-a716-446655440000",
        ...     "media",
        ...     "my_video.mp4"
        ... )
        >>> str(path)
        '/data/uploads/550e8400-e29b-41d4-a716-446655440000/media/a1b2c3d4_my_video.mp4'
    """
    # Validate project_id is a valid UUID
    try:
        UUID(project_id)
    except (ValueError, TypeError):
        raise ValueError(f"Invalid project ID: must be a valid UUID")

    # Validate category
    if category not in VALID_CATEGORIES:
        raise ValueError(f"Invalid category: {category}. Must be one of: {', '.join(VALID_CATEGORIES)}")

    # Sanitize the filename
    safe_filename = sanitize_filename(filename)

    # Add UUID prefix to prevent collisions
    unique_filename = f"{uuid4().hex[:8]}_{safe_filename}"

    # Build the path
    storage_root = get_storage_root()
    path = storage_root / "uploads" / project_id / category / unique_filename

    # Resolve the path and verify it's within storage root
    resolved_path = path.resolve()
    resolved_root = storage_root.resolve()

    if not str(resolved_path).startswith(str(resolved_root) + os.sep):
        raise ValueError("Path traversal detected: path escapes storage root")

    return resolved_path


def validate_file_type(filename: str, expected_type: str) -> bool:
    """
    Validate that a filename has an allowed extension for the expected type.

    Args:
        filename: Filename to check (can include path)
        expected_type: Expected file type category ("image", "video", "audio")

    Returns:
        bool: True if extension is allowed for the type, False otherwise

    Example:
        >>> validate_file_type("video.mp4", "video")
        True
        >>> validate_file_type("video.mp4", "audio")
        False
        >>> validate_file_type("script.exe", "video")
        False
    """
    # Get the extension in lowercase
    ext = os.path.splitext(filename)[1].lower()

    # Get allowed extensions for this type
    allowed = ALLOWED_EXTENSIONS.get(expected_type, set())

    return ext in allowed


def get_file_category(filename: str) -> str | None:
    """
    Determine the category of a file based on its extension.

    Args:
        filename: Filename to categorize

    Returns:
        str | None: Category name ("image", "video", "audio") or None if unknown

    Example:
        >>> get_file_category("video.mp4")
        'video'
        >>> get_file_category("song.mp3")
        'audio'
        >>> get_file_category("unknown.xyz")
        None
    """
    ext = os.path.splitext(filename)[1].lower()

    for category, extensions in ALLOWED_EXTENSIONS.items():
        if ext in extensions:
            return category

    return None


def ensure_project_directories(project_id: str) -> dict[str, Path]:
    """
    Create all necessary directories for a project.

    Args:
        project_id: Valid UUID string for the project

    Returns:
        dict[str, Path]: Dictionary mapping category names to their paths

    Raises:
        ValueError: If project_id is invalid

    Example:
        >>> dirs = ensure_project_directories("550e8400-e29b-41d4-a716-446655440000")
        >>> dirs["media"]
        PosixPath('/data/uploads/550e8400-.../media')
    """
    # Validate project_id
    if not validate_project_id(project_id):
        raise ValueError("Invalid project ID: must be a valid UUID")

    storage_root = get_storage_root()
    base_path = storage_root / "uploads" / project_id

    directories = {}
    for category in VALID_CATEGORIES:
        dir_path = base_path / category
        _mkdir_world_writable(dir_path)
        directories[category] = dir_path

    # Also create derived and output directories
    derived_path = storage_root / "derived" / project_id
    _mkdir_world_writable(derived_path)
    directories["derived"] = derived_path

    output_path = storage_root / "outputs" / project_id
    _mkdir_world_writable(output_path)
    directories["outputs"] = output_path

    return directories


def get_project_path(project_id: str, subpath: str = "") -> Path:
    """
    Get a path within a project's storage area.

    Args:
        project_id: Valid UUID string for the project
        subpath: Optional subpath within the project directory

    Returns:
        Path: Resolved absolute path

    Raises:
        ValueError: If project_id is invalid or path traversal detected

    Example:
        >>> get_project_path("550e8400-...", "media/video.mp4")
        PosixPath('/data/uploads/550e8400-.../media/video.mp4')
    """
    # Validate project_id
    if not validate_project_id(project_id):
        raise ValueError("Invalid project ID: must be a valid UUID")

    storage_root = get_storage_root()
    base_path = storage_root / "uploads" / project_id

    if subpath:
        # Sanitize each component of the subpath
        components = Path(subpath).parts
        safe_components = [sanitize_filename(c) for c in components]
        path = base_path.joinpath(*safe_components)
    else:
        path = base_path

    # Verify path is within storage root
    resolved_path = path.resolve()
    resolved_root = storage_root.resolve()

    if not str(resolved_path).startswith(str(resolved_root) + os.sep):
        raise ValueError("Path traversal detected: path escapes storage root")

    return resolved_path
