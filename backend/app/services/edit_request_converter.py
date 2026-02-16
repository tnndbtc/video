"""
EditRequest to EDL converter for BeatStitch.

This module converts a validated EditRequest (EDL v1) schema into the internal
EDL format used by the renderer. It handles duration calculations, effect
presets, and transition settings.

Usage:
    converter = EditRequestToEDLConverter(db_session)
    edl = await converter.convert(edit_request, project_id)
"""

import hashlib
import json
import logging
from copy import deepcopy
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audio import AudioTrack
from app.models.media import MediaAsset
from app.schemas.edit_request import (
    DurationBeats,
    DurationMs,
    DurationNatural,
    EditRequest,
    TimelineSegment,
)

logger = logging.getLogger(__name__)


# Default image duration in milliseconds
DEFAULT_IMAGE_DURATION_MS = 4000

# Motion preset to Ken Burns effect mapping
EFFECT_PRESET_TO_KEN_BURNS = {
    "slow_zoom_in": {
        "start_zoom": 1.0,
        "end_zoom": 1.2,
        "pan_direction": "center_zoom_in",
    },
    "slow_zoom_out": {
        "start_zoom": 1.2,
        "end_zoom": 1.0,
        "pan_direction": "center_zoom_out",
    },
    "pan_left": {
        "start_zoom": 1.1,
        "end_zoom": 1.1,
        "pan_direction": "left_to_right",
    },
    "pan_right": {
        "start_zoom": 1.1,
        "end_zoom": 1.1,
        "pan_direction": "right_to_left",
    },
    "diagonal_push": {
        "start_zoom": 1.0,
        "end_zoom": 1.15,
        "pan_direction": "top_to_bottom",
    },
    "subtle_drift": {
        "start_zoom": 1.05,
        "end_zoom": 1.1,
        "pan_direction": "center_zoom_in",
    },
    "none": None,
}


class EditRequestToEDLConverter:
    """
    Converts EditRequest (EDL v1) to internal EDL format.

    This converter:
    - Fetches asset information from database
    - Calculates segment durations based on mode
    - Maps effect presets to Ken Burns parameters
    - Applies transition settings
    - Computes EDL hash for caching
    """

    def __init__(self, db: AsyncSession):
        """
        Initialize the converter.

        Args:
            db: AsyncSession for database queries
        """
        self.db = db
        self._media_cache: Dict[str, MediaAsset] = {}
        self._audio_cache: Dict[str, AudioTrack] = {}

    async def convert(
        self,
        edit_request: EditRequest,
        project_id: str,
    ) -> dict:
        """
        Convert an EditRequest to internal EDL format.

        Args:
            edit_request: The validated EditRequest
            project_id: Project UUID

        Returns:
            EDL dictionary ready for the renderer

        Raises:
            ValueError: If required assets are missing
        """
        # Prefetch all assets
        await self._prefetch_assets(edit_request, project_id)

        # Get effective BPM
        effective_bpm = self._get_effective_bpm(edit_request)

        # Build segments
        segments = []
        timeline_position = 0

        for idx, segment in enumerate(edit_request.timeline):
            edl_segment = self._build_segment(
                segment=segment,
                segment_idx=idx,
                timeline_position=timeline_position,
                effective_bpm=effective_bpm,
                defaults=edit_request.defaults,
            )
            segments.append(edl_segment)
            timeline_position = edl_segment["timeline_out_ms"]

        # Apply transition overlaps if needed
        transition_type = edit_request.defaults.transition.type
        transition_duration_ms = edit_request.defaults.transition.duration_ms

        if transition_type != "cut" and len(segments) > 1:
            segments = self._apply_transition_overlaps(
                segments, transition_type, transition_duration_ms
            )

        # Compute total duration
        total_duration_ms = segments[-1]["timeline_out_ms"] if segments else 0

        # Handle audio duration and repeat mode
        if edit_request.audio and edit_request.audio.end_at_audio_end:
            audio_track = self._audio_cache.get(edit_request.audio.asset_id)
            if audio_track:
                audio_duration = audio_track.duration_ms
                audio_duration -= edit_request.audio.start_offset_ms
                audio_duration -= edit_request.audio.trim_end_ms

                if edit_request.repeat.mode in ("repeat_all", "repeat_last"):
                    # Expand segments to fill audio duration
                    segments = self._expand_for_audio(
                        segments=segments,
                        audio_duration_ms=audio_duration,
                        repeat_mode=edit_request.repeat.mode,
                    )
                    total_duration_ms = audio_duration

        # Compute EDL hash
        edl_hash = self._compute_hash(segments, edit_request)

        # Build final EDL
        edl = {
            "version": "1.0",
            "project_id": project_id,
            "generated_at": datetime.utcnow().isoformat() + "Z",
            "edl_hash": f"sha256:{edl_hash}",
            "transition_type": transition_type,
            "transition_duration_ms": transition_duration_ms,
            "ken_burns_enabled": True,  # Effects are per-segment now
            "total_duration_ms": total_duration_ms,
            "segment_count": len(segments),
            "segments": segments,
            # EditRequest v1 specific metadata
            "edit_request_version": edit_request.version,
            "effective_bpm": effective_bpm,
        }

        return edl

    async def _prefetch_assets(
        self,
        edit_request: EditRequest,
        project_id: str,
    ) -> None:
        """Prefetch all referenced assets from database."""
        media_ids = {seg.asset_id for seg in edit_request.timeline}
        audio_ids = set()
        if edit_request.audio:
            audio_ids.add(edit_request.audio.asset_id)

        # Fetch media
        if media_ids:
            query = select(MediaAsset).where(
                MediaAsset.project_id == project_id,
                MediaAsset.id.in_(media_ids),
            )
            result = await self.db.execute(query)
            for asset in result.scalars():
                self._media_cache[asset.id] = asset

        # Fetch audio
        if audio_ids:
            query = select(AudioTrack).where(
                AudioTrack.project_id == project_id,
                AudioTrack.id.in_(audio_ids),
            )
            result = await self.db.execute(query)
            for asset in result.scalars():
                self._audio_cache[asset.id] = asset

    def _get_effective_bpm(self, edit_request: EditRequest) -> Optional[float]:
        """Get effective BPM from EditRequest or audio track."""
        if not edit_request.audio:
            return None

        if edit_request.audio.bpm:
            return edit_request.audio.bpm

        audio_track = self._audio_cache.get(edit_request.audio.asset_id)
        if audio_track and audio_track.bpm:
            return audio_track.bpm

        return None

    def _build_segment(
        self,
        segment: TimelineSegment,
        segment_idx: int,
        timeline_position: int,
        effective_bpm: Optional[float],
        defaults,
    ) -> dict:
        """Build a single EDL segment from TimelineSegment."""
        asset = self._media_cache.get(segment.asset_id)
        if not asset:
            raise ValueError(f"Asset not found: {segment.asset_id}")

        # Calculate duration
        duration_ms = self._calculate_duration(
            segment=segment,
            asset=asset,
            effective_bpm=effective_bpm,
            defaults=defaults,
        )

        # Calculate source timing
        source_in_ms = 0
        source_out_ms = duration_ms

        if segment.source and segment.type == "video":
            source_in_ms = segment.source.in_ms or 0
            if segment.source.out_ms:
                source_out_ms = segment.source.out_ms - source_in_ms
            elif asset.duration_ms:
                source_out_ms = min(duration_ms, asset.duration_ms - source_in_ms)

        # Build effects
        ken_burns = None
        effects = None

        effect_preset = segment.effect or defaults.effect
        if effect_preset and effect_preset != "none" and segment.type == "image":
            ken_burns = EFFECT_PRESET_TO_KEN_BURNS.get(effect_preset)
            if ken_burns:
                ken_burns = deepcopy(ken_burns)
                effects = {
                    "motion_preset": effect_preset,
                    "motion_strength": 1.0,
                    "beat_sync_mode": "none",
                    "beat_sync_n": 4,
                }

        # Build transition
        transition_in = None
        if segment.transition_in:
            transition_in = {
                "type": segment.transition_in.type,
                "duration_ms": segment.transition_in.duration_ms,
            }

        return {
            "segment_index": segment_idx,
            "media_asset_id": segment.asset_id,
            "media_type": segment.type,
            "timeline_in_ms": timeline_position,
            "timeline_out_ms": timeline_position + duration_ms,
            "render_duration_ms": duration_ms,
            "source_in_ms": source_in_ms,
            "source_out_ms": source_out_ms,
            "ken_burns": ken_burns,
            "effects": effects,
            "transition_in": transition_in,
            "transition_out": None,
        }

    def _calculate_duration(
        self,
        segment: TimelineSegment,
        asset: MediaAsset,
        effective_bpm: Optional[float],
        defaults,
    ) -> int:
        """Calculate segment duration based on mode."""
        duration = segment.duration

        # Use defaults if no explicit duration
        if duration is None:
            if effective_bpm:
                beats = defaults.beats_per_cut
                return int(beats * (60000 / effective_bpm))
            elif segment.type == "video" and asset.duration_ms:
                return asset.duration_ms
            else:
                return DEFAULT_IMAGE_DURATION_MS

        # Handle explicit duration modes
        if isinstance(duration, DurationBeats):
            if not effective_bpm:
                raise ValueError("BPM required for beats-based duration")
            return int(duration.count * (60000 / effective_bpm))

        elif isinstance(duration, DurationMs):
            return duration.value

        elif isinstance(duration, DurationNatural):
            if segment.type == "video":
                if segment.source and segment.source.out_ms:
                    in_ms = segment.source.in_ms or 0
                    return segment.source.out_ms - in_ms
                elif asset.duration_ms:
                    return asset.duration_ms
                else:
                    return DEFAULT_IMAGE_DURATION_MS
            else:
                return DEFAULT_IMAGE_DURATION_MS

        return DEFAULT_IMAGE_DURATION_MS

    def _apply_transition_overlaps(
        self,
        segments: List[dict],
        transition_type: str,
        transition_duration_ms: int,
    ) -> List[dict]:
        """Apply transition overlap adjustments."""
        if len(segments) <= 1:
            return segments

        segments = deepcopy(segments)
        overlap_ms = transition_duration_ms

        for i in range(len(segments)):
            effective_overlap = min(overlap_ms, segments[i]["render_duration_ms"] // 2)
            effective_transition = {
                "type": transition_type,
                "duration_ms": effective_overlap,
            }

            # First segment has no transition_in
            if i == 0:
                segments[i]["transition_in"] = None
            else:
                if not segments[i].get("transition_in"):
                    segments[i]["transition_in"] = deepcopy(effective_transition)
                segments[i]["timeline_in_ms"] -= effective_overlap

            # Last segment has no transition_out
            if i < len(segments) - 1:
                segments[i]["transition_out"] = deepcopy(effective_transition)

            # Recalculate render_duration
            segments[i]["render_duration_ms"] = (
                segments[i]["timeline_out_ms"] - segments[i]["timeline_in_ms"]
            )

        return segments

    def _expand_for_audio(
        self,
        segments: List[dict],
        audio_duration_ms: int,
        repeat_mode: str,
    ) -> List[dict]:
        """Expand segments to fill audio duration."""
        if not segments:
            return segments

        total_duration = segments[-1]["timeline_out_ms"]
        if total_duration >= audio_duration_ms:
            # Already long enough, trim to audio
            return self._trim_to_duration(segments, audio_duration_ms)

        expanded = deepcopy(segments)
        current_position = total_duration
        next_segment_idx = len(segments)

        while current_position < audio_duration_ms:
            if repeat_mode == "repeat_all":
                # Loop through all segments
                for seg in segments:
                    if current_position >= audio_duration_ms:
                        break

                    duration = seg["render_duration_ms"]
                    remaining = audio_duration_ms - current_position
                    actual_duration = min(duration, remaining)

                    new_seg = deepcopy(seg)
                    new_seg["segment_index"] = next_segment_idx
                    new_seg["timeline_in_ms"] = current_position
                    new_seg["timeline_out_ms"] = current_position + actual_duration
                    new_seg["render_duration_ms"] = actual_duration
                    expanded.append(new_seg)

                    current_position += actual_duration
                    next_segment_idx += 1

            elif repeat_mode == "repeat_last":
                # Repeat only the last segment
                last_seg = segments[-1]
                remaining = audio_duration_ms - current_position

                new_seg = deepcopy(last_seg)
                new_seg["segment_index"] = next_segment_idx
                new_seg["timeline_in_ms"] = current_position
                new_seg["timeline_out_ms"] = audio_duration_ms
                new_seg["render_duration_ms"] = remaining
                expanded.append(new_seg)

                current_position = audio_duration_ms
                next_segment_idx += 1

        return expanded

    def _trim_to_duration(
        self,
        segments: List[dict],
        target_duration_ms: int,
    ) -> List[dict]:
        """Trim segments to target duration."""
        result = []
        for seg in segments:
            if seg["timeline_in_ms"] >= target_duration_ms:
                break

            new_seg = deepcopy(seg)
            if seg["timeline_out_ms"] > target_duration_ms:
                new_seg["timeline_out_ms"] = target_duration_ms
                new_seg["render_duration_ms"] = target_duration_ms - seg["timeline_in_ms"]

            result.append(new_seg)

        return result

    def _compute_hash(self, segments: List[dict], edit_request: EditRequest) -> str:
        """Compute SHA-256 hash of EDL content."""
        payload = {
            "segments": [
                {
                    "asset_id": s["media_asset_id"],
                    "duration": s["render_duration_ms"],
                    "effects": s.get("effects"),
                }
                for s in segments
            ],
            "audio_asset_id": edit_request.audio.asset_id if edit_request.audio else None,
            "transition_type": edit_request.defaults.transition.type,
            "repeat_mode": edit_request.repeat.mode,
        }
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode()).hexdigest()
