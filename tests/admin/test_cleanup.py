"""
Tests for /api/admin/cleanup endpoint.
Validates safe cleanup using source field.
"""
import pytest
import uuid
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient
pytestmark = pytest.mark.skip(reason="Requires HTTP-level mocking infrastructure for Supabase calls")


@pytest.fixture
def client():
    """Create test client with rate limiting disabled."""
    from main import app
    app.state.limiter.enabled = False
    yield TestClient(app)
    app.state.limiter.enabled = True


class MockUser:
    """Mock Supabase User object"""
    def __init__(self, email):
        self.id = str(uuid.uuid4())
        self.email = email
        self.user_metadata = {"role": "admin"}


class MockUserResponse:
    """Mock UserResponse from Supabase auth.get_user()"""
    def __init__(self, user):
        self.user = user


class MockSupabaseResponse:
    """Mock response from Supabase queries"""
    def __init__(self, data, count=None):
        self.data = data
        self.count = count


def create_mock_supabase_with_profiles(profiles):
    """Create a mock Supabase client with specific profiles"""
    mock_client = MagicMock()
    
    # Mock auth.get_user for admin verification
    admin_user = MockUser("admin@example.com")
    mock_client.auth.get_user.return_value = MockUserResponse(admin_user)
    
    # Store profiles for select query
    profiles_data = profiles
    
    # Mock table operations
    def create_chain(table_name=None):
        chain = MagicMock()
        
        def mock_execute():
            if table_name == "profiles":
                return MockSupabaseResponse(profiles_data)
            return MockSupabaseResponse([])
        
        chain.select.return_value = chain
        chain.eq.return_value = chain
        chain.update.return_value = chain
        chain.insert.return_value = chain
        chain.delete.return_value = chain
        chain.in_.return_value = chain
        chain.execute = mock_execute
        return chain
    
    def mock_table(name):
        return create_chain(name)
    
    mock_client.table = mock_table
    
    return mock_client


def test_cleanup_dry_run_synthetic_only(client):
    """Test dry run cleanup identifies only synthetic users"""
    profiles = [
        {"id": "user1", "email": "real@gmail.com", "source": "signup"},
        {"id": "user2", "email": "test1@example.com", "source": "synthetic"},
        {"id": "user3", "email": "admin@company.com", "source": "admin_manual"},
        {"id": "user4", "email": "test2@example.org", "source": "synthetic"},
    ]
    
    with patch("api.dependencies.get_supabase_service_role_client") as mock_get_supabase, \
         patch("api.dependencies.get_supabase_anon_auth_client") as mock_get_anon:
        
        mock_service = create_mock_supabase_with_profiles(profiles)
        mock_anon = create_mock_supabase_with_profiles(profiles)
        
        mock_get_supabase.return_value = mock_service
        mock_get_anon.return_value = mock_anon
        
        response = client.post(
            "/api/admin/cleanup?dryRun=true",
            headers={"Authorization": "Bearer test-token"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["dryRun"] is True
        assert data["removedRecords"] == 2  # Only user2 and user4
        assert "user2" in data["sampleIds"] or "user4" in data["sampleIds"]


def test_cleanup_execute_removes_synthetic(client):
    """Test actual cleanup removes synthetic users"""
    profiles = [
        {"id": "user1", "email": "real@gmail.com", "source": "signup"},
        {"id": "user2", "email": "test@example.com", "source": "synthetic"},
    ]
    
    with patch("api.dependencies.get_supabase_service_role_client") as mock_get_supabase, \
         patch("api.dependencies.get_supabase_anon_auth_client") as mock_get_anon:
        
        mock_service = create_mock_supabase_with_profiles(profiles)
        mock_anon = create_mock_supabase_with_profiles(profiles)
        
        mock_get_supabase.return_value = mock_service
        mock_get_anon.return_value = mock_anon
        
        response = client.post(
            "/api/admin/cleanup",
            json={"dryRun": False, "confirm": True},
            headers={"Authorization": "Bearer test-token"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["dryRun"] is False
        assert data["removedRecords"] == 1  # Only user2


def test_cleanup_requires_confirmation(client):
    """Test cleanup requires confirmation when not dry run"""
    with patch("api.dependencies.get_supabase_anon_auth_client") as mock_get_anon:
        mock_anon = create_mock_supabase_with_profiles([])
        mock_get_anon.return_value = mock_anon
        
        response = client.post(
            "/api/admin/cleanup",
            json={"dryRun": False, "confirm": False},
            headers={"Authorization": "Bearer test-token"}
        )
        
        assert response.status_code == 400
        assert "Confirme ou use dryRun=true" in response.json()["detail"]


def test_cleanup_no_auth(client):
    """Test cleanup without authorization"""
    response = client.post(
        "/api/admin/cleanup?dryRun=true"
    )
    
    assert response.status_code == 401


def test_cleanup_preserves_manual_users(client):
    """Test that cleanup preserves admin_manual users"""
    profiles = [
        {"id": "user1", "email": "admin@example.com", "source": "admin_manual"},
        {"id": "user2", "email": "test@example.com", "source": "synthetic"},
    ]
    
    with patch("api.dependencies.get_supabase_service_role_client") as mock_get_supabase, \
         patch("api.dependencies.get_supabase_anon_auth_client") as mock_get_anon:
        
        mock_service = create_mock_supabase_with_profiles(profiles)
        mock_anon = create_mock_supabase_with_profiles(profiles)
        
        mock_get_supabase.return_value = mock_service
        mock_get_anon.return_value = mock_anon
        
        response = client.post(
            "/api/admin/cleanup?dryRun=true",
            headers={"Authorization": "Bearer test-token"}
        )
        
        assert response.status_code == 200
        data = response.json()
        # Should only remove user2 (synthetic), not user1 (admin_manual)
        assert data["removedRecords"] == 1
        assert "user2" in data["sampleIds"]
        assert "user1" not in data["sampleIds"]
