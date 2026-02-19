"""
RenderOutput — canonical schema §5.9 of master plan.

Produced by the renderer:
  - final video path/URI
  - captions path/URI
  - audio stems path/URI (optional; null in Phase 0)
  - hashes, provenance links, lineage references

All URI fields use file:// scheme for local Phase 0 artifacts.
hashes contains SHA-256 content hashes of the output files,
enabling artifact registry lookups and re-render deduplication (§14).
"""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class OutputHashes(BaseModel):
    """Content hashes for output artifacts (§5.9: hashes)."""
    video_sha256: str
    captions_sha256: Optional[str] = None
    audio_stems_sha256: Optional[str] = None   # always null in Phase 0


class Provenance(BaseModel):
    """
    Render provenance metadata (§5.9: provenance links).
    rendered_at: ISO 8601 wall-clock timestamp (not used for determinism checks;
    the timing_lock_hash + lineage hashes are the reproducibility anchors).
    """
    render_profile: str
    timing_lock_hash: str
    rendered_at: str            # ISO 8601
    ffmpeg_version: str         # e.g. "6.1.1" — must match pinned version for golden tests
    placeholder_count: int = 0  # number of shots that used generated placeholders


class Lineage(BaseModel):
    """
    Input artifact hashes for full reproducibility (§5.9: lineage references, §14).
    Enables the artifact registry to reconstruct any render from stored inputs.
    """
    asset_manifest_hash: str    # SHA-256 of the input AssetManifest JSON
    render_plan_hash: str       # SHA-256 of the input RenderPlan JSON


class RenderOutput(BaseModel):
    """
    RenderOutput — result of one renderer invocation.
    Canonical schema §5.9. Written to render_output.json alongside the .mp4 and .srt.
    """
    schema_version: str = "1.0.0"
    output_id: str
    request_id: str
    render_plan_ref: str
    video_uri: str                       # file:// URI of output .mp4
    captions_uri: Optional[str] = None  # file:// URI of .srt; null if no VO lines
    audio_stems_uri: Optional[str] = None  # null in Phase 0
    hashes: OutputHashes
    provenance: Provenance
    lineage: Lineage
