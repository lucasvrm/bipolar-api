"""
Tests for /api/admin/generate-data endpoint.
Validates synthetic data generation with proper counts.
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


def create_mock_supabase():
    """Create a mock Supabase client for testing"""
    mock_client = MagicMock()
    
    # Mock auth.get_user for admin verification
    admin_user = MockUser("admin@example.com")
    mock_client.auth.get_user.return_value = MockUserResponse(admin_user)
    
    # Mock table operations
    def create_chain():
        chain = MagicMock()
        chain.select.return_value = chain
        chain.eq.return_value = chain
        chain.update.return_value = chain
        chain.insert.return_value = chain
        chain.delete.return_value = chain
        chain.in_.return_value = chain
        chain.execute.return_value = MockSupabaseResponse([])
        return chain
    
    mock_client.table.return_value = create_chain()
    
    return mock_client


def test_generate_data_success(client):
    """Test successful synthetic data generation"""
    with patch("api.dependencies.get_supabase_service_role_client") as mock_get_supabase, \
         patch("api.dependencies.get_supabase_anon_auth_client") as mock_get_anon, \
         patch("api.admin.generate_and_populate_data", new_callable=AsyncMock) as mock_generate, \
         patch("api.audit.log_audit_action", new_callable=AsyncMock):
        
        mock_service = create_mock_supabase()
        mock_anon = create_mock_supabase()
        
        mock_get_supabase.return_value = mock_service
        mock_get_anon.return_value = mock_anon
        
        # Mock successful generation
        mock_generate.return_value = {
            "status": "success",
            "statistics": {
                "patients_created": 2,
                "therapists_created": 1,
                "users_created": 3,
                "total_checkins": 6,
                "mood_pattern": "stable",
                "checkins_per_user": 3,
                "generated_at": "2024-11-23T10:00:00Z"
            }
        }
        
        response = client.post(
            "/api/admin/generate-data",
            json={
                "patientsCount": 2,
                "therapistsCount": 1,
                "checkinsPerUser": 3,
                "moodPattern": "stable",
                "seed": 42,
                "clearDb": False
            },
            headers={"Authorization": "Bearer test-token"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["statistics"]["patients_created"] == 2
        assert data["statistics"]["therapists_created"] == 1
        assert data["statistics"]["total_checkins"] == 6


def test_generate_data_invalid_pattern(client):
    """Test generation with invalid mood pattern"""
    with patch("api.dependencies.get_supabase_anon_auth_client") as mock_get_anon:
        mock_anon = create_mock_supabase()
        mock_get_anon.return_value = mock_anon
        
        response = client.post(
            "/api/admin/generate-data",
            json={
                "patientsCount": 1,
                "therapistsCount": 0,
                "checkinsPerUser": 3,
                "moodPattern": "invalid_pattern",
                "clearDb": False
            },
            headers={"Authorization": "Bearer test-token"}
        )
        
        assert response.status_code == 400
        assert "moodPattern inválido" in response.json()["detail"]


def test_generate_data_zero_counts(client):
    """Test generation with zero counts"""
    with patch("api.dependencies.get_supabase_anon_auth_client") as mock_get_anon:
        mock_anon = create_mock_supabase()
        mock_get_anon.return_value = mock_anon
        
        response = client.post(
            "/api/admin/generate-data",
            json={
                "patientsCount": 0,
                "therapistsCount": 0,
                "checkinsPerUser": 3,
                "moodPattern": "stable",
                "clearDb": False
            },
            headers={"Authorization": "Bearer test-token"}
        )
        
        assert response.status_code == 400
        assert "ao menos 1 patient ou 1 therapist" in response.json()["detail"]


def test_generate_data_no_auth(client):
    """Test generation without authorization"""
    response = client.post(
        "/api/admin/generate-data",
        json={
            "patientsCount": 1,
            "therapistsCount": 0,
            "checkinsPerUser": 3,
            "moodPattern": "stable",
            "clearDb": False
        }
    )
    
    assert response.status_code == 401
