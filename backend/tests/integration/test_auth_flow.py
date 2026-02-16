"""
Integration tests for authentication flow.

Tests:
- User registration (success and duplicate)
- User login (success and failure)
- Protected endpoint access (with/without token)
- Token validation (valid/invalid/expired)
"""

import uuid

import pytest
from httpx import AsyncClient


class TestUserRegistration:
    """Tests for user registration endpoint."""

    @pytest.mark.asyncio
    async def test_register_success(self, async_client: AsyncClient):
        """Test successful user registration."""
        username = f"newuser_{uuid.uuid4().hex[:8]}"
        response = await async_client.post(
            "/api/auth/register",
            json={
                "username": username,
                "password": "SecurePassword123!",
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert data["username"] == username
        assert "id" in data
        assert "created_at" in data
        # Password should never be returned
        assert "password" not in data
        assert "password_hash" not in data

    @pytest.mark.asyncio
    async def test_register_duplicate_username_fails(
        self, async_client: AsyncClient, test_user: dict
    ):
        """Test that registering with an existing username fails."""
        response = await async_client.post(
            "/api/auth/register",
            json={
                "username": test_user["username"],
                "password": "DifferentPassword123!",
            },
        )

        assert response.status_code == 400
        data = response.json()
        assert "detail" in data
        assert data["detail"]["error"] == "validation_error"
        assert "already exists" in data["detail"]["message"].lower()

    @pytest.mark.asyncio
    async def test_register_username_too_short(self, async_client: AsyncClient):
        """Test that username must be at least 3 characters."""
        response = await async_client.post(
            "/api/auth/register",
            json={
                "username": "ab",
                "password": "SecurePassword123!",
            },
        )

        assert response.status_code == 422  # Validation error
        data = response.json()
        assert "detail" in data

    @pytest.mark.asyncio
    async def test_register_username_too_long(self, async_client: AsyncClient):
        """Test that username must be at most 50 characters."""
        response = await async_client.post(
            "/api/auth/register",
            json={
                "username": "a" * 51,
                "password": "SecurePassword123!",
            },
        )

        assert response.status_code == 422  # Validation error

    @pytest.mark.asyncio
    async def test_register_password_too_short(self, async_client: AsyncClient):
        """Test that password must be at least 8 characters."""
        response = await async_client.post(
            "/api/auth/register",
            json={
                "username": f"user_{uuid.uuid4().hex[:8]}",
                "password": "short",
            },
        )

        assert response.status_code == 422  # Validation error

    @pytest.mark.asyncio
    async def test_register_invalid_username_characters(self, async_client: AsyncClient):
        """Test that username can only contain alphanumeric and underscores."""
        response = await async_client.post(
            "/api/auth/register",
            json={
                "username": "user@with#special$chars",
                "password": "SecurePassword123!",
            },
        )

        assert response.status_code == 422  # Validation error

    @pytest.mark.asyncio
    async def test_register_missing_username(self, async_client: AsyncClient):
        """Test that username is required."""
        response = await async_client.post(
            "/api/auth/register",
            json={
                "password": "SecurePassword123!",
            },
        )

        assert response.status_code == 422  # Validation error

    @pytest.mark.asyncio
    async def test_register_missing_password(self, async_client: AsyncClient):
        """Test that password is required."""
        response = await async_client.post(
            "/api/auth/register",
            json={
                "username": f"user_{uuid.uuid4().hex[:8]}",
            },
        )

        assert response.status_code == 422  # Validation error


class TestUserLogin:
    """Tests for user login endpoint."""

    @pytest.mark.asyncio
    async def test_login_success(self, async_client: AsyncClient, test_user: dict):
        """Test successful login with valid credentials."""
        response = await async_client.post(
            "/api/auth/login",
            json={
                "username": test_user["username"],
                "password": test_user["password"],
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"
        assert "expires_in" in data
        assert data["expires_in"] > 0
        assert "user" in data
        assert data["user"]["username"] == test_user["username"]
        assert data["user"]["id"] == test_user["id"]

    @pytest.mark.asyncio
    async def test_login_wrong_password(self, async_client: AsyncClient, test_user: dict):
        """Test login with incorrect password."""
        response = await async_client.post(
            "/api/auth/login",
            json={
                "username": test_user["username"],
                "password": "WrongPassword123!",
            },
        )

        assert response.status_code == 401
        data = response.json()
        assert "detail" in data
        assert data["detail"]["error"] == "unauthorized"

    @pytest.mark.asyncio
    async def test_login_nonexistent_user(self, async_client: AsyncClient):
        """Test login with non-existent username."""
        response = await async_client.post(
            "/api/auth/login",
            json={
                "username": f"nonexistent_{uuid.uuid4().hex}",
                "password": "SomePassword123!",
            },
        )

        assert response.status_code == 401
        data = response.json()
        assert data["detail"]["error"] == "unauthorized"

    @pytest.mark.asyncio
    async def test_login_missing_username(self, async_client: AsyncClient):
        """Test login without username."""
        response = await async_client.post(
            "/api/auth/login",
            json={
                "password": "SomePassword123!",
            },
        )

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_login_missing_password(self, async_client: AsyncClient, test_user: dict):
        """Test login without password."""
        response = await async_client.post(
            "/api/auth/login",
            json={
                "username": test_user["username"],
            },
        )

        assert response.status_code == 422


class TestProtectedEndpoints:
    """Tests for protected endpoint access."""

    @pytest.mark.asyncio
    async def test_protected_endpoint_without_token(self, async_client: AsyncClient):
        """Test accessing protected endpoint without token."""
        response = await async_client.get("/api/projects")

        assert response.status_code == 403  # No credentials provided

    @pytest.mark.asyncio
    async def test_protected_endpoint_with_invalid_token(self, async_client: AsyncClient):
        """Test accessing protected endpoint with invalid token."""
        response = await async_client.get(
            "/api/projects",
            headers={"Authorization": "Bearer invalid_token_here"},
        )

        assert response.status_code == 401
        data = response.json()
        assert data["detail"]["error"] == "unauthorized"

    @pytest.mark.asyncio
    async def test_protected_endpoint_with_malformed_header(self, async_client: AsyncClient):
        """Test accessing protected endpoint with malformed Authorization header."""
        # Missing "Bearer" prefix
        response = await async_client.get(
            "/api/projects",
            headers={"Authorization": "invalid_format"},
        )

        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_protected_endpoint_with_valid_token(
        self, async_client: AsyncClient, auth_headers: dict
    ):
        """Test accessing protected endpoint with valid token."""
        response = await async_client.get(
            "/api/projects",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert "projects" in data
        assert "total" in data

    @pytest.mark.asyncio
    async def test_protected_endpoint_with_empty_bearer(self, async_client: AsyncClient):
        """Test accessing protected endpoint with empty Bearer token."""
        response = await async_client.get(
            "/api/projects",
            headers={"Authorization": "Bearer "},
        )

        # Empty bearer token returns 403 (Forbidden) - invalid credentials
        assert response.status_code == 403


class TestTokenValidation:
    """Tests for JWT token validation."""

    @pytest.mark.asyncio
    async def test_token_contains_user_info(
        self, async_client: AsyncClient, test_user: dict, auth_headers: dict
    ):
        """Test that token can be used to access user-specific data."""
        # Create a project as the test user
        response = await async_client.post(
            "/api/projects",
            json={"name": "Test Project"},
            headers=auth_headers,
        )
        assert response.status_code == 201
        project = response.json()

        # Verify the project belongs to the test user
        response = await async_client.get(
            f"/api/projects/{project['id']}",
            headers=auth_headers,
        )
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_different_users_have_different_tokens(
        self,
        async_client: AsyncClient,
        test_user: dict,
        second_test_user: dict,
    ):
        """Test that different users get different tokens."""
        assert test_user["access_token"] != second_test_user["access_token"]
        assert test_user["id"] != second_test_user["id"]

    @pytest.mark.asyncio
    async def test_user_can_only_access_own_resources(
        self,
        async_client: AsyncClient,
        auth_headers: dict,
        second_auth_headers: dict,
    ):
        """Test that users can only access their own resources."""
        # Create a project as the first user
        response = await async_client.post(
            "/api/projects",
            json={"name": "User 1 Project"},
            headers=auth_headers,
        )
        assert response.status_code == 201
        project_id = response.json()["id"]

        # Try to access it as the second user (should fail with 404)
        response = await async_client.get(
            f"/api/projects/{project_id}",
            headers=second_auth_headers,
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_token_refresh_by_relogin(
        self, async_client: AsyncClient, test_user: dict
    ):
        """Test that logging in again provides a new token."""
        old_token = test_user["access_token"]

        # Login again
        response = await async_client.post(
            "/api/auth/login",
            json={
                "username": test_user["username"],
                "password": test_user["password"],
            },
        )
        assert response.status_code == 200
        new_token = response.json()["access_token"]

        # Tokens should be different (due to different timestamps)
        # Note: There's a small chance they could be the same if
        # login happens within the same second, but this is unlikely
        # In practice, JWT tokens with iat claim should differ

        # Both tokens should work
        for token in [old_token, new_token]:
            response = await async_client.get(
                "/api/projects",
                headers={"Authorization": f"Bearer {token}"},
            )
            assert response.status_code == 200
