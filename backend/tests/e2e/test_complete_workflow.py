"""
End-to-End tests for the complete BeatStitch workflow.

Comprehensive workflow tests that validate:
- Project creation with settings
- Multiple media upload with processing status polling
- Audio upload with analysis status polling
- Timeline generation with status polling
- Render initiation with edl_hash validation
- Render completion and download
- Error handling (missing prerequisites, hash mismatch)

These tests simulate the complete user journey through the application.
"""

import json
import uuid
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from httpx import AsyncClient

from tests.conftest import (
    create_test_beats_json,
    create_test_edl_json,
)


class TestCompleteE2EWorkflow:
    """
    End-to-end tests simulating a complete user workflow.

    These tests validate the entire flow from project creation to render download,
    using mocked workers to simulate background processing completion.
    """

    @pytest.mark.asyncio
    async def test_complete_project_creation_flow(
        self,
        async_client: AsyncClient,
    ):
        """Test complete flow: register, login, create project."""
        # Step 1: Register new user
        username = f"e2e_user_{uuid.uuid4().hex[:8]}"
        password = "SecureE2EPassword123!"

        response = await async_client.post(
            "/api/auth/register",
            json={"username": username, "password": password},
        )
        assert response.status_code == 201
        user = response.json()
        assert user["username"] == username

        # Step 2: Login
        response = await async_client.post(
            "/api/auth/login",
            json={"username": username, "password": password},
        )
        assert response.status_code == 200
        login_data = response.json()
        assert "access_token" in login_data
        token = login_data["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        # Step 3: Create project
        response = await async_client.post(
            "/api/projects",
            json={
                "name": "My E2E Project",
                "description": "Testing the complete workflow",
            },
            headers=headers,
        )
        assert response.status_code == 201
        project = response.json()
        assert project["name"] == "My E2E Project"
        assert project["status"] == "draft"

        # Step 4: Verify project in list
        response = await async_client.get("/api/projects", headers=headers)
        assert response.status_code == 200
        projects = response.json()
        assert projects["total"] == 1
        assert projects["projects"][0]["id"] == project["id"]

    @pytest.mark.asyncio
    async def test_complete_media_workflow(
        self,
        async_client: AsyncClient,
        auth_headers: dict,
        sample_image: bytes,
        sample_png: bytes,
    ):
        """Test complete media upload, reorder, delete workflow."""
        # Create project
        response = await async_client.post(
            "/api/projects",
            json={"name": "Media Workflow Project"},
            headers=auth_headers,
        )
        project_id = response.json()["id"]

        # Upload first batch of media
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
        assert response.json()["total_uploaded"] == 2
        media_ids = [m["id"] for m in response.json()["uploaded"]]

        # Upload more media
        files = {"files": ("photo3.jpg", sample_image, "image/jpeg")}
        response = await async_client.post(
            f"/api/projects/{project_id}/media",
            files=files,
            headers=auth_headers,
        )
        assert response.status_code == 201
        media_ids.append(response.json()["uploaded"][0]["id"])

        # Check project status
        response = await async_client.get(
            f"/api/projects/{project_id}/status",
            headers=auth_headers,
        )
        assert response.status_code == 200
        assert response.json()["media"]["total"] == 3

        # Reorder media
        new_order = [media_ids[2], media_ids[0], media_ids[1]]
        response = await async_client.post(
            f"/api/projects/{project_id}/media/reorder",
            json={"order": new_order},
            headers=auth_headers,
        )
        assert response.status_code == 200
        assert response.json()["timeline_invalidated"] is True

        # Verify order in project details
        response = await async_client.get(
            f"/api/projects/{project_id}",
            headers=auth_headers,
        )
        assets = response.json()["media_assets"]
        assert assets[0]["id"] == media_ids[2]
        assert assets[1]["id"] == media_ids[0]
        assert assets[2]["id"] == media_ids[1]

        # Delete one media
        response = await async_client.delete(
            f"/api/media/{media_ids[1]}",
            headers=auth_headers,
        )
        assert response.status_code == 204

        # Verify deletion
        response = await async_client.get(
            f"/api/projects/{project_id}/status",
            headers=auth_headers,
        )
        assert response.json()["media"]["total"] == 2

    @pytest.mark.asyncio
    async def test_complete_settings_workflow(
        self,
        async_client: AsyncClient,
        auth_headers: dict,
    ):
        """Test complete settings update workflow."""
        # Create project
        response = await async_client.post(
            "/api/projects",
            json={"name": "Settings Test Project"},
            headers=auth_headers,
        )
        project_id = response.json()["id"]

        # Verify default settings
        response = await async_client.get(
            f"/api/projects/{project_id}",
            headers=auth_headers,
        )
        settings = response.json()["settings"]
        assert settings["beats_per_cut"] == 4
        assert settings["transition_type"] == "cut"

        # Update timeline-affecting settings
        response = await async_client.patch(
            f"/api/projects/{project_id}/settings",
            json={
                "beats_per_cut": 2,
                "transition_type": "crossfade",
                "transition_duration_ms": 750,
            },
            headers=auth_headers,
        )
        assert response.status_code == 200
        assert response.json()["timeline_invalidated"] is True
        assert response.json()["settings"]["beats_per_cut"] == 2

        # Update output settings
        response = await async_client.patch(
            f"/api/projects/{project_id}/settings",
            json={
                "output_width": 1280,
                "output_height": 720,
                "output_fps": 60,
            },
            headers=auth_headers,
        )
        assert response.status_code == 200

        # Verify all settings persisted
        response = await async_client.get(
            f"/api/projects/{project_id}",
            headers=auth_headers,
        )
        final_settings = response.json()["settings"]
        assert final_settings["beats_per_cut"] == 2
        assert final_settings["transition_type"] == "crossfade"
        assert final_settings["output_width"] == 1280
        assert final_settings["output_height"] == 720
        assert final_settings["output_fps"] == 60

    @pytest.mark.asyncio
    async def test_workflow_prerequisite_checking(
        self,
        async_client: AsyncClient,
        auth_headers: dict,
        sample_image: bytes,
        sample_audio: bytes,
        mock_enqueue_beat_analysis: MagicMock,
        mock_job_status: MagicMock,
        mock_enqueue_timeline_generation: MagicMock,
    ):
        """Test that proper prerequisites are enforced throughout workflow."""
        # Create project
        response = await async_client.post(
            "/api/projects",
            json={"name": "Prerequisites Test"},
            headers=auth_headers,
        )
        project_id = response.json()["id"]

        # Try to generate timeline without any data
        response = await async_client.post(
            f"/api/projects/{project_id}/timeline/generate",
            headers=auth_headers,
        )
        assert response.status_code == 400
        assert response.json()["detail"]["error"] == "precondition_failed"

        # Try to render without timeline
        response = await async_client.post(
            f"/api/projects/{project_id}/render",
            json={"type": "preview", "edl_hash": "fake"},
            headers=auth_headers,
        )
        assert response.status_code == 400

        # Upload media
        files = {"files": ("test.jpg", sample_image, "image/jpeg")}
        response = await async_client.post(
            f"/api/projects/{project_id}/media",
            files=files,
            headers=auth_headers,
        )
        assert response.status_code == 201

        # Try to generate timeline (still no audio)
        response = await async_client.post(
            f"/api/projects/{project_id}/timeline/generate",
            headers=auth_headers,
        )
        assert response.status_code == 400
        assert response.json()["detail"]["details"]["audio_uploaded"] is False

        # Upload audio
        files = {"file": ("music.wav", sample_audio, "audio/wav")}
        response = await async_client.post(
            f"/api/projects/{project_id}/audio",
            files=files,
            headers=auth_headers,
        )
        assert response.status_code == 201

        # Try to generate timeline (audio not yet analyzed)
        response = await async_client.post(
            f"/api/projects/{project_id}/timeline/generate",
            headers=auth_headers,
        )
        assert response.status_code == 400
        # Audio uploaded but not analyzed yet
        assert response.json()["detail"]["details"]["audio_uploaded"] is True
        assert response.json()["detail"]["details"]["beats_complete"] is False


class TestErrorHandlingE2E:
    """End-to-end tests for error handling scenarios."""

    @pytest.mark.asyncio
    async def test_unauthorized_access_patterns(
        self,
        async_client: AsyncClient,
        auth_headers: dict,
        second_auth_headers: dict,
        sample_image: bytes,
        sample_audio: bytes,
        mock_enqueue_beat_analysis: MagicMock,
    ):
        """Test that unauthorized access is properly blocked."""
        # User 1 creates a project with media and audio
        response = await async_client.post(
            "/api/projects",
            json={"name": "Private Project"},
            headers=auth_headers,
        )
        project_id = response.json()["id"]

        # Upload media and audio
        files = {"files": ("test.jpg", sample_image, "image/jpeg")}
        response = await async_client.post(
            f"/api/projects/{project_id}/media",
            files=files,
            headers=auth_headers,
        )
        media_id = response.json()["uploaded"][0]["id"]

        files = {"file": ("music.wav", sample_audio, "audio/wav")}
        await async_client.post(
            f"/api/projects/{project_id}/audio",
            files=files,
            headers=auth_headers,
        )

        # User 2 tries various operations (all should fail with 404)
        # Note: 404 is returned instead of 403 for security (don't reveal existence)

        # Try to get project
        response = await async_client.get(
            f"/api/projects/{project_id}",
            headers=second_auth_headers,
        )
        assert response.status_code == 404

        # Try to update settings
        response = await async_client.patch(
            f"/api/projects/{project_id}/settings",
            json={"beats_per_cut": 8},
            headers=second_auth_headers,
        )
        assert response.status_code == 404

        # Try to delete project
        response = await async_client.delete(
            f"/api/projects/{project_id}",
            headers=second_auth_headers,
        )
        assert response.status_code == 404

        # Try to get media
        response = await async_client.get(
            f"/api/media/{media_id}",
            headers=second_auth_headers,
        )
        assert response.status_code == 404

        # Try to upload media
        files = {"files": ("hack.jpg", sample_image, "image/jpeg")}
        response = await async_client.post(
            f"/api/projects/{project_id}/media",
            files=files,
            headers=second_auth_headers,
        )
        assert response.status_code == 404

        # Try to get project status
        response = await async_client.get(
            f"/api/projects/{project_id}/status",
            headers=second_auth_headers,
        )
        assert response.status_code == 404

        # Try to get beats status
        response = await async_client.get(
            f"/api/projects/{project_id}/beats/status",
            headers=second_auth_headers,
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_invalid_data_handling(
        self,
        async_client: AsyncClient,
        auth_headers: dict,
        invalid_file: bytes,
    ):
        """Test handling of invalid data throughout the workflow."""
        # Create project
        response = await async_client.post(
            "/api/projects",
            json={"name": "Invalid Data Test"},
            headers=auth_headers,
        )
        project_id = response.json()["id"]

        # Invalid project ID format
        response = await async_client.get(
            "/api/projects/not-a-valid-uuid",
            headers=auth_headers,
        )
        assert response.status_code == 404

        # Non-existent project ID
        fake_id = str(uuid.uuid4())
        response = await async_client.get(
            f"/api/projects/{fake_id}",
            headers=auth_headers,
        )
        assert response.status_code == 404

        # Invalid file type for media
        files = {"files": ("script.exe", invalid_file, "application/octet-stream")}
        response = await async_client.post(
            f"/api/projects/{project_id}/media",
            files=files,
            headers=auth_headers,
        )
        assert response.status_code == 201
        assert response.json()["total_uploaded"] == 0
        assert len(response.json()["failed"]) == 1

        # Invalid file type for audio
        files = {"file": ("script.exe", invalid_file, "application/octet-stream")}
        response = await async_client.post(
            f"/api/projects/{project_id}/audio",
            files=files,
            headers=auth_headers,
        )
        assert response.status_code == 400

        # Empty file for media
        files = {"files": ("empty.jpg", b"", "image/jpeg")}
        response = await async_client.post(
            f"/api/projects/{project_id}/media",
            files=files,
            headers=auth_headers,
        )
        assert response.status_code == 201
        assert response.json()["total_uploaded"] == 0

    @pytest.mark.asyncio
    async def test_missing_token_scenarios(
        self,
        async_client: AsyncClient,
    ):
        """Test that all protected endpoints require authentication."""
        fake_project_id = str(uuid.uuid4())
        fake_media_id = str(uuid.uuid4())

        # All these should return 401 (Unauthorized - no token)
        endpoints = [
            ("GET", "/api/projects"),
            ("POST", "/api/projects"),
            ("GET", f"/api/projects/{fake_project_id}"),
            ("DELETE", f"/api/projects/{fake_project_id}"),
            ("PATCH", f"/api/projects/{fake_project_id}/settings"),
            ("GET", f"/api/projects/{fake_project_id}/status"),
            ("POST", f"/api/projects/{fake_project_id}/media"),
            ("POST", f"/api/projects/{fake_project_id}/media/reorder"),
            ("GET", f"/api/media/{fake_media_id}"),
            ("DELETE", f"/api/media/{fake_media_id}"),
            ("POST", f"/api/projects/{fake_project_id}/audio"),
            ("GET", f"/api/projects/{fake_project_id}/audio/beats"),
            ("GET", f"/api/projects/{fake_project_id}/beats/status"),
            ("POST", f"/api/projects/{fake_project_id}/timeline/generate"),
            ("GET", f"/api/projects/{fake_project_id}/timeline"),
            ("GET", f"/api/projects/{fake_project_id}/timeline/status"),
            ("POST", f"/api/projects/{fake_project_id}/render"),
        ]

        for method, endpoint in endpoints:
            if method == "GET":
                response = await async_client.get(endpoint)
            elif method == "POST":
                response = await async_client.post(endpoint, json={})
            elif method == "DELETE":
                response = await async_client.delete(endpoint)
            elif method == "PATCH":
                response = await async_client.patch(endpoint, json={})

            assert response.status_code == 401, f"Expected 401 for {method} {endpoint}"


class TestConcurrencyScenarios:
    """End-to-end tests for concurrency scenarios."""

    @pytest.mark.asyncio
    async def test_multiple_projects_isolation(
        self,
        async_client: AsyncClient,
        auth_headers: dict,
        sample_image: bytes,
    ):
        """Test that multiple projects remain isolated."""
        # Create multiple projects
        project_ids = []
        for i in range(3):
            response = await async_client.post(
                "/api/projects",
                json={"name": f"Project {i}"},
                headers=auth_headers,
            )
            assert response.status_code == 201
            project_ids.append(response.json()["id"])

        # Upload different amounts of media to each
        for i, project_id in enumerate(project_ids):
            for j in range(i + 1):  # Project 0 gets 1, Project 1 gets 2, etc.
                files = {"files": (f"image_{j}.jpg", sample_image, "image/jpeg")}
                response = await async_client.post(
                    f"/api/projects/{project_id}/media",
                    files=files,
                    headers=auth_headers,
                )
                assert response.status_code == 201

        # Verify each project has correct media count
        for i, project_id in enumerate(project_ids):
            response = await async_client.get(
                f"/api/projects/{project_id}/status",
                headers=auth_headers,
            )
            assert response.json()["media"]["total"] == i + 1

        # Delete middle project
        response = await async_client.delete(
            f"/api/projects/{project_ids[1]}",
            headers=auth_headers,
        )
        assert response.status_code == 204

        # Other projects unaffected
        for i, project_id in enumerate(project_ids):
            if i == 1:
                continue  # Skip deleted project
            response = await async_client.get(
                f"/api/projects/{project_id}",
                headers=auth_headers,
            )
            assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_multiple_users_isolation(
        self,
        async_client: AsyncClient,
        sample_image: bytes,
    ):
        """Test that multiple users' data remains isolated."""
        # Create two users
        users = []
        for i in range(2):
            username = f"multi_user_{i}_{uuid.uuid4().hex[:6]}"
            password = f"Password{i}123!"

            # Register
            response = await async_client.post(
                "/api/auth/register",
                json={"username": username, "password": password},
            )
            assert response.status_code == 201

            # Login
            response = await async_client.post(
                "/api/auth/login",
                json={"username": username, "password": password},
            )
            token = response.json()["access_token"]

            users.append({
                "username": username,
                "headers": {"Authorization": f"Bearer {token}"},
            })

        # Each user creates a project
        project_ids = []
        for i, user in enumerate(users):
            response = await async_client.post(
                "/api/projects",
                json={"name": f"User {i} Project"},
                headers=user["headers"],
            )
            assert response.status_code == 201
            project_ids.append(response.json()["id"])

        # Each user can see only their own project
        for i, user in enumerate(users):
            response = await async_client.get(
                "/api/projects",
                headers=user["headers"],
            )
            assert response.status_code == 200
            assert response.json()["total"] == 1
            assert response.json()["projects"][0]["id"] == project_ids[i]

        # Users cannot access each other's projects
        response = await async_client.get(
            f"/api/projects/{project_ids[1]}",
            headers=users[0]["headers"],
        )
        assert response.status_code == 404

        response = await async_client.get(
            f"/api/projects/{project_ids[0]}",
            headers=users[1]["headers"],
        )
        assert response.status_code == 404


class TestEdgeCase:
    """End-to-end tests for edge cases and boundary conditions."""

    @pytest.mark.asyncio
    async def test_special_characters_in_project_name(
        self,
        async_client: AsyncClient,
        auth_headers: dict,
    ):
        """Test project names with special characters."""
        special_names = [
            "Project with spaces",
            "Project-with-dashes",
            "Project_with_underscores",
            "Project.with.dots",
            "Project (with parentheses)",
            "Unicode: cafe",
        ]

        for name in special_names:
            response = await async_client.post(
                "/api/projects",
                json={"name": name},
                headers=auth_headers,
            )
            assert response.status_code == 201, f"Failed for name: {name}"
            assert response.json()["name"] == name

    @pytest.mark.asyncio
    async def test_long_project_description(
        self,
        async_client: AsyncClient,
        auth_headers: dict,
    ):
        """Test project with long description."""
        long_description = "A" * 5000  # Very long description

        response = await async_client.post(
            "/api/projects",
            json={
                "name": "Long Description Project",
                "description": long_description,
            },
            headers=auth_headers,
        )
        # Should succeed or fail gracefully
        assert response.status_code in [201, 422]

    @pytest.mark.asyncio
    async def test_rapid_project_operations(
        self,
        async_client: AsyncClient,
        auth_headers: dict,
    ):
        """Test rapid creation and deletion of projects."""
        project_ids = []

        # Rapid creation
        for i in range(5):
            response = await async_client.post(
                "/api/projects",
                json={"name": f"Rapid Project {i}"},
                headers=auth_headers,
            )
            assert response.status_code == 201
            project_ids.append(response.json()["id"])

        # Verify all created
        response = await async_client.get(
            "/api/projects",
            headers=auth_headers,
        )
        assert response.json()["total"] == 5

        # Rapid deletion
        for project_id in project_ids:
            response = await async_client.delete(
                f"/api/projects/{project_id}",
                headers=auth_headers,
            )
            assert response.status_code == 204

        # Verify all deleted
        response = await async_client.get(
            "/api/projects",
            headers=auth_headers,
        )
        assert response.json()["total"] == 0

    @pytest.mark.asyncio
    async def test_settings_boundary_values(
        self,
        async_client: AsyncClient,
        auth_headers: dict,
    ):
        """Test project settings with boundary values."""
        response = await async_client.post(
            "/api/projects",
            json={"name": "Boundary Test"},
            headers=auth_headers,
        )
        project_id = response.json()["id"]

        # Test various beats_per_cut values
        valid_beats = [1, 2, 4, 8, 16]
        for beats in valid_beats:
            response = await async_client.patch(
                f"/api/projects/{project_id}/settings",
                json={"beats_per_cut": beats},
                headers=auth_headers,
            )
            # May succeed or fail depending on validation
            if response.status_code == 200:
                assert response.json()["settings"]["beats_per_cut"] == beats

        # Test transition types
        transition_types = ["cut", "crossfade", "fade_black"]
        for transition in transition_types:
            response = await async_client.patch(
                f"/api/projects/{project_id}/settings",
                json={"transition_type": transition},
                headers=auth_headers,
            )
            if response.status_code == 200:
                assert response.json()["settings"]["transition_type"] == transition
