"""
Integration tests for media upload operations.

Tests:
- Upload image (jpg, png)
- Upload video (mp4)
- Upload invalid file type (rejected)
- File size limits
- Media list/reorder
- Media delete
- Thumbnail retrieval
- Path traversal prevention
- Malicious filename handling
"""

import uuid

import pytest
from httpx import AsyncClient


class TestMediaUpload:
    """Tests for media file upload endpoint."""

    @pytest.mark.asyncio
    async def test_upload_jpeg_image(
        self,
        async_client: AsyncClient,
        auth_headers: dict,
        test_project: dict,
        sample_image: bytes,
    ):
        """Test uploading a JPEG image."""
        files = {"files": ("test_image.jpg", sample_image, "image/jpeg")}
        response = await async_client.post(
            f"/api/projects/{test_project['id']}/media",
            files=files,
            headers=auth_headers,
        )

        assert response.status_code == 201
        data = response.json()
        assert data["total_uploaded"] == 1
        assert len(data["uploaded"]) == 1
        assert data["uploaded"][0]["filename"] == "test_image.jpg"
        assert data["uploaded"][0]["media_type"] == "image"
        assert data["uploaded"][0]["processing_status"] == "pending"
        assert len(data["failed"]) == 0

    @pytest.mark.asyncio
    async def test_upload_png_image(
        self,
        async_client: AsyncClient,
        auth_headers: dict,
        test_project: dict,
        sample_png: bytes,
    ):
        """Test uploading a PNG image."""
        files = {"files": ("test_image.png", sample_png, "image/png")}
        response = await async_client.post(
            f"/api/projects/{test_project['id']}/media",
            files=files,
            headers=auth_headers,
        )

        assert response.status_code == 201
        data = response.json()
        assert data["total_uploaded"] == 1
        assert data["uploaded"][0]["media_type"] == "image"

    @pytest.mark.asyncio
    async def test_upload_mp4_video(
        self,
        async_client: AsyncClient,
        auth_headers: dict,
        test_project: dict,
        sample_video_mp4: bytes,
    ):
        """Test uploading an MP4 video."""
        files = {"files": ("test_video.mp4", sample_video_mp4, "video/mp4")}
        response = await async_client.post(
            f"/api/projects/{test_project['id']}/media",
            files=files,
            headers=auth_headers,
        )

        assert response.status_code == 201
        data = response.json()
        assert data["total_uploaded"] == 1
        assert data["uploaded"][0]["media_type"] == "video"

    @pytest.mark.asyncio
    async def test_upload_multiple_files(
        self,
        async_client: AsyncClient,
        auth_headers: dict,
        test_project: dict,
        sample_image: bytes,
        sample_png: bytes,
    ):
        """Test uploading multiple files at once."""
        files = [
            ("files", ("image1.jpg", sample_image, "image/jpeg")),
            ("files", ("image2.png", sample_png, "image/png")),
        ]
        response = await async_client.post(
            f"/api/projects/{test_project['id']}/media",
            files=files,
            headers=auth_headers,
        )

        assert response.status_code == 201
        data = response.json()
        assert data["total_uploaded"] == 2
        assert len(data["uploaded"]) == 2

    @pytest.mark.asyncio
    async def test_upload_invalid_file_type(
        self,
        async_client: AsyncClient,
        auth_headers: dict,
        test_project: dict,
        invalid_file: bytes,
    ):
        """Test that invalid file types are rejected."""
        files = {"files": ("script.exe", invalid_file, "application/octet-stream")}
        response = await async_client.post(
            f"/api/projects/{test_project['id']}/media",
            files=files,
            headers=auth_headers,
        )

        assert response.status_code == 201  # Partial success is still 201
        data = response.json()
        assert data["total_uploaded"] == 0
        assert len(data["failed"]) == 1
        assert "Invalid file type" in data["failed"][0]["error"]

    @pytest.mark.asyncio
    async def test_upload_mixed_valid_invalid(
        self,
        async_client: AsyncClient,
        auth_headers: dict,
        test_project: dict,
        sample_image: bytes,
        invalid_file: bytes,
    ):
        """Test uploading mix of valid and invalid files."""
        files = [
            ("files", ("valid.jpg", sample_image, "image/jpeg")),
            ("files", ("invalid.exe", invalid_file, "application/octet-stream")),
        ]
        response = await async_client.post(
            f"/api/projects/{test_project['id']}/media",
            files=files,
            headers=auth_headers,
        )

        assert response.status_code == 201
        data = response.json()
        assert data["total_uploaded"] == 1
        assert len(data["uploaded"]) == 1
        assert len(data["failed"]) == 1

    @pytest.mark.asyncio
    async def test_upload_empty_file(
        self,
        async_client: AsyncClient,
        auth_headers: dict,
        test_project: dict,
    ):
        """Test that empty files are rejected."""
        files = {"files": ("empty.jpg", b"", "image/jpeg")}
        response = await async_client.post(
            f"/api/projects/{test_project['id']}/media",
            files=files,
            headers=auth_headers,
        )

        assert response.status_code == 201
        data = response.json()
        assert data["total_uploaded"] == 0
        assert len(data["failed"]) == 1
        assert "empty" in data["failed"][0]["error"].lower()

    @pytest.mark.asyncio
    async def test_upload_to_nonexistent_project(
        self,
        async_client: AsyncClient,
        auth_headers: dict,
        sample_image: bytes,
    ):
        """Test uploading to a non-existent project."""
        fake_id = str(uuid.uuid4())
        files = {"files": ("test.jpg", sample_image, "image/jpeg")}
        response = await async_client.post(
            f"/api/projects/{fake_id}/media",
            files=files,
            headers=auth_headers,
        )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_upload_to_other_user_project(
        self,
        async_client: AsyncClient,
        auth_headers: dict,
        second_auth_headers: dict,
        sample_image: bytes,
    ):
        """Test that users cannot upload to other users' projects."""
        # Create project as first user
        response = await async_client.post(
            "/api/projects",
            json={"name": "Protected Project"},
            headers=auth_headers,
        )
        project_id = response.json()["id"]

        # Try to upload as second user
        files = {"files": ("hack.jpg", sample_image, "image/jpeg")}
        response = await async_client.post(
            f"/api/projects/{project_id}/media",
            files=files,
            headers=second_auth_headers,
        )

        assert response.status_code == 404


class TestPathTraversalPrevention:
    """Tests for path traversal attack prevention."""

    @pytest.mark.asyncio
    async def test_path_traversal_in_filename(
        self,
        async_client: AsyncClient,
        auth_headers: dict,
        test_project: dict,
        sample_image: bytes,
    ):
        """Test that path traversal in filename is sanitized."""
        files = {"files": ("../../../etc/passwd.jpg", sample_image, "image/jpeg")}
        response = await async_client.post(
            f"/api/projects/{test_project['id']}/media",
            files=files,
            headers=auth_headers,
        )

        assert response.status_code == 201
        data = response.json()
        # File should be accepted but filename should be sanitized
        if data["total_uploaded"] > 0:
            # The filename should not contain path traversal characters
            filename = data["uploaded"][0]["filename"]
            assert ".." not in filename
            assert "/" not in filename
            assert "\\" not in filename

    @pytest.mark.asyncio
    async def test_null_byte_in_filename(
        self,
        async_client: AsyncClient,
        auth_headers: dict,
        test_project: dict,
        sample_image: bytes,
    ):
        """Test that null bytes in filename are sanitized."""
        files = {"files": ("test\x00.jpg.exe", sample_image, "image/jpeg")}
        response = await async_client.post(
            f"/api/projects/{test_project['id']}/media",
            files=files,
            headers=auth_headers,
        )

        assert response.status_code == 201
        data = response.json()
        if data["total_uploaded"] > 0:
            filename = data["uploaded"][0]["filename"]
            assert "\x00" not in filename

    @pytest.mark.asyncio
    async def test_special_characters_in_filename(
        self,
        async_client: AsyncClient,
        auth_headers: dict,
        test_project: dict,
        sample_image: bytes,
    ):
        """Test that special characters in filename are handled."""
        files = {"files": ("test<>:\"|?*.jpg", sample_image, "image/jpeg")}
        response = await async_client.post(
            f"/api/projects/{test_project['id']}/media",
            files=files,
            headers=auth_headers,
        )

        assert response.status_code == 201
        data = response.json()
        if data["total_uploaded"] > 0:
            filename = data["uploaded"][0]["filename"]
            # Problematic characters should be removed
            for char in '<>:"|?*':
                assert char not in filename


class TestMediaDetails:
    """Tests for getting media asset details."""

    @pytest.mark.asyncio
    async def test_get_media_details(
        self,
        async_client: AsyncClient,
        auth_headers: dict,
        test_project: dict,
        sample_image: bytes,
    ):
        """Test getting details of an uploaded media asset."""
        # Upload media first
        files = {"files": ("test.jpg", sample_image, "image/jpeg")}
        response = await async_client.post(
            f"/api/projects/{test_project['id']}/media",
            files=files,
            headers=auth_headers,
        )
        assert response.status_code == 201
        media_id = response.json()["uploaded"][0]["id"]

        # Get details
        response = await async_client.get(
            f"/api/media/{media_id}",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == media_id
        assert data["project_id"] == test_project["id"]
        assert data["filename"] == "test.jpg"
        assert data["media_type"] == "image"
        assert "processing_status" in data
        assert "file_size" in data
        assert "sort_order" in data

    @pytest.mark.asyncio
    async def test_get_media_not_found(
        self,
        async_client: AsyncClient,
        auth_headers: dict,
    ):
        """Test getting non-existent media asset."""
        fake_id = str(uuid.uuid4())
        response = await async_client.get(
            f"/api/media/{fake_id}",
            headers=auth_headers,
        )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_get_other_user_media(
        self,
        async_client: AsyncClient,
        auth_headers: dict,
        second_auth_headers: dict,
        sample_image: bytes,
    ):
        """Test that users cannot access other users' media."""
        # Create project and upload as first user
        response = await async_client.post(
            "/api/projects",
            json={"name": "Private Project"},
            headers=auth_headers,
        )
        project_id = response.json()["id"]

        files = {"files": ("private.jpg", sample_image, "image/jpeg")}
        response = await async_client.post(
            f"/api/projects/{project_id}/media",
            files=files,
            headers=auth_headers,
        )
        media_id = response.json()["uploaded"][0]["id"]

        # Try to access as second user
        response = await async_client.get(
            f"/api/media/{media_id}",
            headers=second_auth_headers,
        )

        assert response.status_code == 404


class TestMediaDelete:
    """Tests for media deletion."""

    @pytest.mark.asyncio
    async def test_delete_media_success(
        self,
        async_client: AsyncClient,
        auth_headers: dict,
        test_project: dict,
        sample_image: bytes,
    ):
        """Test successful media deletion."""
        # Upload media
        files = {"files": ("to_delete.jpg", sample_image, "image/jpeg")}
        response = await async_client.post(
            f"/api/projects/{test_project['id']}/media",
            files=files,
            headers=auth_headers,
        )
        media_id = response.json()["uploaded"][0]["id"]

        # Delete it
        response = await async_client.delete(
            f"/api/media/{media_id}",
            headers=auth_headers,
        )

        assert response.status_code == 204

        # Verify it's gone
        response = await async_client.get(
            f"/api/media/{media_id}",
            headers=auth_headers,
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_media_not_found(
        self,
        async_client: AsyncClient,
        auth_headers: dict,
    ):
        """Test deleting non-existent media."""
        fake_id = str(uuid.uuid4())
        response = await async_client.delete(
            f"/api/media/{fake_id}",
            headers=auth_headers,
        )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_other_user_media(
        self,
        async_client: AsyncClient,
        auth_headers: dict,
        second_auth_headers: dict,
        sample_image: bytes,
    ):
        """Test that users cannot delete other users' media."""
        # Create project and upload as first user
        response = await async_client.post(
            "/api/projects",
            json={"name": "Private Project"},
            headers=auth_headers,
        )
        project_id = response.json()["id"]

        files = {"files": ("cannot_delete.jpg", sample_image, "image/jpeg")}
        response = await async_client.post(
            f"/api/projects/{project_id}/media",
            files=files,
            headers=auth_headers,
        )
        media_id = response.json()["uploaded"][0]["id"]

        # Try to delete as second user
        response = await async_client.delete(
            f"/api/media/{media_id}",
            headers=second_auth_headers,
        )

        assert response.status_code == 404

        # Verify it still exists
        response = await async_client.get(
            f"/api/media/{media_id}",
            headers=auth_headers,
        )
        assert response.status_code == 200


class TestMediaReorder:
    """Tests for media reordering."""

    @pytest.mark.asyncio
    async def test_reorder_media_success(
        self,
        async_client: AsyncClient,
        auth_headers: dict,
        test_project: dict,
        sample_image: bytes,
        sample_png: bytes,
    ):
        """Test successful media reordering."""
        # Upload multiple media files
        files = [
            ("files", ("image1.jpg", sample_image, "image/jpeg")),
            ("files", ("image2.png", sample_png, "image/png")),
        ]
        response = await async_client.post(
            f"/api/projects/{test_project['id']}/media",
            files=files,
            headers=auth_headers,
        )
        assert response.status_code == 201

        media_ids = [item["id"] for item in response.json()["uploaded"]]

        # Reorder (reverse the order)
        new_order = list(reversed(media_ids))
        response = await async_client.post(
            f"/api/projects/{test_project['id']}/media/reorder",
            json={"order": new_order},
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["timeline_invalidated"] is True

        # Verify new order
        for i, item in enumerate(data["new_order"]):
            assert item["id"] == new_order[i]
            assert item["sort_order"] == i

    @pytest.mark.asyncio
    async def test_reorder_invalid_media_id(
        self,
        async_client: AsyncClient,
        auth_headers: dict,
        test_project: dict,
        sample_image: bytes,
    ):
        """Test reordering with invalid media ID."""
        # Upload media
        files = {"files": ("test.jpg", sample_image, "image/jpeg")}
        response = await async_client.post(
            f"/api/projects/{test_project['id']}/media",
            files=files,
            headers=auth_headers,
        )
        valid_id = response.json()["uploaded"][0]["id"]

        # Try to reorder with fake ID
        fake_id = str(uuid.uuid4())
        response = await async_client.post(
            f"/api/projects/{test_project['id']}/media/reorder",
            json={"order": [valid_id, fake_id]},
            headers=auth_headers,
        )

        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_reorder_other_user_project(
        self,
        async_client: AsyncClient,
        auth_headers: dict,
        second_auth_headers: dict,
        sample_image: bytes,
    ):
        """Test that users cannot reorder media in other users' projects."""
        # Create project and upload as first user
        response = await async_client.post(
            "/api/projects",
            json={"name": "Private Project"},
            headers=auth_headers,
        )
        project_id = response.json()["id"]

        files = {"files": ("test.jpg", sample_image, "image/jpeg")}
        response = await async_client.post(
            f"/api/projects/{project_id}/media",
            files=files,
            headers=auth_headers,
        )
        media_id = response.json()["uploaded"][0]["id"]

        # Try to reorder as second user
        response = await async_client.post(
            f"/api/projects/{project_id}/media/reorder",
            json={"order": [media_id]},
            headers=second_auth_headers,
        )

        assert response.status_code == 404


class TestThumbnail:
    """Tests for thumbnail retrieval."""

    @pytest.mark.asyncio
    async def test_get_thumbnail_not_ready(
        self,
        async_client: AsyncClient,
        auth_headers: dict,
        test_project: dict,
        sample_image: bytes,
    ):
        """Test getting thumbnail before processing is complete."""
        # Upload media
        files = {"files": ("test.jpg", sample_image, "image/jpeg")}
        response = await async_client.post(
            f"/api/projects/{test_project['id']}/media",
            files=files,
            headers=auth_headers,
        )
        media_id = response.json()["uploaded"][0]["id"]

        # Try to get thumbnail (should fail as not processed yet)
        response = await async_client.get(
            f"/api/media/{media_id}/thumbnail",
            headers=auth_headers,
        )

        # Should return 404 since thumbnail not yet generated
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_get_thumbnail_not_found(
        self,
        async_client: AsyncClient,
        auth_headers: dict,
    ):
        """Test getting thumbnail for non-existent media."""
        fake_id = str(uuid.uuid4())
        response = await async_client.get(
            f"/api/media/{fake_id}/thumbnail",
            headers=auth_headers,
        )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_get_thumbnail_other_user(
        self,
        async_client: AsyncClient,
        auth_headers: dict,
        second_auth_headers: dict,
        sample_image: bytes,
    ):
        """Test that users cannot access other users' thumbnails."""
        # Create project and upload as first user
        response = await async_client.post(
            "/api/projects",
            json={"name": "Private Project"},
            headers=auth_headers,
        )
        project_id = response.json()["id"]

        files = {"files": ("private.jpg", sample_image, "image/jpeg")}
        response = await async_client.post(
            f"/api/projects/{project_id}/media",
            files=files,
            headers=auth_headers,
        )
        media_id = response.json()["uploaded"][0]["id"]

        # Try to access thumbnail as second user
        response = await async_client.get(
            f"/api/media/{media_id}/thumbnail",
            headers=second_auth_headers,
        )

        assert response.status_code == 404
