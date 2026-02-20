"""
Integration tests for scripts/video.py verify.
Requires ffmpeg + Pillow. Marked @pytest.mark.slow.
"""
from __future__ import annotations

import importlib
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

VIDEO_SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "video.py"


@pytest.mark.slow
class TestVideoVerifyCli:

    @pytest.fixture(autouse=True)
    def _need_ffmpeg(self, require_ffmpeg): ...

    @pytest.fixture(scope="class")
    def verify_run(self):
        try:
            from PIL import Image  # noqa: F401
        except ImportError:
            pytest.skip("Pillow not installed")
        return subprocess.run(
            [sys.executable, str(VIDEO_SCRIPT), "verify"],
            capture_output=True, text=True,
        )

    def test_exit_code_zero(self, verify_run):
        assert verify_run.returncode == 0, (
            f"video verify failed:\nSTDOUT: {verify_run.stdout}\n"
            f"STDERR: {verify_run.stderr}"
        )

    def test_ok_stdout(self, verify_run):
        assert verify_run.stdout.strip() == "OK: video verified"

    def test_stderr_empty_on_success(self, verify_run):
        assert verify_run.stderr == ""

    def test_unknown_command_exits_nonzero(self):
        result = subprocess.run(
            [sys.executable, str(VIDEO_SCRIPT), "bogus"],
            capture_output=True, text=True,
        )
        assert result.returncode != 0


@pytest.mark.slow
class TestVideoVerifyDeterminismFailure:
    """Verify that a corrupted frame hash causes cmd_verify() to fail."""

    @pytest.fixture(autouse=True)
    def _need_ffmpeg(self, require_ffmpeg): ...

    def test_frame_hash_corruption_exits_nonzero(self, monkeypatch, capsys):
        try:
            from PIL import Image  # noqa: F401
        except ImportError:
            pytest.skip("Pillow not installed")

        # Load video module so its globals (e.g. _fingerprint_bytes) are fresh
        spec = importlib.util.spec_from_file_location("video_cli", VIDEO_SCRIPT)
        video_mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(video_mod)

        from renderer.preview_local import PreviewRenderer

        original_verify = PreviewRenderer.verify
        call_count = 0

        def patched_verify(self):
            nonlocal call_count
            result = original_verify(self)
            call_count += 1
            if call_count >= 2:
                fp_path = self.output_dir / "render_fingerprint.json"
                data = json.loads(fp_path.read_bytes())
                if data.get("frame_hashes"):
                    data["frame_hashes"][0] = "CORRUPTED"
                    fp_path.write_text(
                        json.dumps(data, indent=2), encoding="utf-8"
                    )
            return result

        monkeypatch.setattr(PreviewRenderer, "verify", patched_verify)

        exit_code = video_mod.cmd_verify()
        captured = capsys.readouterr()

        assert exit_code == 1
        assert captured.out.strip() == "ERROR: video verification failed"
        assert "fingerprint JSON bytes differ" in captured.err


@pytest.mark.slow
class TestVideoVerifyProfile:
    """Test --profile flag for both preview and high profiles."""

    @pytest.fixture(autouse=True)
    def _need_ffmpeg(self, require_ffmpeg): ...

    def test_profile_preview_explicit_exits_zero(self):
        try:
            from PIL import Image  # noqa: F401
        except ImportError:
            pytest.skip("Pillow not installed")
        result = subprocess.run(
            [sys.executable, str(VIDEO_SCRIPT), "verify", "--profile", "preview"],
            capture_output=True, text=True,
        )
        assert result.returncode == 0, result.stderr
        assert result.stdout.strip() == "OK: video verified"

    def test_profile_high_exits_zero(self):
        try:
            from PIL import Image  # noqa: F401
        except ImportError:
            pytest.skip("Pillow not installed")
        result = subprocess.run(
            [sys.executable, str(VIDEO_SCRIPT), "verify", "--profile", "high"],
            capture_output=True, text=True,
        )
        assert result.returncode == 0, result.stderr
        assert result.stdout.strip() == "OK: video verified"

    def test_preview_and_high_fingerprints_differ(self, tmp_path):
        """Preview and high profiles must produce different fingerprint bytes."""
        try:
            from PIL import Image  # noqa: F401
        except ImportError:
            pytest.skip("Pillow not installed")
        import tempfile
        spec = importlib.util.spec_from_file_location("video_cli", VIDEO_SCRIPT)
        video_mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(video_mod)
        with (tempfile.TemporaryDirectory() as dp,
              tempfile.TemporaryDirectory() as dh):
            bp = video_mod._fingerprint_bytes(Path(dp), profile="preview")
            bh = video_mod._fingerprint_bytes(Path(dh), profile="high")
        assert bp != bh
