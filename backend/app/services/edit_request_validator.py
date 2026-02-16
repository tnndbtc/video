"""
EditRequest validation service for BeatStitch.

This service validates EditRequest objects against the database and business rules,
checking for asset existence, type matching, BPM availability, and other constraints.

Usage:
    validator = EditRequestValidator(db_session)
    result = await validator.validate(edit_request, project_id)

    if result.valid:
        # Proceed with processing
        computed_info = result.computed
    else:
        # Handle errors
        for error in result.errors:
            print(f"{error.code}: {error.message}")
"""

import hashlib
import json
import logging
from typing import Dict, List, Optional, Set

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audio import AudioTrack
from app.models.media import MediaAsset
from app.schemas.edit_request import (
    ComputedInfo,
    DurationBeats,
    DurationMs,
    DurationNatural,
    EditRequest,
    EditRequestValidationResult,
    TimelineSegment,
    ValidationErrorDetail,
)

logger = logging.getLogger(__name__)


# Default image duration in milliseconds
DEFAULT_IMAGE_DURATION_MS = 4000


class EditRequestValidator:
    """
    Validates EditRequest objects against database records and business rules.

    This validator performs:
    - Asset existence checks
    - Asset type matching (image vs video)
    - BPM availability for beat-based durations
    - Duration range validation
    - Source trim validation for videos
    - Transition duration warnings
    """

    def __init__(self, db: AsyncSession):
        """
        Initialize the validator with a database session.

        Args:
            db: AsyncSession for database queries
        """
        self.db = db
        self._media_cache: Dict[str, MediaAsset] = {}
        self._audio_cache: Dict[str, AudioTrack] = {}

    async def validate(
        self,
        edit_request: EditRequest,
        project_id: str,
    ) -> EditRequestValidationResult:
        """
        Validate an EditRequest against the database and business rules.

        Args:
            edit_request: The EditRequest to validate
            project_id: The project UUID for asset lookups

        Returns:
            EditRequestValidationResult with valid status, errors, warnings, and computed info
        """
        errors: List[ValidationErrorDetail] = []
        warnings: List[ValidationErrorDetail] = []

        # 1. Fetch all required assets from database
        await self._prefetch_assets(edit_request, project_id)

        # 2. Determine effective BPM
        effective_bpm = await self._get_effective_bpm(edit_request, project_id, errors)

        # 3. Validate audio settings if present
        if edit_request.audio:
            await self._validate_audio(edit_request, project_id, errors, warnings)

        # 4. Validate timeline segments
        segment_durations_ms: List[int] = []
        for idx, segment in enumerate(edit_request.timeline):
            duration_ms = await self._validate_segment(
                segment=segment,
                segment_idx=idx,
                project_id=project_id,
                effective_bpm=effective_bpm,
                defaults=edit_request.defaults,
                errors=errors,
                warnings=warnings,
            )
            if duration_ms is not None:
                segment_durations_ms.append(duration_ms)

        # 5. Check for timeline vs audio alignment warnings
        await self._check_timeline_audio_alignment(
            edit_request=edit_request,
            project_id=project_id,
            segment_durations_ms=segment_durations_ms,
            warnings=warnings,
        )

        # 6. Build computed info if no errors
        computed: Optional[ComputedInfo] = None
        if not errors:
            computed = await self._compute_info(
                edit_request=edit_request,
                project_id=project_id,
                effective_bpm=effective_bpm,
                segment_durations_ms=segment_durations_ms,
            )

        return EditRequestValidationResult(
            valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
            computed=computed,
        )

    async def compute_edl_hash(self, edit_request: EditRequest) -> str:
        """
        Compute a SHA-256 hash of the EditRequest for cache validation.

        Args:
            edit_request: The EditRequest to hash

        Returns:
            SHA-256 hex digest of the normalized JSON
        """
        # Serialize to JSON with sorted keys for deterministic hashing
        json_str = edit_request.model_dump_json(exclude_none=True)
        return hashlib.sha256(json_str.encode()).hexdigest()

    # =========================================================================
    # Private Helper Methods
    # =========================================================================

    async def _prefetch_assets(
        self,
        edit_request: EditRequest,
        project_id: str,
    ) -> None:
        """Prefetch all referenced assets from the database."""
        # Collect all asset IDs
        media_ids: Set[str] = set()
        audio_ids: Set[str] = set()

        for segment in edit_request.timeline:
            media_ids.add(segment.asset_id)

        if edit_request.audio:
            audio_ids.add(edit_request.audio.asset_id)

        # Fetch media assets
        if media_ids:
            query = select(MediaAsset).where(
                MediaAsset.project_id == project_id,
                MediaAsset.id.in_(media_ids),
            )
            result = await self.db.execute(query)
            for asset in result.scalars():
                self._media_cache[asset.id] = asset

        # Fetch audio assets
        if audio_ids:
            query = select(AudioTrack).where(
                AudioTrack.project_id == project_id,
                AudioTrack.id.in_(audio_ids),
            )
            result = await self.db.execute(query)
            for asset in result.scalars():
                self._audio_cache[asset.id] = asset

    async def _get_effective_bpm(
        self,
        edit_request: EditRequest,
        project_id: str,
        errors: List[ValidationErrorDetail],
    ) -> Optional[float]:
        """
        Determine the effective BPM for beat-based calculations.

        Priority:
        1. audio.bpm override
        2. Analyzed BPM from audio track
        3. None (beats mode not available)
        """
        if not edit_request.audio:
            return None

        # Check for explicit BPM override
        if edit_request.audio.bpm:
            return edit_request.audio.bpm

        # Look up audio track from cache
        audio_track = self._audio_cache.get(edit_request.audio.asset_id)
        if audio_track and audio_track.bpm:
            return audio_track.bpm

        # BPM not available - check if any segment needs it
        needs_bpm = False
        for segment in edit_request.timeline:
            if segment.duration and isinstance(segment.duration, DurationBeats):
                needs_bpm = True
                break
            if segment.duration is None:
                # Uses default beats_per_cut
                needs_bpm = True
                break

        if needs_bpm:
            errors.append(
                ValidationErrorDetail(
                    code="bpm_required",
                    message="Audio settings required for beats-based duration. Set audio.bpm or wait for analysis.",
                    path="audio.bpm",
                )
            )

        return None

    async def _validate_audio(
        self,
        edit_request: EditRequest,
        project_id: str,
        errors: List[ValidationErrorDetail],
        warnings: List[ValidationErrorDetail],
    ) -> None:
        """Validate audio settings."""
        audio = edit_request.audio
        if not audio:
            return

        # Check if audio asset exists
        audio_track = self._audio_cache.get(audio.asset_id)
        if not audio_track:
            errors.append(
                ValidationErrorDetail(
                    code="asset_not_found",
                    message=f"Audio asset '{audio.asset_id}' not found",
                    path="audio.asset_id",
                    asset_id=audio.asset_id,
                )
            )
            return

        # Check if audio is analyzed (if no BPM override provided)
        if not audio.bpm and audio_track.analysis_status != "complete":
            if audio_track.analysis_status == "analyzing":
                warnings.append(
                    ValidationErrorDetail(
                        code="audio_analyzing",
                        message="Audio analysis in progress. BPM may change.",
                        path="audio.asset_id",
                        asset_id=audio.asset_id,
                    )
                )
            elif audio_track.analysis_status == "failed":
                errors.append(
                    ValidationErrorDetail(
                        code="audio_analysis_failed",
                        message=f"Audio analysis failed: {audio_track.analysis_error or 'Unknown error'}",
                        path="audio.asset_id",
                        asset_id=audio.asset_id,
                    )
                )

    async def _validate_segment(
        self,
        segment: TimelineSegment,
        segment_idx: int,
        project_id: str,
        effective_bpm: Optional[float],
        defaults,
        errors: List[ValidationErrorDetail],
        warnings: List[ValidationErrorDetail],
    ) -> Optional[int]:
        """
        Validate a timeline segment and compute its duration.

        Returns:
            Duration in milliseconds, or None if validation failed
        """
        path_prefix = f"timeline[{segment_idx}]"

        # Check if asset exists
        asset = self._media_cache.get(segment.asset_id)
        if not asset:
            errors.append(
                ValidationErrorDetail(
                    code="asset_not_found",
                    message=f"Asset '{segment.asset_id}' not found",
                    path=f"{path_prefix}.asset_id",
                    asset_id=segment.asset_id,
                )
            )
            return None

        # Check asset type matches
        if asset.media_type != segment.type:
            errors.append(
                ValidationErrorDetail(
                    code="asset_type_mismatch",
                    message=f"Asset '{segment.asset_id}' is {asset.media_type}, not {segment.type}",
                    path=f"{path_prefix}.type",
                    asset_id=segment.asset_id,
                )
            )
            return None

        # Validate source trim for videos
        if segment.source:
            if segment.type != "video":
                warnings.append(
                    ValidationErrorDetail(
                        code="source_trim_ignored",
                        message="Source trim settings are ignored for images",
                        path=f"{path_prefix}.source",
                        asset_id=segment.asset_id,
                    )
                )
            else:
                await self._validate_source_trim(
                    segment=segment,
                    asset=asset,
                    path_prefix=path_prefix,
                    errors=errors,
                )

        # Calculate duration
        duration_ms = self._calculate_segment_duration(
            segment=segment,
            asset=asset,
            effective_bpm=effective_bpm,
            defaults=defaults,
            errors=errors,
            path_prefix=path_prefix,
        )

        # Validate transition duration vs segment duration
        if duration_ms and segment.transition_in:
            transition_duration = segment.transition_in.duration_ms
            if transition_duration > duration_ms * 0.5:
                warnings.append(
                    ValidationErrorDetail(
                        code="transition_too_long",
                        message=f"Transition duration ({transition_duration}ms) exceeds 50% of segment duration ({duration_ms}ms)",
                        path=f"{path_prefix}.transition_in.duration_ms",
                        asset_id=segment.asset_id,
                    )
                )

        return duration_ms

    async def _validate_source_trim(
        self,
        segment: TimelineSegment,
        asset: MediaAsset,
        path_prefix: str,
        errors: List[ValidationErrorDetail],
    ) -> None:
        """Validate video source trim settings."""
        source = segment.source
        if not source:
            return

        video_duration = asset.duration_ms
        if video_duration is None:
            # Can't validate without duration
            return

        # Validate in_ms
        if source.in_ms and source.in_ms >= video_duration:
            errors.append(
                ValidationErrorDetail(
                    code="source_trim_invalid",
                    message=f"source.in_ms ({source.in_ms}ms) exceeds video duration ({video_duration}ms)",
                    path=f"{path_prefix}.source.in_ms",
                    asset_id=segment.asset_id,
                )
            )
            return

        # Validate out_ms > in_ms
        if source.out_ms is not None:
            if source.out_ms <= (source.in_ms or 0):
                errors.append(
                    ValidationErrorDetail(
                        code="source_trim_invalid",
                        message="source.out_ms must be greater than source.in_ms",
                        path=f"{path_prefix}.source.out_ms",
                        asset_id=segment.asset_id,
                    )
                )
            elif source.out_ms > video_duration:
                errors.append(
                    ValidationErrorDetail(
                        code="source_trim_invalid",
                        message=f"source.out_ms ({source.out_ms}ms) exceeds video duration ({video_duration}ms)",
                        path=f"{path_prefix}.source.out_ms",
                        asset_id=segment.asset_id,
                    )
                )

    def _calculate_segment_duration(
        self,
        segment: TimelineSegment,
        asset: MediaAsset,
        effective_bpm: Optional[float],
        defaults,
        errors: List[ValidationErrorDetail],
        path_prefix: str,
    ) -> Optional[int]:
        """Calculate segment duration in milliseconds."""
        duration = segment.duration

        # Use defaults if no explicit duration
        if duration is None:
            if effective_bpm:
                # Use default beats_per_cut
                beats = defaults.beats_per_cut
                return int(beats * (60000 / effective_bpm))
            elif segment.type == "video" and asset.duration_ms:
                # For videos without BPM, use natural duration
                return asset.duration_ms
            else:
                # For images without BPM, use default image duration
                return DEFAULT_IMAGE_DURATION_MS

        # Handle explicit duration modes
        if isinstance(duration, DurationBeats):
            if not effective_bpm:
                errors.append(
                    ValidationErrorDetail(
                        code="bpm_required",
                        message="BPM required for beats-based duration",
                        path=f"{path_prefix}.duration",
                        asset_id=segment.asset_id,
                    )
                )
                return None
            return int(duration.count * (60000 / effective_bpm))

        elif isinstance(duration, DurationMs):
            return duration.value

        elif isinstance(duration, DurationNatural):
            if segment.type == "video":
                if segment.source and segment.source.out_ms:
                    # Use trimmed duration
                    in_ms = segment.source.in_ms or 0
                    return segment.source.out_ms - in_ms
                elif asset.duration_ms:
                    return asset.duration_ms
                else:
                    errors.append(
                        ValidationErrorDetail(
                            code="duration_unknown",
                            message="Video duration not available",
                            path=f"{path_prefix}.duration",
                            asset_id=segment.asset_id,
                        )
                    )
                    return None
            else:
                # Images use default duration
                return DEFAULT_IMAGE_DURATION_MS

        return None

    async def _check_timeline_audio_alignment(
        self,
        edit_request: EditRequest,
        project_id: str,
        segment_durations_ms: List[int],
        warnings: List[ValidationErrorDetail],
    ) -> None:
        """Check if timeline duration aligns with audio duration."""
        if not edit_request.audio:
            return

        audio_track = self._audio_cache.get(edit_request.audio.asset_id)
        if not audio_track:
            return

        # Calculate effective audio duration
        audio_duration = audio_track.duration_ms
        audio_duration -= edit_request.audio.start_offset_ms
        audio_duration -= edit_request.audio.trim_end_ms

        if audio_duration <= 0:
            warnings.append(
                ValidationErrorDetail(
                    code="audio_too_short",
                    message="Audio trimming results in zero or negative duration",
                    path="audio",
                )
            )
            return

        # Calculate total timeline duration
        total_timeline_ms = sum(segment_durations_ms)

        if edit_request.repeat.mode == "stop":
            if total_timeline_ms < audio_duration:
                warnings.append(
                    ValidationErrorDetail(
                        code="timeline_shorter_than_audio",
                        message=f"Timeline ({total_timeline_ms}ms) is shorter than audio ({audio_duration}ms) with mode=stop",
                        path="repeat.mode",
                    )
                )

    async def _compute_info(
        self,
        edit_request: EditRequest,
        project_id: str,
        effective_bpm: Optional[float],
        segment_durations_ms: List[int],
    ) -> ComputedInfo:
        """Compute metadata from a valid EditRequest."""
        total_timeline_ms = sum(segment_durations_ms)

        audio_duration_ms: Optional[int] = None
        loop_count: Optional[int] = None

        if edit_request.audio:
            audio_track = self._audio_cache.get(edit_request.audio.asset_id)
            if audio_track:
                # Calculate effective audio duration
                audio_duration_ms = audio_track.duration_ms
                audio_duration_ms -= edit_request.audio.start_offset_ms
                audio_duration_ms -= edit_request.audio.trim_end_ms

                # Calculate loop count if needed
                if edit_request.audio.end_at_audio_end and total_timeline_ms > 0:
                    if edit_request.repeat.mode in ("repeat_all", "repeat_last"):
                        loop_count = max(1, (audio_duration_ms + total_timeline_ms - 1) // total_timeline_ms)

        return ComputedInfo(
            total_duration_ms=total_timeline_ms,
            segment_count=len(edit_request.timeline),
            effective_bpm=effective_bpm,
            audio_duration_ms=audio_duration_ms,
            loop_count=loop_count,
        )
