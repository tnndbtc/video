"""
Integration tests for AI Planner API endpoints.

Tests:
- POST /api/ai/plan
- POST /api/ai/apply
- POST /api/ai/plan_and_apply
"""

import pytest
from httpx import AsyncClient

from tests.conftest import create_media_asset_directly


class TestAiPlan:
    """Tests for POST /api/ai/plan"""

    @pytest.mark.asyncio
    async def test_ai_plan_requires_auth(self, async_client: AsyncClient):
        response = await async_client.post(
            "/api/ai/plan",
            json={
                "project_id": "fake-id",
                "prompt": "Make a video",
            },
        )
        assert response.status_code in (401, 403)

    @pytest.mark.asyncio
    async def test_ai_plan_project_not_found(
        self, async_client: AsyncClient, auth_headers: dict
    ):
        response = await async_client.post(
            "/api/ai/plan",
            headers=auth_headers,
            json={
                "project_id": "nonexistent-project-id",
                "prompt": "Make a video",
            },
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_ai_plan_stub(
        self,
        async_client: AsyncClient,
        auth_headers: dict,
        test_project: dict,
        test_db,
    ):
        """Test stub planner generates a valid plan."""
        # Create 2 image media assets with processing_status="ready"
        # Need to get the project object for create_media_asset_directly
        from app.models.project import Project
        from sqlalchemy import select

        query = select(Project).where(Project.id == test_project["id"])
        result = await test_db.execute(query)
        project = result.scalar_one()

        asset1 = await create_media_asset_directly(
            test_db, project, media_type="image", processing_status="ready"
        )
        asset2 = await create_media_asset_directly(
            test_db, project, media_type="image", processing_status="ready"
        )
        await test_db.commit()

        response = await async_client.post(
            "/api/ai/plan",
            headers=auth_headers,
            json={
                "project_id": test_project["id"],
                "prompt": "Make a nice video",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert "edit_plan" in data
        assert data["edit_plan"]["plan_version"] == "v1"
        assert len(data["edit_plan"]["timeline"]["segments"]) == 2
        # Stub should have warning about OPENAI_API_KEY
        assert any(
            "stub" in w.lower() or "openai" in w.lower()
            for w in data.get("warnings", [])
        )

    @pytest.mark.asyncio
    async def test_ai_plan_no_assets_returns_400(
        self,
        async_client: AsyncClient,
        auth_headers: dict,
        test_project: dict,
    ):
        """Test that plan generation fails when no ready assets exist."""
        response = await async_client.post(
            "/api/ai/plan",
            headers=auth_headers,
            json={
                "project_id": test_project["id"],
                "prompt": "Make a video",
            },
        )
        assert response.status_code == 400


class TestAiApply:
    """Tests for POST /api/ai/apply"""

    @pytest.mark.asyncio
    async def test_ai_apply_requires_auth(self, async_client: AsyncClient):
        response = await async_client.post(
            "/api/ai/apply",
            json={
                "project_id": "fake-id",
                "edit_plan": {},
            },
        )
        assert response.status_code in (401, 403)

    @pytest.mark.asyncio
    async def test_ai_apply_saves_edit_request(
        self,
        async_client: AsyncClient,
        auth_headers: dict,
        test_project: dict,
        test_db,
    ):
        """Test that apply converts plan and saves edit_request.json."""
        from app.models.project import Project
        from sqlalchemy import select

        query = select(Project).where(Project.id == test_project["id"])
        result = await test_db.execute(query)
        project = result.scalar_one()

        asset1 = await create_media_asset_directly(
            test_db, project, media_type="image", processing_status="ready"
        )
        asset2 = await create_media_asset_directly(
            test_db, project, media_type="image", processing_status="ready"
        )
        await test_db.commit()

        edit_plan = {
            "plan_version": "v1",
            "mode": "no_audio",
            "project_id": test_project["id"],
            "project_settings": {
                "transition_type": "cut",
                "transition_duration_ms": 0,
            },
            "timeline": {
                "total_duration_ms": 4000,
                "segments": [
                    {
                        "index": 0,
                        "media_asset_id": asset1.id,
                        "media_type": "image",
                        "render_duration_ms": 2000,
                        "source_in_ms": 0,
                        "source_out_ms": 2000,
                    },
                    {
                        "index": 1,
                        "media_asset_id": asset2.id,
                        "media_type": "image",
                        "render_duration_ms": 2000,
                        "source_in_ms": 0,
                        "source_out_ms": 2000,
                    },
                ],
            },
        }

        response = await async_client.post(
            "/api/ai/apply",
            headers=auth_headers,
            json={
                "project_id": test_project["id"],
                "edit_plan": edit_plan,
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True
        assert "edl_hash" in data
        assert data["segment_count"] == 2
        assert data["total_duration_ms"] == 4000

    @pytest.mark.asyncio
    async def test_ai_apply_validation_failure(
        self,
        async_client: AsyncClient,
        auth_headers: dict,
        test_project: dict,
    ):
        """Test that apply fails with invalid plan."""
        edit_plan = {
            "plan_version": "v1",
            "project_id": test_project["id"],
            "timeline": {
                "total_duration_ms": 2000,
                "segments": [
                    {
                        "index": 0,
                        "media_asset_id": "nonexistent-asset",
                        "media_type": "image",
                        "render_duration_ms": 2000,
                        "source_in_ms": 0,
                        "source_out_ms": 2000,
                    },
                ],
            },
        }

        response = await async_client.post(
            "/api/ai/apply",
            headers=auth_headers,
            json={
                "project_id": test_project["id"],
                "edit_plan": edit_plan,
            },
        )
        assert response.status_code == 400


class TestAiPlanAndApply:
    """Tests for POST /api/ai/plan_and_apply"""

    @pytest.mark.asyncio
    async def test_ai_plan_and_apply(
        self,
        async_client: AsyncClient,
        auth_headers: dict,
        test_project: dict,
        test_db,
    ):
        """Test combined plan + apply endpoint."""
        from app.models.project import Project
        from sqlalchemy import select

        query = select(Project).where(Project.id == test_project["id"])
        result = await test_db.execute(query)
        project = result.scalar_one()

        await create_media_asset_directly(
            test_db, project, media_type="image", processing_status="ready"
        )
        await create_media_asset_directly(
            test_db, project, media_type="image", processing_status="ready"
        )
        await test_db.commit()

        response = await async_client.post(
            "/api/ai/plan_and_apply",
            headers=auth_headers,
            json={
                "project_id": test_project["id"],
                "prompt": "Quick montage",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True
        assert "edit_plan" in data
        assert "edl_hash" in data
        assert data["segment_count"] == 2
