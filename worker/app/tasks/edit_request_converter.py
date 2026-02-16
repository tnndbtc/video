"""
EditRequest to EDL converter for BeatStitch Worker.

Synchronous version of the converter for use in RQ worker tasks.
Converts a validated EditRequest (EDL v1) schema into the internal
EDL format used by the renderer.

Usage:
    converter = EditRequestToEDLConverter(db_session)
    edl = converter.convert(edit_request_dict, project_id)
"""

import hashlib
import json
import logging
from copy import deepcopy
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

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
    Converts EditRequest (EDL v1) dict to internal EDL format.

    Synchronous version for RQ worker tasks.
    """

    def __init__(self, db: Session, media_asset_class, audio_track_class):
        """
        Initialize the converter.

        Args:
            db: SQLAlchemy Session for database queries
            media_asset_class: MediaAsset model class
            audio_track_class: AudioTrack model class
        """
        self.db = db
        self.MediaAsset = media_asset_class
        self.AudioTrack = audio_track_class
        self._media_cache: Dict[str, Any] = {}
        self._audio_cache: Dict[str, Any] = {}

    def convert(
        self,
        edit_request: dict,
        project_id: str,
    ) -> dict:
        """
        Convert an EditRequest dict to internal EDL format.

        Args:
            edit_request: The EditRequest dict (already parsed from JSON)
            project_id: Project UUID

        Returns:
            EDL dictionary ready for the renderer

        Raises:
            ValueError: If required assets are missing
        """
        # Prefetch all assets
        self._prefetch_assets(edit_request, project_id)

        # Get defaults
        defaults = edit_request.get("defaults", {})
        beats_per_cut = defaults.get("beats_per_cut", 8)
        default_transition = defaults.get("transition", {"type": "cut", "duration_ms": 0})
        default_effect = defaults.get("effect")

        # Get effective BPM
        effective_bpm = self._get_effective_bpm(edit_request)

        # Build segments
        segments = []
        timeline_position = 0

        for idx, segment in enumerate(edit_request["timeline"]):
            edl_segment = self._build_segment(
                segment=segment,
                segment_idx=idx,
                timeline_position=timeline_position,
                effective_bpm=effective_bpm,
                beats_per_cut=beats_per_cut,
                default_effect=default_effect,
            )
            segments.append(edl_segment)
            timeline_position = edl_segment["timeline_out_ms"]

        # Apply transition overlaps if needed
        transition_type = default_transition.get("type", "cut")
        transition_duration_ms = default_transition.get("duration_ms", 0)

        if transition_type != "cut" and len(segments) > 1:
            segments = self._apply_transition_overlaps(
                segments, transition_type, transition_duration_ms
            )

        # Compute total duration
        total_duration_ms = segments[-1]["timeline_out_ms"] if segments else 0

        # Handle audio duration and repeat mode
        audio_settings = edit_request.get("audio")
        repeat_settings = edit_request.get("repeat", {"mode": "repeat_all"})

        if audio_settings and audio_settings.get("end_at_audio_end", True):
            audio_track = self._audio_cache.get(audio_settings.get("asset_id"))
            if audio_track:
                audio_duration = audio_track.duration_ms
                audio_duration -= audio_settings.get("start_offset_ms", 0)
                audio_duration -= audio_settings.get("trim_end_ms", 0)

                repeat_mode = repeat_settings.get("mode", "repeat_all")
                if repeat_mode in ("repeat_all", "repeat_last"):
                    segments = self._expand_for_audio(
                        segments=segments,
                        audio_duration_ms=audio_duration,
                        repeat_mode=repeat_mode,
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
            "ken_burns_enabled": True,
            "total_duration_ms": total_duration_ms,
            "segment_count": len(segments),
            "segments": segments,
            "edit_request_version": edit_request.get("version", "1.0"),
            "effective_bpm": effective_bpm,
        }

        return edl

    def _prefetch_assets(self, edit_request: dict, project_id: str) -> None:
        """Prefetch all referenced assets from database."""
        media_ids = {seg["asset_id"] for seg in edit_request["timeline"]}
        audio_ids = set()
        audio_settings = edit_request.get("audio")
        if audio_settings:
            audio_ids.add(audio_settings.get("asset_id"))

        # Fetch media
        if media_ids:
            assets = self.db.query(self.MediaAsset).filter(
                self.MediaAsset.project_id == project_id,
                self.MediaAsset.id.in_(media_ids),
            ).all()
            for asset in assets:
                self._media_cache[asset.id] = asset

        # Fetch audio
        if audio_ids:
            tracks = self.db.query(self.AudioTrack).filter(
                self.AudioTrack.project_id == project_id,
                self.AudioTrack.id.in_(audio_ids),
            ).all()
            for track in tracks:
                self._audio_cache[track.id] = track

    def _get_effective_bpm(self, edit_request: dict) -> Optional[float]:
        """Get effective BPM from EditRequest or audio track."""
        audio_settings = edit_request.get("audio")
        if not audio_settings:
            return None

        if audio_settings.get("bpm"):
            return float(audio_settings["bpm"])

        audio_track = self._audio_cache.get(audio_settings.get("asset_id"))
        if audio_track and audio_track.bpm:
            return float(audio_track.bpm)

        return None

    def _build_segment(
        self,
        segment: dict,
        segment_idx: int,
        timeline_position: int,
        effective_bpm: Optional[float],
        beats_per_cut: int,
        default_effect: Optional[str],
    ) -> dict:
        """Build a single EDL segment from timeline segment dict."""
        asset_id = segment["asset_id"]
        asset = self._media_cache.get(asset_id)
        if not asset:
            raise ValueError(f"Asset not found: {asset_id}")

        segment_type = segment["type"]

        # Calculate duration
        duration_ms = self._calculate_duration(
            segment=segment,
            asset=asset,
            effective_bpm=effective_bpm,
            beats_per_cut=beats_per_cut,
        )

        # Calculate source timing
        source_in_ms = 0
        source_out_ms = duration_ms

        source = segment.get("source")
        if source and segment_type == "video":
            source_in_ms = source.get("in_ms", 0)
            if source.get("out_ms"):
                source_out_ms = source["out_ms"] - source_in_ms
            elif asset.duration_ms:
                source_out_ms = min(duration_ms, asset.duration_ms - source_in_ms)

        # Build effects
        ken_burns = None
        effects = None

        effect_preset = segment.get("effect") or default_effect
        if effect_preset and effect_preset != "none" and segment_type == "image":
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
        trans = segment.get("transition_in")
        if trans:
            transition_in = {
                "type": trans.get("type", "cut"),
                "duration_ms": trans.get("duration_ms", 0),
            }

        return {
            "segment_index": segment_idx,
            "media_asset_id": asset_id,
            "media_type": segment_type,
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
        segment: dict,
        asset,
        effective_bpm: Optional[float],
        beats_per_cut: int,
    ) -> int:
        """Calculate segment duration based on mode."""
        duration = segment.get("duration")
        segment_type = segment["type"]

        # Use defaults if no explicit duration
        if duration is None:
            if effective_bpm:
                return int(beats_per_cut * (60000 / effective_bpm))
            elif segment_type == "video" and asset.duration_ms:
                return asset.duration_ms
            else:
                return DEFAULT_IMAGE_DURATION_MS

        mode = duration.get("mode")

        if mode == "beats":
            if not effective_bpm:
                raise ValueError("BPM required for beats-based duration")
            return int(duration["count"] * (60000 / effective_bpm))

        elif mode == "ms":
            return duration["value"]

        elif mode == "natural":
            if segment_type == "video":
                source = segment.get("source")
                if source and source.get("out_ms"):
                    in_ms = source.get("in_ms", 0)
                    return source["out_ms"] - in_ms
                elif asset.duration_ms:
                    return asset.duration_ms
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

            if i == 0:
                segments[i]["transition_in"] = None
            else:
                if not segments[i].get("transition_in"):
                    segments[i]["transition_in"] = deepcopy(effective_transition)
                segments[i]["timeline_in_ms"] -= effective_overlap

            if i < len(segments) - 1:
                segments[i]["transition_out"] = deepcopy(effective_transition)

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
            return self._trim_to_duration(segments, audio_duration_ms)

        expanded = deepcopy(segments)
        current_position = total_duration
        next_segment_idx = len(segments)

        while current_position < audio_duration_ms:
            if repeat_mode == "repeat_all":
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

    def _compute_hash(self, segments: List[dict], edit_request: dict) -> str:
        """Compute SHA-256 hash of EDL content."""
        audio_settings = edit_request.get("audio")
        defaults = edit_request.get("defaults", {})
        repeat_settings = edit_request.get("repeat", {})

        payload = {
            "segments": [
                {
                    "asset_id": s["media_asset_id"],
                    "duration": s["render_duration_ms"],
                    "effects": s.get("effects"),
                }
                for s in segments
            ],
            "audio_asset_id": audio_settings.get("asset_id") if audio_settings else None,
            "transition_type": defaults.get("transition", {}).get("type", "cut"),
            "repeat_mode": repeat_settings.get("mode", "repeat_all"),
        }
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode()).hexdigest()
