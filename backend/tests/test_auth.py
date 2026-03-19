"""
Tests for authentication endpoints.

Covers: signup, login, token refresh, /me, workspace creation.
All tests use the in-memory SQLite DB via the client fixture.
"""
import uuid
import pytest


@pytest.fixture
def signup_payload():
    """Unique email per test — auth endpoints call db.commit() so data
    persists across tests in StaticPool mode. Unique emails prevent 409s."""
    return {
        "email": f"user_{uuid.uuid4().hex[:8]}@ragops.dev",
        "full_name": "New User",
        "password": "Secure1234",
    }


class TestSignup:

    @pytest.mark.asyncio
    async def test_signup_returns_201_with_tokens(self, client, signup_payload):
        response = await client.post("/api/auth/signup", json=signup_payload)
        assert response.status_code == 201
        data = response.json()
        assert "tokens" in data
        assert "access_token" in data["tokens"]
        assert "refresh_token" in data["tokens"]
        assert data["user"]["email"] == signup_payload["email"]

    @pytest.mark.asyncio
    async def test_signup_duplicate_email_returns_409(self, client, signup_payload):
        await client.post("/api/auth/signup", json=signup_payload)
        response = await client.post("/api/auth/signup", json=signup_payload)
        assert response.status_code == 409
        assert "already exists" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_signup_weak_password_returns_422(self, client, signup_payload):
        payload = {**signup_payload, "password": "weak"}
        response = await client.post("/api/auth/signup", json=payload)
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_signup_invalid_email_returns_422(self, client, signup_payload):
        payload = {**signup_payload, "email": "not-an-email"}
        response = await client.post("/api/auth/signup", json=payload)
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_signup_missing_uppercase_returns_422(self, client, signup_payload):
        payload = {**signup_payload, "password": "nouppercase1"}
        response = await client.post("/api/auth/signup", json=payload)
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_signup_creates_default_workspace(self, client, signup_payload):
        response = await client.post("/api/auth/signup", json=signup_payload)
        assert response.status_code == 201
        # Default workspace is created; user can list workspaces
        token = response.json()["tokens"]["access_token"]
        ws_response = await client.get(
            "/api/auth/workspaces",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert ws_response.status_code == 200
        workspaces = ws_response.json()
        assert len(workspaces) == 1
        assert workspaces[0]["name"] == "My Workspace"


class TestLogin:

    @pytest.mark.asyncio
    async def test_login_valid_credentials_returns_tokens(self, client, signup_payload):
        await client.post("/api/auth/signup", json=signup_payload)
        response = await client.post(
            "/api/auth/login",
            json={
                "email": signup_payload["email"],
                "password": signup_payload["password"],
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"

    @pytest.mark.asyncio
    async def test_login_wrong_password_returns_401(self, client, signup_payload):
        await client.post("/api/auth/signup", json=signup_payload)
        response = await client.post(
            "/api/auth/login",
            json={"email": signup_payload["email"], "password": "WrongPass1"},
        )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_login_unknown_email_returns_401(self, client):
        response = await client.post(
            "/api/auth/login",
            json={"email": "ghost@ragops.dev", "password": "Ghost1234"},
        )
        assert response.status_code == 401


class TestTokenRefresh:

    @pytest.mark.asyncio
    async def test_valid_refresh_token_issues_new_access_token(self, client, signup_payload):
        signup = await client.post("/api/auth/signup", json=signup_payload)
        refresh_token = signup.json()["tokens"]["refresh_token"]

        response = await client.post(
            "/api/auth/refresh",
            json={"refresh_token": refresh_token},
        )
        assert response.status_code == 200
        assert "access_token" in response.json()

    @pytest.mark.asyncio
    async def test_access_token_rejected_as_refresh(self, client, signup_payload):
        signup = await client.post("/api/auth/signup", json=signup_payload)
        access_token = signup.json()["tokens"]["access_token"]

        response = await client.post(
            "/api/auth/refresh",
            json={"refresh_token": access_token},
        )
        assert response.status_code == 400
        assert "refresh token" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_malformed_token_returns_401(self, client):
        response = await client.post(
            "/api/auth/refresh",
            json={"refresh_token": "this.is.not.a.jwt"},
        )
        assert response.status_code == 401


class TestGetMe:

    @pytest.mark.asyncio
    async def test_me_returns_current_user(self, client, signup_payload):
        signup = await client.post("/api/auth/signup", json=signup_payload)
        token = signup.json()["tokens"]["access_token"]

        response = await client.get(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        assert response.json()["email"] == signup_payload["email"]

    @pytest.mark.asyncio
    async def test_me_without_token_returns_403(self, client):
        response = await client.get("/api/auth/me")
        assert response.status_code == 403


class TestWorkspaces:

    @pytest.mark.asyncio
    async def test_create_workspace_returns_201(self, client, signup_payload):
        signup = await client.post("/api/auth/signup", json=signup_payload)
        token = signup.json()["tokens"]["access_token"]

        response = await client.post(
            "/api/auth/workspaces",
            json={"name": "Research Workspace", "description": "For papers"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 201
        assert response.json()["name"] == "Research Workspace"

    @pytest.mark.asyncio
    async def test_workspace_name_required(self, client, signup_payload):
        signup = await client.post("/api/auth/signup", json=signup_payload)
        token = signup.json()["tokens"]["access_token"]

        response = await client.post(
            "/api/auth/workspaces",
            json={"name": ""},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 422
