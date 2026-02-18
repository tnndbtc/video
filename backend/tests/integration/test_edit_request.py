"""
Integration tests for EditRequest (EDL v1) API endpoints.

Tests:
- POST /api/projects/{project_id}/edl/validate
- POST /api/projects/{project_id}/edl/save
- GET /api/projects/{project_id}/edl
- DELETE /api/projects/{project_id}/edl
"""

import uuid

import pytest
from httpx import AsyncClient


# =============================================================================
# Test Fixtures
# =============================================================================


@pytest.fixture
def simple_edit_request():
    """Simple EditRequest for testing."""
    return {
        "version": "1.0",
        "timeline": [
            {"asset_id": "test_asset_001", "type": "image"},
            {"asset_id": "test_asset_002", "type": "image"},
        ],
    }


@pytest.fixture
def edit_request_with_audio():
    """EditRequest with audio settings."""
    return {
        "version": "1.0",
        "audio": {
            "asset_id": "test_audio_001",
            "bpm": 120.0,
            "end_at_audio_end": True,
        },
        "defaults": {
            "beats_per_cut": 8,
            "effect": "slow_zoom_in",
        },
        "timeline": [
            {"asset_id": "test_asset_001", "type": "image"},
            {"asset_id": "test_asset_002", "type": "image"},
        ],
        "repeat": {"mode": "repeat_all"},
    }


@pytest.fixture
def edit_request_with_durations():
    """EditRequest with various duration modes."""
    return {
        "version": "1.0",
        "audio": {
            "asset_id": "test_audio_001",
            "bpm": 120.0,
        },
        "timeline": [
            {
                "asset_id": "test_asset_001",
                "type": "image",
                "duration": {"mode": "beats", "count": 8},
            },
            {
                "asset_id": "test_asset_002",
                "type": "image",
                "duration": {"mode": "ms", "value": 3000},
            },
            {
                "asset_id": "test_asset_003",
                "type": "video",
                "duration": {"mode": "natural"},
            },
        ],
    }


# =============================================================================
# Validate Endpoint Tests
# =============================================================================


class TestValidateEditRequest:
    """Tests for POST /api/projects/{project_id}/edl/validate"""

    @pytest.mark.asyncio
    async def test_validate_requires_auth(self, async_client: AsyncClient):
        """Test that validation requires authentication."""
        response = await async_client.post(
            f"/api/projects/{uuid.uuid4()}/edl/validate",
            json={"version": "1.0", "timeline": []},
        )
        # No auth token returns 401 (Unauthorized)
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_validate_project_not_found(
        self, async_client: AsyncClient, auth_headers: dict
    ):
        """Test validation with non-existent project."""
        response = await async_client.post(
            f"/api/projects/{uuid.uuid4()}/edl/validate",
            json={
                "version": "1.0",
                "timeline": [{"asset_id": "test", "type": "image"}],
            },
            headers=auth_headers,
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_validate_invalid_json_structure(
        self, async_client: AsyncClient, auth_headers: dict
    ):
        """Test validation with invalid JSON structure."""
        # Create a project first
        project_response = await async_client.post(
            "/api/projects",
            json={"name": "Test Project"},
            headers=auth_headers,
        )
        project_id = project_response.json()["id"]

        # Try to validate with invalid structure (empty timeline)
        response = await async_client.post(
            f"/api/projects/{project_id}/edl/validate",
            json={"version": "1.0", "timeline": []},
            headers=auth_headers,
        )
        assert response.status_code == 422  # Pydantic validation error

    @pytest.mark.asyncio
    async def test_validate_asset_not_found(
        self, async_client: AsyncClient, auth_headers: dict, simple_edit_request: dict
    ):
        """Test validation with non-existent assets."""
        # Create a project first
        project_response = await async_client.post(
            "/api/projects",
            json={"name": "Test Project"},
            headers=auth_headers,
        )
        project_id = project_response.json()["id"]

        # Validate - assets don't exist
        response = await async_client.post(
            f"/api/projects/{project_id}/edl/validate",
            json=simple_edit_request,
            headers=auth_headers,
        )

        assert response.status_code == 200  # Validation completes, returns result
        data = response.json()
        assert data["valid"] is False
        assert len(data["errors"]) > 0
        assert data["errors"][0]["code"] == "asset_not_found"

    @pytest.mark.asyncio
    async def test_validate_invalid_version(
        self, async_client: AsyncClient, auth_headers: dict
    ):
        """Test validation with invalid version."""
        # Create a project first
        project_response = await async_client.post(
            "/api/projects",
            json={"name": "Test Project"},
            headers=auth_headers,
        )
        project_id = project_response.json()["id"]

        response = await async_client.post(
            f"/api/projects/{project_id}/edl/validate",
            json={
                "version": "2.0",  # Invalid version
                "timeline": [{"asset_id": "test", "type": "image"}],
            },
            headers=auth_headers,
        )
        assert response.status_code == 422  # Pydantic validation error

    @pytest.mark.asyncio
    async def test_validate_invalid_duration_mode(
        self, async_client: AsyncClient, auth_headers: dict
    ):
        """Test validation with invalid duration mode."""
        project_response = await async_client.post(
            "/api/projects",
            json={"name": "Test Project"},
            headers=auth_headers,
        )
        project_id = project_response.json()["id"]

        response = await async_client.post(
            f"/api/projects/{project_id}/edl/validate",
            json={
                "version": "1.0",
                "timeline": [
                    {
                        "asset_id": "test",
                        "type": "image",
                        "duration": {"mode": "invalid_mode"},
                    }
                ],
            },
            headers=auth_headers,
        )
        assert response.status_code == 422


# =============================================================================
# Save Endpoint Tests
# =============================================================================


class TestSaveEditRequest:
    """Tests for POST /api/projects/{project_id}/edl/save"""

    @pytest.mark.asyncio
    async def test_save_requires_auth(self, async_client: AsyncClient):
        """Test that save requires authentication."""
        response = await async_client.post(
            f"/api/projects/{uuid.uuid4()}/edl/save",
            json={"version": "1.0", "timeline": []},
        )
        # No auth token returns 401 (Unauthorized)
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_save_project_not_found(
        self, async_client: AsyncClient, auth_headers: dict
    ):
        """Test save with non-existent project."""
        response = await async_client.post(
            f"/api/projects/{uuid.uuid4()}/edl/save",
            json={
                "version": "1.0",
                "timeline": [{"asset_id": "test", "type": "image"}],
            },
            headers=auth_headers,
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_save_validation_failure_returns_400(
        self, async_client: AsyncClient, auth_headers: dict, simple_edit_request: dict
    ):
        """Test that save returns 400 when validation fails."""
        # Create a project first
        project_response = await async_client.post(
            "/api/projects",
            json={"name": "Test Project"},
            headers=auth_headers,
        )
        project_id = project_response.json()["id"]

        # Try to save - assets don't exist
        response = await async_client.post(
            f"/api/projects/{project_id}/edl/save",
            json=simple_edit_request,
            headers=auth_headers,
        )

        assert response.status_code == 400
        data = response.json()
        assert data["detail"]["error"] == "validation_failed"
        assert data["detail"]["validation"]["valid"] is False


# =============================================================================
# Get Endpoint Tests
# =============================================================================


class TestGetEditRequest:
    """Tests for GET /api/projects/{project_id}/edl"""

    @pytest.mark.asyncio
    async def test_get_requires_auth(self, async_client: AsyncClient):
        """Test that get requires authentication."""
        response = await async_client.get(f"/api/projects/{uuid.uuid4()}/edl")
        # No auth token returns 401 (Unauthorized)
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_get_project_not_found(
        self, async_client: AsyncClient, auth_headers: dict
    ):
        """Test get with non-existent project."""
        response = await async_client.get(
            f"/api/projects/{uuid.uuid4()}/edl",
            headers=auth_headers,
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_get_no_edit_request_returns_null(
        self, async_client: AsyncClient, auth_headers: dict
    ):
        """Test that get returns null when no EditRequest saved."""
        # Create a project first
        project_response = await async_client.post(
            "/api/projects",
            json={"name": "Test Project"},
            headers=auth_headers,
        )
        project_id = project_response.json()["id"]

        # Get - should return null/204
        response = await async_client.get(
            f"/api/projects/{project_id}/edl",
            headers=auth_headers,
        )
        # Either 200 with null or 204 No Content
        assert response.status_code in [200, 204]
        if response.status_code == 200:
            assert response.json() is None


# =============================================================================
# Delete Endpoint Tests
# =============================================================================


class TestDeleteEditRequest:
    """Tests for DELETE /api/projects/{project_id}/edl"""

    @pytest.mark.asyncio
    async def test_delete_requires_auth(self, async_client: AsyncClient):
        """Test that delete requires authentication."""
        response = await async_client.delete(f"/api/projects/{uuid.uuid4()}/edl")
        # No auth token returns 401 (Unauthorized)
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_delete_project_not_found(
        self, async_client: AsyncClient, auth_headers: dict
    ):
        """Test delete with non-existent project."""
        response = await async_client.delete(
            f"/api/projects/{uuid.uuid4()}/edl",
            headers=auth_headers,
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_no_edit_request_succeeds(
        self, async_client: AsyncClient, auth_headers: dict
    ):
        """Test that delete succeeds even when no EditRequest saved."""
        # Create a project first
        project_response = await async_client.post(
            "/api/projects",
            json={"name": "Test Project"},
            headers=auth_headers,
        )
        project_id = project_response.json()["id"]

        # Delete - should succeed (no-op)
        response = await async_client.delete(
            f"/api/projects/{project_id}/edl",
            headers=auth_headers,
        )
        assert response.status_code == 204


# =============================================================================
# Schema Validation Tests (Pydantic)
# =============================================================================


class TestEditRequestSchema:
    """Tests for EditRequest schema validation at API level."""

    @pytest.mark.asyncio
    async def test_beats_count_validation(
        self, async_client: AsyncClient, auth_headers: dict
    ):
        """Test that beats count is validated."""
        project_response = await async_client.post(
            "/api/projects",
            json={"name": "Test Project"},
            headers=auth_headers,
        )
        project_id = project_response.json()["id"]

        # Beats count too high (> 64)
        response = await async_client.post(
            f"/api/projects/{project_id}/edl/validate",
            json={
                "version": "1.0",
                "timeline": [
                    {
                        "asset_id": "test",
                        "type": "image",
                        "duration": {"mode": "beats", "count": 100},
                    }
                ],
            },
            headers=auth_headers,
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_ms_duration_validation(
        self, async_client: AsyncClient, auth_headers: dict
    ):
        """Test that ms duration is validated."""
        project_response = await async_client.post(
            "/api/projects",
            json={"name": "Test Project"},
            headers=auth_headers,
        )
        project_id = project_response.json()["id"]

        # Duration too short (< 250ms)
        response = await async_client.post(
            f"/api/projects/{project_id}/edl/validate",
            json={
                "version": "1.0",
                "timeline": [
                    {
                        "asset_id": "test",
                        "type": "image",
                        "duration": {"mode": "ms", "value": 100},
                    }
                ],
            },
            headers=auth_headers,
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_transition_duration_validation(
        self, async_client: AsyncClient, auth_headers: dict
    ):
        """Test that transition duration is validated."""
        project_response = await async_client.post(
            "/api/projects",
            json={"name": "Test Project"},
            headers=auth_headers,
        )
        project_id = project_response.json()["id"]

        # Transition too long (> 2000ms)
        response = await async_client.post(
            f"/api/projects/{project_id}/edl/validate",
            json={
                "version": "1.0",
                "timeline": [
                    {
                        "asset_id": "test",
                        "type": "image",
                        "transition_in": {"type": "crossfade", "duration_ms": 5000},
                    }
                ],
            },
            headers=auth_headers,
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_effect_preset_validation(
        self, async_client: AsyncClient, auth_headers: dict
    ):
        """Test that effect preset is validated."""
        project_response = await async_client.post(
            "/api/projects",
            json={"name": "Test Project"},
            headers=auth_headers,
        )
        project_id = project_response.json()["id"]

        # Invalid effect preset
        response = await async_client.post(
            f"/api/projects/{project_id}/edl/validate",
            json={
                "version": "1.0",
                "timeline": [
                    {
                        "asset_id": "test",
                        "type": "image",
                        "effect": "invalid_effect",
                    }
                ],
            },
            headers=auth_headers,
        )
        assert response.status_code == 422
