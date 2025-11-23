"""
Tests for admin user CRUD endpoints:
- GET /api/admin/users/{user_id}
- PATCH /api/admin/users/{user_id}
- DELETE /api/admin/users/{user_id}
"""
import pytest
import uuid
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    """Create test client with rate limiting disabled."""
    from main import app
    app.state.limiter.enabled = False
    yield TestClient(app)
    app.state.limiter.enabled = True


class MockUser:
    """Mock Supabase User object"""
    def __init__(self, email, user_id=None):
        self.id = user_id or str(uuid.uuid4())
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


def create_mock_supabase():
    """Create a mock Supabase client for testing"""
    mock_supabase = MagicMock()
    
    # Mock table operations
    mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value = \
        MockSupabaseResponse([])
    mock_supabase.table.return_value.update.return_value.eq.return_value.execute.return_value = \
        MockSupabaseResponse([])
    mock_supabase.table.return_value.delete.return_value.eq.return_value.execute.return_value = \
        MockSupabaseResponse([])
    mock_supabase.table.return_value.insert.return_value.execute.return_value = \
        MockSupabaseResponse([])
    
    # Mock auth
    mock_supabase.auth.admin.delete_user = MagicMock()
    
    return mock_supabase


@pytest.fixture
def mock_env(monkeypatch):
    """Set up environment variables for testing."""
    monkeypatch.setenv("ADMIN_EMAILS", "admin@example.com")
    monkeypatch.setenv("SUPABASE_URL", "https://test.supabase.co")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "test-anon-key-" + "x" * 100)
    monkeypatch.setenv("SUPABASE_SERVICE_KEY", "test-service-key-" + "x" * 200)
    monkeypatch.setenv("APP_ENV", "test")


@pytest.fixture
def admin_user():
    """Create admin user for testing."""
    return MockUser("admin@example.com", str(uuid.uuid4()))


class TestUserDetail:
    """Tests for GET /api/admin/users/{user_id}"""
    
    def test_get_user_detail_success(self, client, mock_env, admin_user):
        """Test successful retrieval of user details."""
        user_id = str(uuid.uuid4())
        
        with patch("api.dependencies.get_supabase_anon_auth_client") as mock_anon, \
             patch("api.dependencies.get_supabase_service_role_client") as mock_service:
            
            # Mock admin auth
            mock_anon.return_value.auth.get_user.return_value = MockUserResponse(admin_user)
            
            # Mock service client
            mock_supabase = create_mock_supabase()
            mock_service.return_value = mock_supabase
            
            # Mock user profile
            profile_data = {
                "id": user_id,
                "email": "patient@example.com",
                "role": "patient",
                "is_test_patient": False,
                "source": "admin_manual",
                "created_at": "2024-01-01T00:00:00Z"
            }
            mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value = \
                MockSupabaseResponse([profile_data])
            
            # Mock aggregates (counts)
            mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value.count = 5
            
            response = client.get(
                f"/api/admin/users/{user_id}",
                headers={"Authorization": "Bearer test-token"}
            )
            
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "success"
            assert "user" in data
            assert "aggregates" in data
            assert data["user"]["id"] == user_id
    
    def test_get_user_detail_not_found(self, client, mock_env, admin_user):
        """Test retrieval of non-existent user."""
        user_id = str(uuid.uuid4())
        
        with patch("api.dependencies.get_supabase_anon_auth_client") as mock_anon, \
             patch("api.dependencies.get_supabase_service_role_client") as mock_service:
            
            mock_anon.return_value.auth.get_user.return_value = MockUserResponse(admin_user)
            
            mock_supabase = create_mock_supabase()
            mock_service.return_value = mock_supabase
            
            # No user found
            mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value = \
                MockSupabaseResponse([])
            
            response = client.get(
                f"/api/admin/users/{user_id}",
                headers={"Authorization": "Bearer test-token"}
            )
            
            assert response.status_code == 404


class TestUserUpdate:
    """Tests for PATCH /api/admin/users/{user_id}"""
    
    def test_update_user_success(self, client, mock_env, admin_user):
        """Test successful user update."""
        user_id = str(uuid.uuid4())
        
        with patch("api.dependencies.get_supabase_anon_auth_client") as mock_anon, \
             patch("api.dependencies.get_supabase_service_role_client") as mock_service:
            
            mock_anon.return_value.auth.get_user.return_value = MockUserResponse(admin_user)
            
            mock_supabase = create_mock_supabase()
            mock_service.return_value = mock_supabase
            
            # Mock existing user
            mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value = \
                MockSupabaseResponse([{"id": user_id, "deleted_at": None}])
            
            # Mock update success
            mock_supabase.table.return_value.update.return_value.eq.return_value.execute.return_value = \
                MockSupabaseResponse([{"id": user_id, "role": "therapist"}])
            
            response = client.patch(
                f"/api/admin/users/{user_id}",
                headers={"Authorization": "Bearer test-token"},
                json={"role": "therapist"}
            )
            
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "success"
            assert data["user_id"] == user_id
    
    def test_update_deleted_user_fails(self, client, mock_env, admin_user):
        """Test that updating deleted user fails."""
        user_id = str(uuid.uuid4())
        
        with patch("api.dependencies.get_supabase_anon_auth_client") as mock_anon, \
             patch("api.dependencies.get_supabase_service_role_client") as mock_service:
            
            mock_anon.return_value.auth.get_user.return_value = MockUserResponse(admin_user)
            
            mock_supabase = create_mock_supabase()
            mock_service.return_value = mock_supabase
            
            # Mock deleted user
            mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value = \
                MockSupabaseResponse([{"id": user_id, "deleted_at": "2024-01-01T00:00:00Z"}])
            
            response = client.patch(
                f"/api/admin/users/{user_id}",
                headers={"Authorization": "Bearer test-token"},
                json={"role": "therapist"}
            )
            
            assert response.status_code == 400
            assert "deleted" in response.json()["detail"].lower()


class TestUserDelete:
    """Tests for DELETE /api/admin/users/{user_id}"""
    
    def test_delete_test_user_hard_delete(self, client, mock_env, admin_user):
        """Test that test users are hard deleted."""
        user_id = str(uuid.uuid4())
        
        with patch("api.dependencies.get_supabase_anon_auth_client") as mock_anon, \
             patch("api.dependencies.get_supabase_service_role_client") as mock_service:
            
            mock_anon.return_value.auth.get_user.return_value = MockUserResponse(admin_user)
            
            mock_supabase = create_mock_supabase()
            mock_service.return_value = mock_supabase
            
            # Mock test user
            mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value = \
                MockSupabaseResponse([{
                    "id": user_id,
                    "email": "test@example.com",
                    "is_test_patient": True
                }])
            
            response = client.delete(
                f"/api/admin/users/{user_id}",
                headers={"Authorization": "Bearer test-token"}
            )
            
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "success"
            assert data["deletion_type"] == "hard"
            
            # Verify auth user was deleted
            mock_supabase.auth.admin.delete_user.assert_called_once_with(user_id)
    
    def test_delete_normal_user_soft_delete(self, client, mock_env, admin_user):
        """Test that normal users are soft deleted."""
        user_id = str(uuid.uuid4())
        
        with patch("api.dependencies.get_supabase_anon_auth_client") as mock_anon, \
             patch("api.dependencies.get_supabase_service_role_client") as mock_service:
            
            mock_anon.return_value.auth.get_user.return_value = MockUserResponse(admin_user)
            
            mock_supabase = create_mock_supabase()
            mock_service.return_value = mock_supabase
            
            # Mock normal user
            mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value = \
                MockSupabaseResponse([{
                    "id": user_id,
                    "email": "normal@example.com",
                    "is_test_patient": False
                }])
            
            response = client.delete(
                f"/api/admin/users/{user_id}",
                headers={"Authorization": "Bearer test-token"}
            )
            
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "success"
            assert data["deletion_type"] == "soft"
            
            # Verify auth user was NOT deleted (soft delete)
            mock_supabase.auth.admin.delete_user.assert_not_called()
