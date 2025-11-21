"""
Tests for the user profile endpoint.

This endpoint allows fetching user profile information including admin status.
"""
import pytest
from fastapi.testclient import TestClient
from unittest.mock import MagicMock, AsyncMock
from main import app
from api.dependencies import get_supabase_client
from api.rate_limiter import limiter


class MockSupabaseTable:
    """Mock Supabase table for testing."""
    
    def __init__(self, data):
        self.data = data
        
    def select(self, *args, **kwargs):
        return self
    
    def eq(self, *args, **kwargs):
        return self
    
    def is_(self, *args, **kwargs):
        """Support for is_() method used in soft-delete filtering"""
        return self
    
    async def execute(self):
        result = MagicMock()
        result.data = self.data
        return result


class MockSupabase:
    """Mock Supabase client for testing."""
    
    def __init__(self, profile_data):
        self.profile_data = profile_data
    
    def table(self, table_name):
        if table_name == 'profiles':
            return MockSupabaseTable(self.profile_data)
        return MockSupabaseTable([])


@pytest.fixture(autouse=True)
def clear_rate_limits():
    """Clear rate limiter counters before each test."""
    # Clear rate limiter counters to ensure tests don't interfere with each other
    limiter._storage.storage.clear()
    yield
    # Clean up after test
    limiter._storage.storage.clear()


@pytest.fixture
def test_user_id():
    """Valid test UUID."""
    return "550e8400-e29b-41d4-a716-446655440000"


@pytest.fixture
def mock_profile(test_user_id):
    """Mock user profile data."""
    return [{
        "id": test_user_id,
        "email": "test@example.com",
        "is_admin": True,
        "created_at": "2023-01-01T00:00:00Z"
    }]


def test_get_user_profile_success(test_user_id, mock_profile):
    """Test successful profile fetch."""
    # Override dependency
    async def override_get_supabase():
        return MockSupabase(mock_profile)
    
    app.dependency_overrides[get_supabase_client] = override_get_supabase
    
    with TestClient(app) as client:
        response = client.get(f"/user/{test_user_id}/profile")
    
    # Clean up
    app.dependency_overrides.clear()
    
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == test_user_id
    assert data["email"] == "test@example.com"
    assert data["is_admin"] is True
    assert "created_at" in data


def test_get_user_profile_non_admin(test_user_id):
    """Test profile fetch for non-admin user."""
    mock_profile = [{
        "id": test_user_id,
        "email": "regular@example.com",
        "is_admin": False,
        "created_at": "2023-01-01T00:00:00Z"
    }]
    
    # Override dependency
    async def override_get_supabase():
        return MockSupabase(mock_profile)
    
    app.dependency_overrides[get_supabase_client] = override_get_supabase
    
    with TestClient(app) as client:
        response = client.get(f"/user/{test_user_id}/profile")
    
    # Clean up
    app.dependency_overrides.clear()
    
    assert response.status_code == 200
    data = response.json()
    assert data["is_admin"] is False


def test_get_user_profile_not_found(test_user_id):
    """Test profile not found."""
    # Override dependency with empty data
    async def override_get_supabase():
        return MockSupabase([])
    
    app.dependency_overrides[get_supabase_client] = override_get_supabase
    
    with TestClient(app) as client:
        response = client.get(f"/user/{test_user_id}/profile")
    
    # Clean up
    app.dependency_overrides.clear()
    
    assert response.status_code == 404
    data = response.json()
    assert "not found" in data["detail"].lower()


def test_get_user_profile_invalid_uuid():
    """Test invalid UUID validation."""
    # Override dependency to avoid DB connection
    async def override_get_supabase():
        return MockSupabase([])
    
    app.dependency_overrides[get_supabase_client] = override_get_supabase
    
    with TestClient(app) as client:
        response = client.get("/user/invalid-uuid/profile")
    
    # Clean up
    app.dependency_overrides.clear()
    
    assert response.status_code == 400
    data = response.json()
    assert "uuid" in data["detail"].lower() or "invalid" in data["detail"].lower()


def test_get_user_profile_empty_uuid():
    """Test empty UUID validation."""
    # Override dependency to avoid DB connection
    async def override_get_supabase():
        return MockSupabase([])
    
    app.dependency_overrides[get_supabase_client] = override_get_supabase
    
    with TestClient(app) as client:
        response = client.get("/user//profile")
    
    # Clean up
    app.dependency_overrides.clear()
    
    # Should be 404 (route not found) or 400 (validation error)
    assert response.status_code in [404, 422]


def test_get_user_profile_malformed_uuid():
    """Test malformed UUID (correct format but invalid)."""
    malformed_uuid = "00000000-0000-0000-0000-000000000000"
    
    # Override dependency
    async def override_get_supabase():
        return MockSupabase([])
    
    app.dependency_overrides[get_supabase_client] = override_get_supabase
    
    with TestClient(app) as client:
        response = client.get(f"/user/{malformed_uuid}/profile")
    
    # Clean up
    app.dependency_overrides.clear()
    
    # Valid UUID format, just not found
    assert response.status_code == 404


def test_profile_endpoint_no_auth_required(test_user_id, mock_profile):
    """Test that profile endpoint does not require authentication."""
    # Override dependency
    async def override_get_supabase():
        return MockSupabase(mock_profile)
    
    app.dependency_overrides[get_supabase_client] = override_get_supabase
    
    with TestClient(app) as client:
        # Call without any authorization header
        response = client.get(f"/user/{test_user_id}/profile")
    
    # Clean up
    app.dependency_overrides.clear()
    
    # Should succeed without auth
    assert response.status_code == 200
    assert response.json()["id"] == test_user_id


def test_profile_endpoint_returns_expected_fields(test_user_id, mock_profile):
    """Test that profile endpoint returns all expected fields."""
    # Override dependency
    async def override_get_supabase():
        return MockSupabase(mock_profile)
    
    app.dependency_overrides[get_supabase_client] = override_get_supabase
    
    with TestClient(app) as client:
        response = client.get(f"/user/{test_user_id}/profile")
    
    # Clean up
    app.dependency_overrides.clear()
    
    assert response.status_code == 200
    data = response.json()
    
    # Check all expected fields are present
    expected_fields = ["id", "email", "is_admin", "created_at"]
    for field in expected_fields:
        assert field in data, f"Expected field '{field}' not found in response"
