"""
Integration tests for project CRUD operations.

Tests:
- Create project
- List projects (user isolation)
- Get single project
- Update project settings
- Delete project
- Access other user's project (forbidden)
- Project status endpoint
"""

import uuid

import pytest
from httpx import AsyncClient


class TestCreateProject:
    """Tests for project creation endpoint."""

    @pytest.mark.asyncio
    async def test_create_project_success(
        self, async_client: AsyncClient, auth_headers: dict
    ):
        """Test successful project creation."""
        project_name = f"Test Project {uuid.uuid4().hex[:8]}"
        response = await async_client.post(
            "/api/projects",
            json={"name": project_name},
            headers=auth_headers,
        )

        assert response.status_code == 201
        data = response.json()
        assert data["name"] == project_name
        assert "id" in data
        assert data["status"] == "draft"
        assert "settings" in data
        assert "created_at" in data
        assert data["media_assets"] == []
        assert data["audio_track"] is None
        assert data["timeline"] is None

    @pytest.mark.asyncio
    async def test_create_project_with_description(
        self, async_client: AsyncClient, auth_headers: dict
    ):
        """Test project creation with optional description."""
        response = await async_client.post(
            "/api/projects",
            json={
                "name": "Project With Description",
                "description": "A detailed description of this project",
            },
            headers=auth_headers,
        )

        assert response.status_code == 201
        data = response.json()
        assert data["description"] == "A detailed description of this project"

    @pytest.mark.asyncio
    async def test_create_project_default_settings(
        self, async_client: AsyncClient, auth_headers: dict
    ):
        """Test that projects are created with default settings."""
        response = await async_client.post(
            "/api/projects",
            json={"name": "Default Settings Project"},
            headers=auth_headers,
        )

        assert response.status_code == 201
        settings = response.json()["settings"]

        # Verify default settings
        assert settings["beats_per_cut"] == 4
        assert settings["transition_type"] == "cut"
        assert settings["transition_duration_ms"] == 500
        assert settings["ken_burns_enabled"] is True
        assert settings["output_width"] == 1920
        assert settings["output_height"] == 1080
        assert settings["output_fps"] == 30

    @pytest.mark.asyncio
    async def test_create_project_missing_name(
        self, async_client: AsyncClient, auth_headers: dict
    ):
        """Test that project name is required."""
        response = await async_client.post(
            "/api/projects",
            json={},
            headers=auth_headers,
        )

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_create_project_without_auth(self, async_client: AsyncClient):
        """Test that authentication is required to create projects."""
        response = await async_client.post(
            "/api/projects",
            json={"name": "Unauthorized Project"},
        )

        assert response.status_code == 401


class TestListProjects:
    """Tests for project listing endpoint."""

    @pytest.mark.asyncio
    async def test_list_projects_empty(
        self, async_client: AsyncClient, auth_headers: dict
    ):
        """Test listing projects when user has none."""
        response = await async_client.get(
            "/api/projects",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["projects"] == []
        assert data["total"] == 0

    @pytest.mark.asyncio
    async def test_list_projects_with_projects(
        self, async_client: AsyncClient, auth_headers: dict
    ):
        """Test listing projects when user has some."""
        # Create a few projects
        project_names = ["Project A", "Project B", "Project C"]
        for name in project_names:
            response = await async_client.post(
                "/api/projects",
                json={"name": name},
                headers=auth_headers,
            )
            assert response.status_code == 201

        # List projects
        response = await async_client.get(
            "/api/projects",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 3
        assert len(data["projects"]) == 3

        # Check project structure
        for project in data["projects"]:
            assert "id" in project
            assert "name" in project
            assert "status" in project
            assert "media_count" in project
            assert "has_audio" in project
            assert "created_at" in project

    @pytest.mark.asyncio
    async def test_list_projects_user_isolation(
        self,
        async_client: AsyncClient,
        auth_headers: dict,
        second_auth_headers: dict,
    ):
        """Test that users only see their own projects."""
        # Create project as first user
        response = await async_client.post(
            "/api/projects",
            json={"name": "User 1 Project"},
            headers=auth_headers,
        )
        assert response.status_code == 201

        # Create project as second user
        response = await async_client.post(
            "/api/projects",
            json={"name": "User 2 Project"},
            headers=second_auth_headers,
        )
        assert response.status_code == 201

        # List as first user
        response = await async_client.get(
            "/api/projects",
            headers=auth_headers,
        )
        assert response.status_code == 200
        user1_projects = response.json()["projects"]
        assert len(user1_projects) == 1
        assert user1_projects[0]["name"] == "User 1 Project"

        # List as second user
        response = await async_client.get(
            "/api/projects",
            headers=second_auth_headers,
        )
        assert response.status_code == 200
        user2_projects = response.json()["projects"]
        assert len(user2_projects) == 1
        assert user2_projects[0]["name"] == "User 2 Project"


class TestGetProject:
    """Tests for getting a single project."""

    @pytest.mark.asyncio
    async def test_get_project_success(
        self, async_client: AsyncClient, auth_headers: dict, test_project: dict
    ):
        """Test getting a project by ID."""
        response = await async_client.get(
            f"/api/projects/{test_project['id']}",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == test_project["id"]
        assert data["name"] == test_project["name"]
        assert "settings" in data
        assert "media_assets" in data
        assert "audio_track" in data
        assert "timeline" in data

    @pytest.mark.asyncio
    async def test_get_project_not_found(
        self, async_client: AsyncClient, auth_headers: dict
    ):
        """Test getting a non-existent project."""
        fake_id = str(uuid.uuid4())
        response = await async_client.get(
            f"/api/projects/{fake_id}",
            headers=auth_headers,
        )

        assert response.status_code == 404
        data = response.json()
        assert data["detail"]["error"] == "not_found"

    @pytest.mark.asyncio
    async def test_get_project_invalid_id(
        self, async_client: AsyncClient, auth_headers: dict
    ):
        """Test getting a project with invalid ID format."""
        response = await async_client.get(
            "/api/projects/invalid-not-uuid",
            headers=auth_headers,
        )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_get_other_user_project(
        self,
        async_client: AsyncClient,
        auth_headers: dict,
        second_auth_headers: dict,
    ):
        """Test that users cannot access other users' projects."""
        # Create project as first user
        response = await async_client.post(
            "/api/projects",
            json={"name": "Private Project"},
            headers=auth_headers,
        )
        assert response.status_code == 201
        project_id = response.json()["id"]

        # Try to access as second user
        response = await async_client.get(
            f"/api/projects/{project_id}",
            headers=second_auth_headers,
        )

        assert response.status_code == 404  # Returns 404 for security (not 403)


class TestUpdateProjectSettings:
    """Tests for updating project settings."""

    @pytest.mark.asyncio
    async def test_update_settings_single_field(
        self, async_client: AsyncClient, auth_headers: dict, test_project: dict
    ):
        """Test updating a single setting."""
        response = await async_client.patch(
            f"/api/projects/{test_project['id']}/settings",
            json={"beats_per_cut": 8},
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["settings"]["beats_per_cut"] == 8
        # Other settings should remain unchanged
        assert data["settings"]["transition_type"] == "cut"

    @pytest.mark.asyncio
    async def test_update_settings_multiple_fields(
        self, async_client: AsyncClient, auth_headers: dict, test_project: dict
    ):
        """Test updating multiple settings at once."""
        response = await async_client.patch(
            f"/api/projects/{test_project['id']}/settings",
            json={
                "beats_per_cut": 2,
                "transition_type": "crossfade",
                "transition_duration_ms": 1000,
                "ken_burns_enabled": False,
            },
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["settings"]["beats_per_cut"] == 2
        assert data["settings"]["transition_type"] == "crossfade"
        assert data["settings"]["transition_duration_ms"] == 1000
        assert data["settings"]["ken_burns_enabled"] is False

    @pytest.mark.asyncio
    async def test_update_settings_timeline_invalidation(
        self, async_client: AsyncClient, auth_headers: dict, test_project: dict
    ):
        """Test that timeline-affecting settings return invalidation flag."""
        response = await async_client.patch(
            f"/api/projects/{test_project['id']}/settings",
            json={"beats_per_cut": 16},
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["timeline_invalidated"] is True

    @pytest.mark.asyncio
    async def test_update_output_settings(
        self, async_client: AsyncClient, auth_headers: dict, test_project: dict
    ):
        """Test updating output resolution and fps."""
        response = await async_client.patch(
            f"/api/projects/{test_project['id']}/settings",
            json={
                "output_width": 1280,
                "output_height": 720,
                "output_fps": 60,
            },
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["settings"]["output_width"] == 1280
        assert data["settings"]["output_height"] == 720
        assert data["settings"]["output_fps"] == 60

    @pytest.mark.asyncio
    async def test_update_settings_not_found(
        self, async_client: AsyncClient, auth_headers: dict
    ):
        """Test updating settings for non-existent project."""
        fake_id = str(uuid.uuid4())
        response = await async_client.patch(
            f"/api/projects/{fake_id}/settings",
            json={"beats_per_cut": 8},
            headers=auth_headers,
        )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_update_settings_other_user_project(
        self,
        async_client: AsyncClient,
        auth_headers: dict,
        second_auth_headers: dict,
    ):
        """Test that users cannot update other users' project settings."""
        # Create project as first user
        response = await async_client.post(
            "/api/projects",
            json={"name": "Protected Project"},
            headers=auth_headers,
        )
        project_id = response.json()["id"]

        # Try to update as second user
        response = await async_client.patch(
            f"/api/projects/{project_id}/settings",
            json={"beats_per_cut": 8},
            headers=second_auth_headers,
        )

        assert response.status_code == 404


class TestDeleteProject:
    """Tests for project deletion."""

    @pytest.mark.asyncio
    async def test_delete_project_success(
        self, async_client: AsyncClient, auth_headers: dict
    ):
        """Test successful project deletion."""
        # Create a project
        response = await async_client.post(
            "/api/projects",
            json={"name": "To Be Deleted"},
            headers=auth_headers,
        )
        project_id = response.json()["id"]

        # Delete it
        response = await async_client.delete(
            f"/api/projects/{project_id}",
            headers=auth_headers,
        )

        assert response.status_code == 204

        # Verify it's gone
        response = await async_client.get(
            f"/api/projects/{project_id}",
            headers=auth_headers,
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_project_not_found(
        self, async_client: AsyncClient, auth_headers: dict
    ):
        """Test deleting a non-existent project."""
        fake_id = str(uuid.uuid4())
        response = await async_client.delete(
            f"/api/projects/{fake_id}",
            headers=auth_headers,
        )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_other_user_project(
        self,
        async_client: AsyncClient,
        auth_headers: dict,
        second_auth_headers: dict,
    ):
        """Test that users cannot delete other users' projects."""
        # Create project as first user
        response = await async_client.post(
            "/api/projects",
            json={"name": "Cannot Delete Me"},
            headers=auth_headers,
        )
        project_id = response.json()["id"]

        # Try to delete as second user
        response = await async_client.delete(
            f"/api/projects/{project_id}",
            headers=second_auth_headers,
        )

        assert response.status_code == 404

        # Verify it still exists for the owner
        response = await async_client.get(
            f"/api/projects/{project_id}",
            headers=auth_headers,
        )
        assert response.status_code == 200


class TestProjectStatus:
    """Tests for project status endpoint."""

    @pytest.mark.asyncio
    async def test_get_status_empty_project(
        self, async_client: AsyncClient, auth_headers: dict, test_project: dict
    ):
        """Test getting status of empty project."""
        response = await async_client.get(
            f"/api/projects/{test_project['id']}/status",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["project_id"] == test_project["id"]
        assert data["media"]["total"] == 0
        assert data["audio"]["uploaded"] is False
        assert data["timeline"]["generated"] is False
        assert data["ready_to_render"] is False

    @pytest.mark.asyncio
    async def test_get_status_with_media(
        self,
        async_client: AsyncClient,
        auth_headers: dict,
        test_project: dict,
        sample_image: bytes,
    ):
        """Test getting status of project with media."""
        # Upload media
        files = {"files": ("test.jpg", sample_image, "image/jpeg")}
        response = await async_client.post(
            f"/api/projects/{test_project['id']}/media",
            files=files,
            headers=auth_headers,
        )
        assert response.status_code == 201

        # Get status
        response = await async_client.get(
            f"/api/projects/{test_project['id']}/status",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["media"]["total"] >= 1
        assert data["ready_to_render"] is False  # Still needs audio and timeline

    @pytest.mark.asyncio
    async def test_get_status_not_found(
        self, async_client: AsyncClient, auth_headers: dict
    ):
        """Test getting status of non-existent project."""
        fake_id = str(uuid.uuid4())
        response = await async_client.get(
            f"/api/projects/{fake_id}/status",
            headers=auth_headers,
        )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_get_status_other_user_project(
        self,
        async_client: AsyncClient,
        auth_headers: dict,
        second_auth_headers: dict,
    ):
        """Test that users cannot get status of other users' projects."""
        # Create project as first user
        response = await async_client.post(
            "/api/projects",
            json={"name": "Secret Project"},
            headers=auth_headers,
        )
        project_id = response.json()["id"]

        # Try to get status as second user
        response = await async_client.get(
            f"/api/projects/{project_id}/status",
            headers=second_auth_headers,
        )

        assert response.status_code == 404
