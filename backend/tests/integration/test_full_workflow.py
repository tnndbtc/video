"""
Integration tests for the complete video editing workflow.

Tests the full flow with mocked workers:
1. Create project
2. Upload media
3. Upload audio (mock beat analysis completion)
4. Generate timeline (mock worker completion)
5. Start render (mock worker completion)
6. Download render

Also tests timeline and render endpoints with various states.
"""

import json
import uuid
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from httpx import AsyncClient

from tests.conftest import create_test_beats_json, create_test_edl_json


class TestTimelineGeneration:
    """Tests for timeline generation endpoint."""

    @pytest.mark.asyncio
    async def test_generate_timeline_no_audio(
        self,
        async_client: AsyncClient,
        auth_headers: dict,
        test_project: dict,
        sample_image: bytes,
    ):
        """Test that timeline generation fails without audio."""
        # Upload media but no audio
        files = {"files": ("test.jpg", sample_image, "image/jpeg")}
        response = await async_client.post(
            f"/api/projects/{test_project['id']}/media",
            files=files,
            headers=auth_headers,
        )
        assert response.status_code == 201

        # Try to generate timeline
        response = await async_client.post(
            f"/api/projects/{test_project['id']}/timeline/generate",
            headers=auth_headers,
        )

        assert response.status_code == 400
        data = response.json()
        assert data["detail"]["error"] == "precondition_failed"
        assert data["detail"]["details"]["audio_uploaded"] is False

    @pytest.mark.asyncio
    async def test_generate_timeline_no_media(
        self,
        async_client: AsyncClient,
        auth_headers: dict,
        test_project: dict,
        sample_audio: bytes,
        mock_enqueue_beat_analysis: MagicMock,
    ):
        """Test that timeline generation fails without media."""
        # Upload audio but no media
        files = {"file": ("test.wav", sample_audio, "audio/wav")}
        response = await async_client.post(
            f"/api/projects/{test_project['id']}/audio",
            files=files,
            headers=auth_headers,
        )
        assert response.status_code == 201

        # Try to generate timeline (will fail because beats not complete)
        response = await async_client.post(
            f"/api/projects/{test_project['id']}/timeline/generate",
            headers=auth_headers,
        )

        assert response.status_code == 400
        data = response.json()
        assert data["detail"]["error"] == "precondition_failed"

    @pytest.mark.asyncio
    async def test_generate_timeline_not_found(
        self,
        async_client: AsyncClient,
        auth_headers: dict,
    ):
        """Test generate timeline for non-existent project."""
        fake_id = str(uuid.uuid4())
        response = await async_client.post(
            f"/api/projects/{fake_id}/timeline/generate",
            headers=auth_headers,
        )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_generate_timeline_other_user(
        self,
        async_client: AsyncClient,
        auth_headers: dict,
        second_auth_headers: dict,
    ):
        """Test that users cannot generate timeline for other users' projects."""
        # Create project as first user
        response = await async_client.post(
            "/api/projects",
            json={"name": "Private Project"},
            headers=auth_headers,
        )
        project_id = response.json()["id"]

        # Try to generate as second user
        response = await async_client.post(
            f"/api/projects/{project_id}/timeline/generate",
            headers=second_auth_headers,
        )

        assert response.status_code == 404


class TestTimelineStatus:
    """Tests for timeline status endpoint."""

    @pytest.mark.asyncio
    async def test_get_timeline_status_none(
        self,
        async_client: AsyncClient,
        auth_headers: dict,
        test_project: dict,
    ):
        """Test getting timeline status when no timeline exists."""
        response = await async_client.get(
            f"/api/projects/{test_project['id']}/timeline/status",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["generation_status"] == "none"
        assert data["edl_hash"] is None

    @pytest.mark.asyncio
    async def test_get_timeline_status_not_found(
        self,
        async_client: AsyncClient,
        auth_headers: dict,
    ):
        """Test getting timeline status for non-existent project."""
        fake_id = str(uuid.uuid4())
        response = await async_client.get(
            f"/api/projects/{fake_id}/timeline/status",
            headers=auth_headers,
        )

        assert response.status_code == 404


class TestGetTimeline:
    """Tests for getting full timeline data."""

    @pytest.mark.asyncio
    async def test_get_timeline_not_generated(
        self,
        async_client: AsyncClient,
        auth_headers: dict,
        test_project: dict,
    ):
        """Test getting timeline when not yet generated."""
        response = await async_client.get(
            f"/api/projects/{test_project['id']}/timeline",
            headers=auth_headers,
        )

        assert response.status_code == 404
        data = response.json()
        assert "not generated" in data["detail"]["message"].lower()

    @pytest.mark.asyncio
    async def test_get_timeline_not_found(
        self,
        async_client: AsyncClient,
        auth_headers: dict,
    ):
        """Test getting timeline for non-existent project."""
        fake_id = str(uuid.uuid4())
        response = await async_client.get(
            f"/api/projects/{fake_id}/timeline",
            headers=auth_headers,
        )

        assert response.status_code == 404


class TestRenderStart:
    """Tests for starting render jobs."""

    @pytest.mark.asyncio
    async def test_start_render_no_timeline(
        self,
        async_client: AsyncClient,
        auth_headers: dict,
        test_project: dict,
    ):
        """Test that render fails without timeline."""
        response = await async_client.post(
            f"/api/projects/{test_project['id']}/render",
            json={
                "type": "preview",
                "edl_hash": "fake_hash",
            },
            headers=auth_headers,
        )

        assert response.status_code == 400
        data = response.json()
        assert data["detail"]["error"] == "precondition_failed"

    @pytest.mark.asyncio
    async def test_start_render_not_found(
        self,
        async_client: AsyncClient,
        auth_headers: dict,
    ):
        """Test starting render for non-existent project."""
        fake_id = str(uuid.uuid4())
        response = await async_client.post(
            f"/api/projects/{fake_id}/render",
            json={
                "type": "preview",
                "edl_hash": "fake_hash",
            },
            headers=auth_headers,
        )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_start_render_other_user(
        self,
        async_client: AsyncClient,
        auth_headers: dict,
        second_auth_headers: dict,
    ):
        """Test that users cannot start render for other users' projects."""
        # Create project as first user
        response = await async_client.post(
            "/api/projects",
            json={"name": "Private Project"},
            headers=auth_headers,
        )
        project_id = response.json()["id"]

        # Try to render as second user
        response = await async_client.post(
            f"/api/projects/{project_id}/render",
            json={
                "type": "preview",
                "edl_hash": "fake_hash",
            },
            headers=second_auth_headers,
        )

        assert response.status_code == 404


class TestRenderStatus:
    """Tests for getting render job status."""

    @pytest.mark.asyncio
    async def test_get_render_status_not_found_job(
        self,
        async_client: AsyncClient,
        auth_headers: dict,
        test_project: dict,
    ):
        """Test getting status of non-existent render job."""
        fake_job_id = str(uuid.uuid4())
        response = await async_client.get(
            f"/api/projects/{test_project['id']}/render/{fake_job_id}/status",
            headers=auth_headers,
        )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_get_render_status_by_type_no_renders(
        self,
        async_client: AsyncClient,
        auth_headers: dict,
        test_project: dict,
    ):
        """Test getting latest render status when no renders exist."""
        response = await async_client.get(
            f"/api/projects/{test_project['id']}/render/preview/status",
            headers=auth_headers,
        )

        assert response.status_code == 404


class TestRenderDownload:
    """Tests for downloading rendered videos."""

    @pytest.mark.asyncio
    async def test_download_render_not_found(
        self,
        async_client: AsyncClient,
        auth_headers: dict,
        test_project: dict,
    ):
        """Test downloading when no render exists."""
        response = await async_client.get(
            f"/api/projects/{test_project['id']}/render/preview/download",
            headers=auth_headers,
        )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_download_render_not_found_project(
        self,
        async_client: AsyncClient,
        auth_headers: dict,
    ):
        """Test downloading from non-existent project."""
        fake_id = str(uuid.uuid4())
        response = await async_client.get(
            f"/api/projects/{fake_id}/render/preview/download",
            headers=auth_headers,
        )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_download_render_other_user(
        self,
        async_client: AsyncClient,
        auth_headers: dict,
        second_auth_headers: dict,
    ):
        """Test that users cannot download other users' renders."""
        # Create project as first user
        response = await async_client.post(
            "/api/projects",
            json={"name": "Private Project"},
            headers=auth_headers,
        )
        project_id = response.json()["id"]

        # Try to download as second user
        response = await async_client.get(
            f"/api/projects/{project_id}/render/preview/download",
            headers=second_auth_headers,
        )

        assert response.status_code == 404


class TestWorkflowWithMockedWorkers:
    """
    Tests for the complete workflow with mocked worker completion.

    These tests simulate what happens when the worker completes its jobs.
    """

    @pytest.mark.asyncio
    async def test_complete_workflow_media_upload_flow(
        self,
        async_client: AsyncClient,
        auth_headers: dict,
        sample_image: bytes,
        sample_png: bytes,
    ):
        """Test the media upload portion of the workflow."""
        # Step 1: Create project
        response = await async_client.post(
            "/api/projects",
            json={"name": "Workflow Test Project"},
            headers=auth_headers,
        )
        assert response.status_code == 201
        project = response.json()
        project_id = project["id"]

        # Step 2: Upload multiple media files
        files = [
            ("files", ("photo1.jpg", sample_image, "image/jpeg")),
            ("files", ("photo2.png", sample_png, "image/png")),
        ]
        response = await async_client.post(
            f"/api/projects/{project_id}/media",
            files=files,
            headers=auth_headers,
        )
        assert response.status_code == 201
        upload_data = response.json()
        assert upload_data["total_uploaded"] == 2

        # Step 3: Verify project shows media
        response = await async_client.get(
            f"/api/projects/{project_id}",
            headers=auth_headers,
        )
        assert response.status_code == 200
        project_data = response.json()
        assert len(project_data["media_assets"]) == 2

        # Step 4: Check project status
        response = await async_client.get(
            f"/api/projects/{project_id}/status",
            headers=auth_headers,
        )
        assert response.status_code == 200
        status = response.json()
        assert status["media"]["total"] == 2
        assert status["audio"]["uploaded"] is False
        assert status["ready_to_render"] is False

    @pytest.mark.asyncio
    async def test_workflow_audio_upload_flow(
        self,
        async_client: AsyncClient,
        auth_headers: dict,
        sample_audio: bytes,
        mock_enqueue_beat_analysis: MagicMock,
    ):
        """Test the audio upload portion of the workflow."""
        # Create project
        response = await async_client.post(
            "/api/projects",
            json={"name": "Audio Workflow Test"},
            headers=auth_headers,
        )
        assert response.status_code == 201
        project_id = response.json()["id"]

        # Upload audio
        files = {"file": ("music.wav", sample_audio, "audio/wav")}
        response = await async_client.post(
            f"/api/projects/{project_id}/audio",
            files=files,
            headers=auth_headers,
        )
        assert response.status_code == 201
        audio_data = response.json()
        assert audio_data["analysis_status"] == "queued"

        # Check beats status shows queued
        response = await async_client.get(
            f"/api/projects/{project_id}/beats/status",
            headers=auth_headers,
        )
        assert response.status_code == 200
        beats_status = response.json()
        assert beats_status["audio_uploaded"] is True
        assert beats_status["analysis_status"] == "queued"

    @pytest.mark.asyncio
    async def test_workflow_reorder_media(
        self,
        async_client: AsyncClient,
        auth_headers: dict,
        sample_image: bytes,
        sample_png: bytes,
    ):
        """Test reordering media in the workflow."""
        # Create project and upload media
        response = await async_client.post(
            "/api/projects",
            json={"name": "Reorder Test"},
            headers=auth_headers,
        )
        project_id = response.json()["id"]

        files = [
            ("files", ("first.jpg", sample_image, "image/jpeg")),
            ("files", ("second.png", sample_png, "image/png")),
        ]
        response = await async_client.post(
            f"/api/projects/{project_id}/media",
            files=files,
            headers=auth_headers,
        )
        media_ids = [m["id"] for m in response.json()["uploaded"]]

        # Reorder media
        reversed_ids = list(reversed(media_ids))
        response = await async_client.post(
            f"/api/projects/{project_id}/media/reorder",
            json={"order": reversed_ids},
            headers=auth_headers,
        )
        assert response.status_code == 200
        assert response.json()["timeline_invalidated"] is True

        # Verify new order in project
        response = await async_client.get(
            f"/api/projects/{project_id}",
            headers=auth_headers,
        )
        media_assets = response.json()["media_assets"]
        for i, asset in enumerate(media_assets):
            assert asset["id"] == reversed_ids[i]
            assert asset["sort_order"] == i

    @pytest.mark.asyncio
    async def test_workflow_update_settings(
        self,
        async_client: AsyncClient,
        auth_headers: dict,
        test_project: dict,
    ):
        """Test updating project settings in the workflow."""
        project_id = test_project["id"]

        # Update settings
        response = await async_client.patch(
            f"/api/projects/{project_id}/settings",
            json={
                "beats_per_cut": 8,
                "transition_type": "crossfade",
                "transition_duration_ms": 1000,
            },
            headers=auth_headers,
        )
        assert response.status_code == 200
        settings = response.json()["settings"]
        assert settings["beats_per_cut"] == 8
        assert settings["transition_type"] == "crossfade"
        assert settings["transition_duration_ms"] == 1000

        # Verify settings are persisted
        response = await async_client.get(
            f"/api/projects/{project_id}",
            headers=auth_headers,
        )
        project_settings = response.json()["settings"]
        assert project_settings["beats_per_cut"] == 8
        assert project_settings["transition_type"] == "crossfade"

    @pytest.mark.asyncio
    async def test_workflow_delete_media(
        self,
        async_client: AsyncClient,
        auth_headers: dict,
        sample_image: bytes,
        sample_png: bytes,
    ):
        """Test deleting media in the workflow."""
        # Create project and upload media
        response = await async_client.post(
            "/api/projects",
            json={"name": "Delete Media Test"},
            headers=auth_headers,
        )
        project_id = response.json()["id"]

        files = [
            ("files", ("keep.jpg", sample_image, "image/jpeg")),
            ("files", ("delete.png", sample_png, "image/png")),
        ]
        response = await async_client.post(
            f"/api/projects/{project_id}/media",
            files=files,
            headers=auth_headers,
        )
        media_ids = [m["id"] for m in response.json()["uploaded"]]

        # Delete one media
        response = await async_client.delete(
            f"/api/media/{media_ids[1]}",
            headers=auth_headers,
        )
        assert response.status_code == 204

        # Verify only one media remains
        response = await async_client.get(
            f"/api/projects/{project_id}",
            headers=auth_headers,
        )
        assert len(response.json()["media_assets"]) == 1
        assert response.json()["media_assets"][0]["id"] == media_ids[0]

    @pytest.mark.asyncio
    async def test_workflow_project_deletion_cascade(
        self,
        async_client: AsyncClient,
        auth_headers: dict,
        sample_image: bytes,
        sample_audio: bytes,
        mock_enqueue_beat_analysis: MagicMock,
    ):
        """Test that deleting project cascades to all related data."""
        # Create project
        response = await async_client.post(
            "/api/projects",
            json={"name": "Cascade Delete Test"},
            headers=auth_headers,
        )
        project_id = response.json()["id"]

        # Upload media
        files = {"files": ("test.jpg", sample_image, "image/jpeg")}
        response = await async_client.post(
            f"/api/projects/{project_id}/media",
            files=files,
            headers=auth_headers,
        )
        media_id = response.json()["uploaded"][0]["id"]

        # Upload audio
        files = {"file": ("test.wav", sample_audio, "audio/wav")}
        await async_client.post(
            f"/api/projects/{project_id}/audio",
            files=files,
            headers=auth_headers,
        )

        # Delete project
        response = await async_client.delete(
            f"/api/projects/{project_id}",
            headers=auth_headers,
        )
        assert response.status_code == 204

        # Verify project is gone
        response = await async_client.get(
            f"/api/projects/{project_id}",
            headers=auth_headers,
        )
        assert response.status_code == 404

        # Verify media is gone
        response = await async_client.get(
            f"/api/media/{media_id}",
            headers=auth_headers,
        )
        assert response.status_code == 404
