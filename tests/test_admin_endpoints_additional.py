# tests/test_admin_endpoints_additional.py
"""
Additional tests for admin endpoints to ensure comprehensive coverage.

This file provides test coverage for admin endpoints that were not fully covered
in the original test_admin_endpoints.py file.
"""
import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    """Create test client with rate limiting disabled."""
    from main import app

    # Disable rate limiting for tests
    app.state.limiter.enabled = False

    yield TestClient(app)

    # Re-enable after tests
    app.state.limiter.enabled = True


class MockSupabaseResponse:
    """Mock response from Supabase"""
    def __init__(self, data):
        self.data = data


class MockUser:
    """Mock Supabase User object"""
    def __init__(self, email, user_metadata=None):
        self.id = "test-user-id-123"
        self.email = email
        self.user_metadata = user_metadata or {}
        self.app_metadata = {}
        self.role = None


class MockUserResponse:
    """Mock UserResponse from Supabase auth.get_user()"""
    def __init__(self, user):
        self.user = user


def create_mock_supabase_client(return_data=None, mock_user=None):
    """Create a mock Supabase client"""
    mock_client = MagicMock()

    if return_data is None:
        return_data = []

    def mock_execute():
        return MockSupabaseResponse(return_data)

    # Create generic chain that works for all operations
    def create_chain():
        mock_method = MagicMock()

        # Support various chain methods
        for method in ['execute', 'insert', 'upsert', 'update', 'delete', 'eq', 'select', 'limit', 'order', 'in_', 'is_', 'gte', 'lt', 'head']:
            if method == 'execute':
                setattr(mock_method, method, mock_execute)
            else:
                setattr(mock_method, method, MagicMock(return_value=mock_method))

        return mock_method

    mock_client.table = MagicMock(return_value=create_chain())
    
    # Mock auth.get_user() method
    async def mock_get_user(jwt=None):
        if mock_user:
            return MockUserResponse(mock_user)
        return None
    
    mock_auth = MagicMock()
    mock_auth.get_user = mock_get_user
    mock_client.auth = mock_auth

    return mock_client


@pytest.fixture
def admin_user():
    """Return a mock admin user."""
    return MockUser(email="admin@example.com", user_metadata={"role": "admin"})


@pytest.fixture
def non_admin_user():
    """Return a mock non-admin user."""
    return MockUser(email="user@example.com", user_metadata={})


@pytest.fixture
def mock_env(monkeypatch):
    """Mock environment variables."""
    # Use realistic JWT keys that pass validation
    mock_service_key = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9." + "x" * 150  # 200+ chars
    mock_anon_key = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9." + "y" * 80  # 120+ chars
    monkeypatch.setenv("SUPABASE_URL", "https://test.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_KEY", mock_service_key)
    monkeypatch.setenv("SUPABASE_ANON_KEY", mock_anon_key)
    monkeypatch.setenv("ADMIN_EMAILS", "admin@example.com,superadmin@test.com")


class TestCleanupDataEndpoint:
    """Test the /api/admin/cleanup-data endpoint."""

    def test_cleanup_data_without_auth_returns_401(self, client, mock_env):
        """Test that request without authorization header is rejected."""
        async def mock_create(*args, **kwargs):
            return create_mock_supabase_client()
        
        with patch("api.dependencies.acreate_client", side_effect=mock_create):
            response = client.post(
                "/api/admin/cleanup-data",
                json={"confirm": True}
            )

            assert response.status_code == 401
            assert "authorization required" in response.json()["detail"].lower()

    def test_cleanup_data_with_invalid_token_returns_401(self, client, mock_env):
        """Test that request with invalid token is rejected."""
        async def mock_create(*args, **kwargs):
            return create_mock_supabase_client(mock_user=None)
        
        with patch("api.dependencies.acreate_client", side_effect=mock_create):
            response = client.post(
                "/api/admin/cleanup-data",
                headers={"Authorization": "Bearer invalid-token"},
                json={"confirm": True}
            )

            assert response.status_code == 401
            assert "invalid" in response.json()["detail"].lower()

    def test_cleanup_data_with_non_admin_returns_403(self, client, mock_env, non_admin_user):
        """Test that non-admin user gets 403 Forbidden."""
        async def mock_create(*args, **kwargs):
            return create_mock_supabase_client(mock_user=non_admin_user)
        
        with patch("api.dependencies.acreate_client", side_effect=mock_create):
            response = client.post(
                "/api/admin/cleanup-data",
                headers={"Authorization": "Bearer valid-non-admin-token"},
                json={"confirm": True}
            )

            assert response.status_code == 403
            assert "forbidden" in response.json()["detail"].lower()

    def test_cleanup_data_without_confirmation_returns_400(self, client, mock_env, admin_user):
        """Test that cleanup without confirmation is rejected."""
        async def mock_create(*args, **kwargs):
            return create_mock_supabase_client(mock_user=admin_user)
        
        with patch("api.dependencies.acreate_client", side_effect=mock_create):
            response = client.post(
                "/api/admin/cleanup-data",
                headers={"Authorization": "Bearer valid-admin-token"},
                json={"confirm": False}
            )

            assert response.status_code == 400
            assert "confirmation" in response.json()["detail"].lower()

    def test_cleanup_data_success(self, client, mock_env, admin_user):
        """Test successful cleanup operation."""
        # Mock synthetic users
        synthetic_users = [
            {"id": "user-1", "email": "test1@example.com"},
            {"id": "user-2", "email": "test2@example.org"},
        ]
        
        async def mock_create(*args, **kwargs):
            return create_mock_supabase_client(return_data=synthetic_users, mock_user=admin_user)
        
        with patch("api.dependencies.acreate_client", side_effect=mock_create):
            response = client.post(
                "/api/admin/cleanup-data",
                headers={"Authorization": "Bearer valid-admin-token"},
                json={"confirm": True}
            )

            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "success"
            assert "statistics" in data


class TestSyntheticDataCleanEndpoint:
    """Test the /api/admin/synthetic-data/clean endpoint."""

    def test_synthetic_clean_without_auth_returns_401(self, client, mock_env):
        """Test that request without authorization header is rejected."""
        async def mock_create(*args, **kwargs):
            return create_mock_supabase_client()
        
        with patch("api.dependencies.acreate_client", side_effect=mock_create):
            response = client.post(
                "/api/admin/synthetic-data/clean",
                json={"action": "delete_all"}
            )

            assert response.status_code == 401

    def test_synthetic_clean_with_non_admin_returns_403(self, client, mock_env, non_admin_user):
        """Test that non-admin user gets 403 Forbidden."""
        async def mock_create(*args, **kwargs):
            return create_mock_supabase_client(mock_user=non_admin_user)
        
        with patch("api.dependencies.acreate_client", side_effect=mock_create):
            response = client.post(
                "/api/admin/synthetic-data/clean",
                headers={"Authorization": "Bearer valid-non-admin-token"},
                json={"action": "delete_all"}
            )

            assert response.status_code == 403

    def test_synthetic_clean_delete_all_success(self, client, mock_env, admin_user):
        """Test successful delete_all action."""
        async def mock_create(*args, **kwargs):
            return create_mock_supabase_client(return_data=[], mock_user=admin_user)
        
        with patch("api.dependencies.acreate_client", side_effect=mock_create):
            response = client.post(
                "/api/admin/synthetic-data/clean",
                headers={"Authorization": "Bearer valid-admin-token"},
                json={"action": "delete_all"}
            )

            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "success"

    def test_synthetic_clean_delete_last_n_without_quantity_returns_400(self, client, mock_env, admin_user):
        """Test that delete_last_n without quantity returns 400."""
        async def mock_create(*args, **kwargs):
            return create_mock_supabase_client(mock_user=admin_user)
        
        with patch("api.dependencies.acreate_client", side_effect=mock_create):
            response = client.post(
                "/api/admin/synthetic-data/clean",
                headers={"Authorization": "Bearer valid-admin-token"},
                json={"action": "delete_last_n"}
            )

            assert response.status_code == 400
            assert "quantity" in response.json()["detail"].lower()


class TestSyntheticDataExportEndpoint:
    """Test the /api/admin/synthetic-data/export endpoint."""

    def test_export_without_auth_returns_401(self, client, mock_env):
        """Test that request without authorization header is rejected."""
        async def mock_create(*args, **kwargs):
            return create_mock_supabase_client()
        
        with patch("api.dependencies.acreate_client", side_effect=mock_create):
            response = client.get("/api/admin/synthetic-data/export")

            assert response.status_code == 401

    def test_export_with_non_admin_returns_403(self, client, mock_env, non_admin_user):
        """Test that non-admin user gets 403 Forbidden."""
        async def mock_create(*args, **kwargs):
            return create_mock_supabase_client(mock_user=non_admin_user)
        
        with patch("api.dependencies.acreate_client", side_effect=mock_create):
            response = client.get(
                "/api/admin/synthetic-data/export",
                headers={"Authorization": "Bearer valid-non-admin-token"}
            )

            assert response.status_code == 403

    def test_export_invalid_format_returns_400(self, client, mock_env, admin_user):
        """Test that invalid format returns 400."""
        async def mock_create(*args, **kwargs):
            return create_mock_supabase_client(mock_user=admin_user)
        
        with patch("api.dependencies.acreate_client", side_effect=mock_create):
            response = client.get(
                "/api/admin/synthetic-data/export?format=invalid",
                headers={"Authorization": "Bearer valid-admin-token"}
            )

            assert response.status_code == 400
            assert "format" in response.json()["detail"].lower()

    def test_export_json_success(self, client, mock_env, admin_user):
        """Test successful JSON export."""
        synthetic_users = [
            {"id": "user-1", "email": "test1@example.com", "is_test_patient": True, "created_at": "2024-01-01T00:00:00Z"}
        ]
        
        async def mock_create(*args, **kwargs):
            return create_mock_supabase_client(return_data=synthetic_users, mock_user=admin_user)
        
        with patch("api.dependencies.acreate_client", side_effect=mock_create):
            response = client.get(
                "/api/admin/synthetic-data/export?format=json",
                headers={"Authorization": "Bearer valid-admin-token"}
            )

            assert response.status_code == 200
            assert response.headers["content-type"] == "application/json"

    def test_export_csv_success(self, client, mock_env, admin_user):
        """Test successful CSV export."""
        synthetic_users = [
            {"id": "user-1", "email": "test1@example.com", "is_test_patient": True, "created_at": "2024-01-01T00:00:00Z"}
        ]
        
        async def mock_create(*args, **kwargs):
            return create_mock_supabase_client(return_data=synthetic_users, mock_user=admin_user)
        
        with patch("api.dependencies.acreate_client", side_effect=mock_create):
            response = client.get(
                "/api/admin/synthetic-data/export?format=csv",
                headers={"Authorization": "Bearer valid-admin-token"}
            )

            assert response.status_code == 200
            assert response.headers["content-type"] == "text/csv; charset=utf-8"


class TestToggleTestFlagEndpoint:
    """Test the /api/admin/patients/{patient_id}/toggle-test-flag endpoint."""

    def test_toggle_flag_without_auth_returns_401(self, client, mock_env):
        """Test that request without authorization header is rejected."""
        async def mock_create(*args, **kwargs):
            return create_mock_supabase_client()
        
        with patch("api.dependencies.acreate_client", side_effect=mock_create):
            response = client.patch("/api/admin/patients/test-id/toggle-test-flag")

            assert response.status_code == 401

    def test_toggle_flag_with_non_admin_returns_403(self, client, mock_env, non_admin_user):
        """Test that non-admin user gets 403 Forbidden."""
        async def mock_create(*args, **kwargs):
            return create_mock_supabase_client(mock_user=non_admin_user)
        
        with patch("api.dependencies.acreate_client", side_effect=mock_create):
            response = client.patch(
                "/api/admin/patients/test-id/toggle-test-flag",
                headers={"Authorization": "Bearer valid-non-admin-token"}
            )

            assert response.status_code == 403

    def test_toggle_flag_patient_not_found_returns_404(self, client, mock_env, admin_user):
        """Test that non-existent patient returns 404."""
        async def mock_create(*args, **kwargs):
            return create_mock_supabase_client(return_data=[], mock_user=admin_user)
        
        with patch("api.dependencies.acreate_client", side_effect=mock_create):
            response = client.patch(
                "/api/admin/patients/non-existent-id/toggle-test-flag",
                headers={"Authorization": "Bearer valid-admin-token"}
            )

            assert response.status_code == 404

    def test_toggle_flag_success(self, client, mock_env, admin_user):
        """Test successful flag toggle."""
        patient_data = [{"id": "patient-123", "is_test_patient": False}]
        
        async def mock_create(*args, **kwargs):
            return create_mock_supabase_client(return_data=patient_data, mock_user=admin_user)
        
        with patch("api.dependencies.acreate_client", side_effect=mock_create):
            response = client.patch(
                "/api/admin/patients/patient-123/toggle-test-flag",
                headers={"Authorization": "Bearer valid-admin-token"}
            )

            assert response.status_code == 200
            data = response.json()
            assert "is_test_patient" in data


class TestRunDeletionJobEndpoint:
    """Test the /api/admin/run-deletion-job endpoint."""

    def test_deletion_job_without_auth_returns_401(self, client, mock_env):
        """Test that request without authorization header is rejected."""
        async def mock_create(*args, **kwargs):
            return create_mock_supabase_client()
        
        with patch("api.dependencies.acreate_client", side_effect=mock_create):
            response = client.post("/api/admin/run-deletion-job")

            assert response.status_code == 401

    def test_deletion_job_with_non_admin_returns_403(self, client, mock_env, non_admin_user):
        """Test that non-admin user gets 403 Forbidden."""
        async def mock_create(*args, **kwargs):
            return create_mock_supabase_client(mock_user=non_admin_user)
        
        with patch("api.dependencies.acreate_client", side_effect=mock_create):
            response = client.post(
                "/api/admin/run-deletion-job",
                headers={"Authorization": "Bearer valid-non-admin-token"}
            )

            assert response.status_code == 403

    def test_deletion_job_success(self, client, mock_env, admin_user):
        """Test successful deletion job execution."""
        async def mock_create(*args, **kwargs):
            return create_mock_supabase_client(mock_user=admin_user)
        
        # Mock the process_scheduled_deletions function
        async def mock_process_deletions():
            return {
                "processed": 5,
                "deleted": 2,
                "errors": 0
            }
        
        with patch("api.dependencies.acreate_client", side_effect=mock_create):
            with patch("jobs.scheduled_deletion.process_scheduled_deletions", side_effect=mock_process_deletions):
                response = client.post(
                    "/api/admin/run-deletion-job",
                    headers={"Authorization": "Bearer valid-admin-token"}
                )

                assert response.status_code == 200
                data = response.json()
                assert data["status"] == "success"
                assert "statistics" in data
