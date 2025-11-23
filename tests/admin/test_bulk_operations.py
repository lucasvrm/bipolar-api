"""
Tests for admin bulk operations endpoints:
- POST /api/admin/synthetic/bulk-users
- POST /api/admin/synthetic/bulk-checkins
- POST /api/admin/test-data/delete-test-users
- POST /api/admin/test-data/clear-database
"""
import pytest
import uuid
from unittest.mock import MagicMock, patch, AsyncMock
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
    mock_supabase.table.return_value.select.return_value.eq.return_value.is_.return_value.execute.return_value = \
        MockSupabaseResponse([])
    mock_supabase.table.return_value.update.return_value.eq.return_value.execute.return_value = \
        MockSupabaseResponse([])
    mock_supabase.table.return_value.delete.return_value.eq.return_value.execute.return_value = \
        MockSupabaseResponse([])
    mock_supabase.table.return_value.delete.return_value.in_.return_value.execute.return_value = \
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
    monkeypatch.setenv("ALLOW_SYNTHETIC_IN_PROD", "0")
    monkeypatch.setenv("SYNTHETIC_MAX_PATIENTS_PROD", "50")
    monkeypatch.setenv("SYNTHETIC_MAX_THERAPISTS_PROD", "10")
    monkeypatch.setenv("SYNTHETIC_MAX_CHECKINS_PER_USER_PROD", "60")


@pytest.fixture
def admin_user():
    """Create admin user for testing."""
    return MockUser("admin@example.com", str(uuid.uuid4()))


class TestBulkUsers:
    """Tests for POST /api/admin/synthetic/bulk-users"""
    
    def test_bulk_create_patients_success(self, client, mock_env, admin_user):
        """Test successful bulk patient creation."""
        with patch("api.dependencies.get_supabase_anon_auth_client") as mock_anon, \
             patch("api.dependencies.get_supabase_service_role_client") as mock_service, \
             patch("data_generator.create_user_with_retry") as mock_create:
            
            mock_anon.return_value.auth.get_user.return_value = MockUserResponse(admin_user)
            
            mock_supabase = create_mock_supabase()
            mock_service.return_value = mock_supabase
            
            # Mock user creation
            async def mock_create_user(*args, **kwargs):
                user_id = str(uuid.uuid4())
                return (user_id, f"patient_{user_id[:8]}@example.com", "password123")
            
            mock_create.side_effect = mock_create_user
            
            response = client.post(
                "/api/admin/synthetic/bulk-users",
                headers={"Authorization": "Bearer test-token"},
                json={
                    "role": "patient",
                    "count": 3,
                    "is_test_patient": True,
                    "source": "synthetic"
                }
            )
            
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "success"
            assert data["users_created"] == 3
            assert data["patients_count"] == 3
            assert len(data["user_ids"]) == 3
    
    def test_bulk_create_exceeds_production_limit(self, client, admin_user):
        """Test that exceeding production limits is rejected."""
        with patch("api.dependencies.get_supabase_anon_auth_client") as mock_anon, \
             patch("api.dependencies.get_supabase_service_role_client") as mock_service:
            
            # Set production environment
            import os
            os.environ["APP_ENV"] = "production"
            os.environ["ALLOW_SYNTHETIC_IN_PROD"] = "1"
            
            mock_anon.return_value.auth.get_user.return_value = MockUserResponse(admin_user)
            mock_service.return_value = create_mock_supabase()
            
            response = client.post(
                "/api/admin/synthetic/bulk-users",
                headers={"Authorization": "Bearer test-token"},
                json={
                    "role": "patient",
                    "count": 100,  # Exceeds limit of 50
                    "is_test_patient": True,
                    "source": "synthetic"
                }
            )
            
            assert response.status_code == 400
            assert "limit" in response.json()["detail"].lower()
            
            # Reset env
            os.environ["APP_ENV"] = "test"


class TestBulkCheckins:
    """Tests for POST /api/admin/synthetic/bulk-checkins"""
    
    def test_bulk_create_checkins_for_test_patients(self, client, mock_env, admin_user):
        """Test bulk check-in creation for test patients."""
        with patch("api.dependencies.get_supabase_anon_auth_client") as mock_anon, \
             patch("api.dependencies.get_supabase_service_role_client") as mock_service:
            
            mock_anon.return_value.auth.get_user.return_value = MockUserResponse(admin_user)
            
            mock_supabase = create_mock_supabase()
            mock_service.return_value = mock_supabase
            
            # Mock test patients
            test_patients = [
                {"id": str(uuid.uuid4())},
                {"id": str(uuid.uuid4())}
            ]
            mock_supabase.table.return_value.select.return_value.eq.return_value.eq.return_value.is_.return_value.execute.return_value = \
                MockSupabaseResponse(test_patients)
            
            # Mock insert response
            mock_supabase.table.return_value.insert.return_value.execute.return_value = \
                MockSupabaseResponse([{"id": str(uuid.uuid4())} for _ in range(10)])
            
            response = client.post(
                "/api/admin/synthetic/bulk-checkins",
                headers={"Authorization": "Bearer test-token"},
                json={
                    "all_test_patients": True,
                    "last_n_days": 5,
                    "checkins_per_day_min": 1,
                    "checkins_per_day_max": 1,
                    "mood_pattern": "stable"
                }
            )
            
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "success"
            assert data["users_affected"] == 2
            assert "checkins_created" in data
    
    def test_bulk_checkins_requires_target(self, client, mock_env, admin_user):
        """Test that bulk checkins requires target users."""
        with patch("api.dependencies.get_supabase_anon_auth_client") as mock_anon, \
             patch("api.dependencies.get_supabase_service_role_client") as mock_service:
            
            mock_anon.return_value.auth.get_user.return_value = MockUserResponse(admin_user)
            mock_service.return_value = create_mock_supabase()
            
            response = client.post(
                "/api/admin/synthetic/bulk-checkins",
                headers={"Authorization": "Bearer test-token"},
                json={
                    "last_n_days": 5,
                    "checkins_per_day_min": 1,
                    "checkins_per_day_max": 1,
                    "mood_pattern": "stable"
                }
            )
            
            assert response.status_code == 400
            assert "target" in response.json()["detail"].lower()


class TestDeleteTestUsers:
    """Tests for POST /api/admin/test-data/delete-test-users"""
    
    def test_delete_test_users_success(self, client, mock_env, admin_user):
        """Test successful deletion of all test users."""
        with patch("api.dependencies.get_supabase_anon_auth_client") as mock_anon, \
             patch("api.dependencies.get_supabase_service_role_client") as mock_service:
            
            mock_anon.return_value.auth.get_user.return_value = MockUserResponse(admin_user)
            
            mock_supabase = create_mock_supabase()
            mock_service.return_value = mock_supabase
            
            # Mock test users
            test_users = [
                {"id": str(uuid.uuid4()), "email": "test1@example.com"},
                {"id": str(uuid.uuid4()), "email": "test2@example.com"}
            ]
            mock_supabase.table.return_value.select.return_value.eq.return_value.is_.return_value.execute.return_value = \
                MockSupabaseResponse(test_users)
            
            # Mock counts for deleted data
            mock_supabase.table.return_value.select.return_value.in_.return_value.execute.return_value.count = 10
            
            response = client.post(
                "/api/admin/test-data/delete-test-users",
                headers={"Authorization": "Bearer test-token"}
            )
            
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "success"
            assert data["users_deleted"] == 2
    
    def test_delete_test_users_none_found(self, client, mock_env, admin_user):
        """Test deletion when no test users exist."""
        with patch("api.dependencies.get_supabase_anon_auth_client") as mock_anon, \
             patch("api.dependencies.get_supabase_service_role_client") as mock_service:
            
            mock_anon.return_value.auth.get_user.return_value = MockUserResponse(admin_user)
            
            mock_supabase = create_mock_supabase()
            mock_service.return_value = mock_supabase
            
            # No test users
            mock_supabase.table.return_value.select.return_value.eq.return_value.is_.return_value.execute.return_value = \
                MockSupabaseResponse([])
            
            response = client.post(
                "/api/admin/test-data/delete-test-users",
                headers={"Authorization": "Bearer test-token"}
            )
            
            assert response.status_code == 200
            data = response.json()
            assert data["users_deleted"] == 0


class TestClearDatabase:
    """Tests for POST /api/admin/test-data/clear-database"""
    
    def test_clear_database_requires_confirmation(self, client, mock_env, admin_user):
        """Test that clear database requires exact confirmation text."""
        with patch("api.dependencies.get_supabase_anon_auth_client") as mock_anon, \
             patch("api.dependencies.get_supabase_service_role_client") as mock_service:
            
            mock_anon.return_value.auth.get_user.return_value = MockUserResponse(admin_user)
            mock_service.return_value = create_mock_supabase()
            
            response = client.post(
                "/api/admin/test-data/clear-database",
                headers={"Authorization": "Bearer test-token"},
                json={"confirm_text": "wrong text"}
            )
            
            assert response.status_code == 400
            assert "confirmation" in response.json()["detail"].lower()
    
    def test_clear_database_blocked_in_production(self, client, admin_user):
        """Test that clear database is blocked in production without flag."""
        with patch("api.dependencies.get_supabase_anon_auth_client") as mock_anon, \
             patch("api.dependencies.get_supabase_service_role_client") as mock_service:
            
            # Set production environment without synthetic flag
            import os
            os.environ["APP_ENV"] = "production"
            os.environ["ALLOW_SYNTHETIC_IN_PROD"] = "0"
            
            mock_anon.return_value.auth.get_user.return_value = MockUserResponse(admin_user)
            mock_service.return_value = create_mock_supabase()
            
            response = client.post(
                "/api/admin/test-data/clear-database",
                headers={"Authorization": "Bearer test-token"},
                json={"confirm_text": "DELETE ALL DATA"}
            )
            
            assert response.status_code == 403
            assert "production" in response.json()["detail"].lower()
            
            # Reset env
            os.environ["APP_ENV"] = "test"
    
    def test_clear_database_success(self, client, mock_env, admin_user):
        """Test successful database clearing."""
        with patch("api.dependencies.get_supabase_anon_auth_client") as mock_anon, \
             patch("api.dependencies.get_supabase_service_role_client") as mock_service:
            
            mock_anon.return_value.auth.get_user.return_value = MockUserResponse(admin_user)
            
            mock_supabase = create_mock_supabase()
            mock_service.return_value = mock_supabase
            
            # Mock all users (test and normal)
            all_users = [
                {"id": str(uuid.uuid4()), "is_test_patient": True, "email": "test@example.com"},
                {"id": str(uuid.uuid4()), "is_test_patient": False, "email": "normal@example.com"}
            ]
            mock_supabase.table.return_value.select.return_value.execute.return_value = \
                MockSupabaseResponse(all_users)
            
            # Mock counts for domain data
            mock_supabase.table.return_value.select.return_value.execute.return_value.count = 100
            
            response = client.post(
                "/api/admin/test-data/clear-database",
                headers={"Authorization": "Bearer test-token"},
                json={"confirm_text": "DELETE ALL DATA"}
            )
            
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "success"
            assert data["test_users_deleted"] >= 0
            assert data["normal_users_soft_deleted"] >= 0
