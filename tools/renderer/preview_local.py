"""
Phase 0 Preview Renderer — profile: preview_local.

Inputs:  AssetManifest (§5.7) + RenderPlan (§5.8, profile=preview_local)
Outputs: output.mp4 + output.srt + render_output.json  (§5.9)

Design guarantees:
  1. Deterministic — same inputs produce bit-identical video output
     (requires identical ffmpeg version; see README.md §ffmpeg-version).
  2. Complete — missing visual asset slots are filled with placeholder PNGs;
     the render never aborts due to a missing asset.
  3. Local-only — zero external calls; ffmpeg is the only subprocess.
  4. Schema-validated — outputs a RenderOutput that round-trips through
     the Pydantic model.

Phase 0 scope:
  - Static images only (no Ken Burns / zoompan).
  - Cut transitions only (no crossfade).
  - Captions: sidecar .srt only (no burned-in subtitles).
  - Audio: silence (-an) or optional background music track.
  - No distributed queue; sequential single-process execution.
"""
from __future__ import annotations

import datetime
import hashlib
import json
import logging
import uuid
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

from schemas.asset_manifest import AssetManifest, Shot
from schemas.render_plan import RenderPlan
from schemas.render_output import Lineage, OutputHashes, Provenance, RenderOutput
from renderer.captions import write_srt
from renderer.ffmpeg_runner import FFmpegError, get_ffmpeg_version, run_ffmpeg
from renderer.placeholder import generate_placeholder

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

class PreviewRenderer:
    """
    Deterministic preview renderer for profile=preview_local.

    Usage::

        from renderer.preview_local import PreviewRenderer
        from schemas.asset_manifest import AssetManifest
        from schemas.render_plan import RenderPlan

        manifest = AssetManifest.model_validate_json(manifest_path.read_text())
        plan     = RenderPlan.model_validate_json(plan_path.read_text())
        result   = PreviewRenderer(manifest, plan, output_dir=Path("/tmp/out")).render()
        print(result.model_dump_json(indent=2))
    """

    def __init__(
        self,
        manifest: AssetManifest,
        plan: RenderPlan,
        output_dir: Path,
        request_id: Optional[str] = None,
    ) -> None:
        if plan.profile != "preview_local":
            raise ValueError(
                f"PreviewRenderer only supports profile=preview_local, "
                f"got: {plan.profile!r}"
            )
        if manifest.timing_lock_hash != plan.timing_lock_hash:
            raise ValueError(
                f"timing_lock_hash mismatch between AssetManifest "
                f"({manifest.timing_lock_hash!r}) and RenderPlan "
                f"({plan.timing_lock_hash!r}). "
                f"Ensure both were produced from the same ShotList."
            )

        self.manifest = manifest
        self.plan = plan
        self.output_dir = Path(output_dir)
        self.request_id = request_id or str(uuid.uuid4())
        self._placeholder_count = 0

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    def render(self) -> RenderOutput:
        """
        Execute the full render pipeline and return a RenderOutput.

        Writes to output_dir:
          output.mp4         — encoded video
          output.srt         — SRT captions (empty if no VO lines)
          render_output.json — serialised RenderOutput for the artifact registry
        """
        self.output_dir.mkdir(parents=True, exist_ok=True)
        placeholder_dir = self.output_dir / ".placeholders"
        placeholder_dir.mkdir(exist_ok=True)

        ffmpeg_version = get_ffmpeg_version()
        logger.info(
            "PreviewRenderer | project=%s | ffmpeg=%s | shots=%d",
            self.manifest.project_id,
            ffmpeg_version,
            len(self.manifest.shots),
        )

        # Lineage hashes: computed from the canonical JSON representation.
        manifest_hash = _sha256_text(self.manifest.model_dump_json())
        plan_hash = _sha256_text(self.plan.model_dump_json())

        # Step 1 — resolve or generate one visual input per shot.
        shot_inputs = self._resolve_shot_inputs(placeholder_dir)

        # Step 2 — build and execute the ffmpeg concat command.
        output_mp4 = self.output_dir / "output.mp4"
        self._run_concat(shot_inputs, output_mp4)

        # Step 3 — generate SRT captions.
        output_srt = self.output_dir / "output.srt"
        write_srt(self.manifest, output_srt)

        # Step 4 — compute content hashes.
        video_hash = _sha256_file(output_mp4)
        captions_hash = _sha256_text(output_srt.read_text(encoding="utf-8"))

        # Step 5 — assemble RenderOutput.
        result = RenderOutput(
            schema_version="1.0.0",
            output_id=str(uuid.uuid4()),
            request_id=self.request_id,
            render_plan_ref=self.plan.asset_manifest_ref,
            video_uri=f"file://{output_mp4.resolve()}",
            captions_uri=f"file://{output_srt.resolve()}",
            audio_stems_uri=None,
            hashes=OutputHashes(
                video_sha256=video_hash,
                captions_sha256=captions_hash,
            ),
            provenance=Provenance(
                render_profile=self.plan.profile,
                timing_lock_hash=self.plan.timing_lock_hash,
                rendered_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                ffmpeg_version=ffmpeg_version,
                placeholder_count=self._placeholder_count,
            ),
            lineage=Lineage(
                asset_manifest_hash=manifest_hash,
                render_plan_hash=plan_hash,
            ),
        )

        output_json = self.output_dir / "render_output.json"
        output_json.write_text(result.model_dump_json(indent=2), encoding="utf-8")
        logger.info(
            "Render complete → %s  (placeholders=%d)",
            output_mp4,
            self._placeholder_count,
        )
        return result

    # ------------------------------------------------------------------
    # Internal: asset resolution
    # ------------------------------------------------------------------

    def _resolve_shot_inputs(self, placeholder_dir: Path) -> list[Path]:
        """Return one resolved image Path per shot, in shot-index order."""
        w = self.plan.resolution.width
        h = self.plan.resolution.height
        return [
            self._get_shot_visual(shot, placeholder_dir, w, h)
            for shot in self.manifest.shots
        ]

    def _get_shot_visual(
        self,
        shot: Shot,
        placeholder_dir: Path,
        w: int,
        h: int,
    ) -> Path:
        """
        Return the best available visual Path for a shot.

        Priority:
          1. plan.asset_resolutions[asset_id] (asset resolver output)
          2. asset.asset_uri on the AssetManifest itself
        Backgrounds are preferred over characters / props (sorted by role).
        Falls back to a generated placeholder if no usable file is found.
        """
        candidates = sorted(
            shot.visual_assets,
            key=lambda a: (0 if a.role == "background" else 1),
        )
        for asset in candidates:
            uri = self.plan.asset_resolutions.get(asset.asset_id) or asset.asset_uri
            if not uri:
                continue
            path = _resolve_uri(uri)
            if path and path.exists():
                return path

        # No usable asset → synthesise placeholder.
        self._placeholder_count += 1
        logger.debug(
            "No visual asset found for shot %r — generating placeholder.", shot.shot_id
        )
        fb = self.plan.fallback
        font_path: Optional[str] = None
        if Path(fb.placeholder_font_path).exists():
            font_path = fb.placeholder_font_path

        return generate_placeholder(
            shot_id=shot.shot_id,
            width=w,
            height=h,
            color=fb.placeholder_color,
            font_path=font_path,
            font_size=fb.placeholder_font_size,
            cache_dir=placeholder_dir,
        )

    # ------------------------------------------------------------------
    # Internal: ffmpeg
    # ------------------------------------------------------------------

    def _run_concat(self, shot_inputs: list[Path], output_path: Path) -> None:
        """
        Build and execute a deterministic ffmpeg concat command.

        Each shot becomes one `-loop 1 -framerate N -t dur -i file` input.
        A filter_complex scales/pads each input to the target resolution then
        concatenates with `concat=n=N:v=1:a=0`.

        Determinism flags applied:
          -fflags +bitexact        suppress non-deterministic metadata writes
          -flags:v +bitexact       deterministic video encoder path
          -map_metadata -1         strip creation_time and encoder strings
          -movflags +faststart     consistent MP4 atom ordering
          (libx264 is deterministic for fixed crf/preset/pix_fmt/fps)
        """
        w = self.plan.resolution.width
        h = self.plan.resolution.height
        fps = self.plan.fps
        n = len(shot_inputs)

        cmd: list[str] = ["ffmpeg", "-y"]

        # --- Video inputs ---
        for shot, path in zip(self.manifest.shots, shot_inputs):
            dur_s = shot.duration_ms / 1000.0
            cmd += [
                "-loop", "1",
                "-framerate", str(fps),
                "-t", f"{dur_s:.6f}",
                "-i", str(path),
            ]

        # --- Optional music input (index = n) ---
        music_path = _resolve_music(self.manifest)
        if music_path is not None:
            cmd += ["-i", str(music_path)]

        # --- filter_complex: scale + pad each video input, then concat ---
        total_dur_s = sum(s.duration_ms for s in self.manifest.shots) / 1000.0
        filter_parts: list[str] = []
        for i in range(n):
            filter_parts.append(
                f"[{i}:v]"
                f"scale={w}:{h}:force_original_aspect_ratio=decrease,"
                f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:black,"
                f"setsar=1,"
                f"fps={fps}"
                f"[v{i}]"
            )
        concat_in = "".join(f"[v{i}]" for i in range(n))
        filter_parts.append(f"{concat_in}concat=n={n}:v=1:a=0[vout]")

        cmd += ["-filter_complex", ";".join(filter_parts)]
        cmd += ["-map", "[vout]"]

        # --- Audio ---
        if music_path is not None:
            cmd += [
                "-map", f"{n}:a",
                "-t", f"{total_dur_s:.6f}",
                "-c:a", "aac",
                "-flags:a", "+bitexact",
            ]
        else:
            cmd += ["-an"]

        # --- Encoding + determinism ---
        cmd += [
            "-c:v", "libx264",
            "-crf", "28",
            "-preset", "medium",
            "-pix_fmt", "yuv420p",
            "-r", str(fps),
            # Determinism: prevent ffmpeg from embedding non-reproducible metadata.
            "-fflags", "+bitexact",
            "-flags:v", "+bitexact",
            "-map_metadata", "-1",
            "-movflags", "+faststart",
            str(output_path),
        ]

        run_ffmpeg(cmd)


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------

def _resolve_uri(uri: str) -> Optional[Path]:
    """Resolve a file:// URI or plain filesystem path to a Path object."""
    if not uri:
        return None
    if uri.startswith("file://"):
        return Path(urlparse(uri).path)
    return Path(uri)


def _resolve_music(manifest: AssetManifest) -> Optional[Path]:
    """Return the resolved music track Path, or None if absent / unreadable."""
    if not manifest.music_uri:
        return None
    path = _resolve_uri(manifest.music_uri)
    if path and path.exists():
        return path
    logger.warning(
        "music_uri %r not found — rendering without background music.",
        manifest.music_uri,
    )
    return None


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65_536), b""):
            h.update(chunk)
    return h.hexdigest()


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
