"""
Tests for admin /generate-data endpoint with comprehensive coverage.
"""
import pytest
import os
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient


class MockUser:
    """Mock Supabase User object"""
    def __init__(self, email):
        self.id = "admin-user-id-123"
        self.email = email
        self.user_metadata = {}
        self.app_metadata = {}
        self.role = "authenticated"


class MockUserResponse:
    """Mock UserResponse from Supabase auth.get_user()"""
    def __init__(self, user):
        self.user = user


class MockSupabaseResponse:
    """Mock response from Supabase table operations"""
    def __init__(self, data, count=None):
        self.data = data
        self.count = count


@pytest.fixture
def admin_client():
    """Create test client with admin authorization mocked."""
    # Set environment variables
    os.environ["SUPABASE_URL"] = "https://test.supabase.co"
    os.environ["SUPABASE_SERVICE_KEY"] = "x" * 200
    os.environ["SUPABASE_ANON_KEY"] = "x" * 120
    os.environ["ADMIN_EMAILS"] = "admin@test.com"
    os.environ["RATE_LIMIT_STORAGE_URI"] = "memory://"

    from main import app
    
    # Disable rate limiting for tests
    app.state.limiter.enabled = False
    
    client = TestClient(app)
    
    yield client
    
    # Re-enable after tests
    app.state.limiter.enabled = True


@pytest.fixture
def mock_admin_user():
    """Create a mock admin user"""
    return MockUser(email="admin@test.com")


@pytest.fixture
def mock_non_admin_user():
    """Create a mock non-admin user"""
    return MockUser(email="user@test.com")


def test_generate_data_requires_auth(admin_client):
    """Test that /generate-data requires authorization header"""
    response = admin_client.post("/api/admin/generate-data", json={
        "patients_count": 2,
        "therapists_count": 1,
        "checkins_per_user": 10,
        "mood_pattern": "stable",
        "clear_db": False
    })
    
    assert response.status_code == 401
    assert "bearer token" in response.json()["detail"].lower()


def test_generate_data_invalid_mood_pattern(admin_client, mock_admin_user):
    """Test that /generate-data validates mood_pattern"""
    from api.dependencies import verify_admin_authorization, get_supabase_service
    from main import app
    
    # Override admin verification to always return True
    async def mock_verify_admin(authorization: str = None):
        return True
    
    async def mock_service_client():
        mock = MagicMock()
        
        async def mock_execute():
            return MockSupabaseResponse([])
        
        mock_chain = MagicMock()
        mock_chain.execute = mock_execute
        mock_chain.select = MagicMock(return_value=mock_chain)
        mock_chain.delete = MagicMock(return_value=mock_chain)
        mock_chain.in_ = MagicMock(return_value=mock_chain)
        
        mock.table = MagicMock(return_value=mock_chain)
        return mock
    
    app.dependency_overrides[verify_admin_authorization] = mock_verify_admin
    app.dependency_overrides[get_supabase_service] = mock_service_client
    
    try:
        response = admin_client.post("/api/admin/generate-data", 
            headers={"Authorization": "Bearer valid-token"},
            json={
                "patients_count": 2,
                "therapists_count": 1,
                "checkins_per_user": 10,
                "mood_pattern": "invalid_pattern",  # Invalid pattern
                "clear_db": False
            }
        )
        
        assert response.status_code == 400
        assert "invalid mood_pattern" in response.json()["detail"].lower()
    finally:
        app.dependency_overrides.clear()


def test_generate_data_success(admin_client, mock_admin_user):
    """Test successful data generation"""
    from api.dependencies import verify_admin_authorization, get_supabase_service
    from main import app
    
    # Override admin verification to always return True
    async def mock_verify_admin(authorization: str = None):
        return True
    
    # Mock the generate_and_populate_data function
    async def mock_generate_data(**kwargs):
        return {
            "status": "success",
            "statistics": {
                "users_created": 3,
                "patients_created": 2,
                "therapists_created": 1,
                "total_checkins": 20,
                "mood_pattern": "stable",
                "checkins_per_user": 10,
                "generated_at": datetime.now(timezone.utc).isoformat()
            },
            "patient_ids": ["patient-1", "patient-2"],
            "therapist_ids": ["therapist-1"]
        }
    
    async def mock_service_client():
        mock = MagicMock()
        
        async def mock_execute():
            return MockSupabaseResponse([])
        
        mock_chain = MagicMock()
        mock_chain.execute = mock_execute
        mock_chain.select = MagicMock(return_value=mock_chain)
        mock_chain.delete = MagicMock(return_value=mock_chain)
        mock_chain.in_ = MagicMock(return_value=mock_chain)
        
        mock.table = MagicMock(return_value=mock_chain)
        return mock
    
    app.dependency_overrides[verify_admin_authorization] = mock_verify_admin
    app.dependency_overrides[get_supabase_service] = mock_service_client
    
    try:
        with patch('api.admin.generate_and_populate_data', side_effect=mock_generate_data):
            response = admin_client.post("/api/admin/generate-data",
                headers={"Authorization": "Bearer valid-token"},
                json={
                    "patients_count": 2,
                    "therapists_count": 1,
                    "checkins_per_user": 10,
                    "mood_pattern": "stable",
                    "clear_db": False
                }
            )
            
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "success"
            assert data["statistics"]["patients_created"] == 2
            assert data["statistics"]["therapists_created"] == 1
            assert data["statistics"]["total_checkins"] == 20
            assert data["statistics"]["mood_pattern"] == "stable"
    finally:
        app.dependency_overrides.clear()


def test_generate_data_non_admin_forbidden(admin_client, mock_non_admin_user):
    """Test that non-admin users get 403"""
    from api.dependencies import verify_admin_authorization
    from main import app
    from fastapi import HTTPException
    
    # Override admin verification to raise 403
    async def mock_verify_non_admin(authorization: str = None):
        raise HTTPException(status_code=403, detail="Not authorized as admin")
    
    app.dependency_overrides[verify_admin_authorization] = mock_verify_non_admin
    
    try:
        response = admin_client.post("/api/admin/generate-data",
            headers={"Authorization": "Bearer valid-token"},
            json={
                "patients_count": 2,
                "therapists_count": 1,
                "checkins_per_user": 10,
                "mood_pattern": "stable",
                "clear_db": False
            }
        )
        
        assert response.status_code == 403
        assert "not authorized" in response.json()["detail"].lower()
    finally:
        app.dependency_overrides.clear()


def test_stats_endpoint_with_admin(admin_client, mock_admin_user):
    """Test /stats endpoint returns proper structure"""
    from api.dependencies import verify_admin_authorization, get_supabase_service
    from main import app
    
    # Override admin verification to always return True
    async def mock_verify_admin(authorization: str = None):
        return True
    
    async def mock_service_client():
        mock = MagicMock()
        
        # Different data for different queries
        call_count = {'count': 0}
        
        async def mock_execute():
            call_count['count'] += 1
            # First few calls are for counts (head=True)
            if call_count['count'] <= 2:
                return MockSupabaseResponse(data=[], count=10)
            # Profile data
            elif call_count['count'] == 3:
                return MockSupabaseResponse(
                    data=[
                        {"id": "user-1", "email": "test1@example.com", "role": "patient", "is_test_patient": False},
                        {"id": "user-2", "email": "test2@example.org", "role": "patient", "is_test_patient": True}
                    ],
                    count=2
                )
            # Check-ins data
            else:
                return MockSupabaseResponse(
                    data=[
                        {
                            "user_id": "user-1",
                            "checkin_date": "2024-01-01T00:00:00Z",
                            "mood_data": {"elevation": 5, "depressedMood": 3, "activation": 5, "energyLevel": 5, "anxietyStress": 3},
                            "meds_context_data": {"medication_adherence": 80},
                            "appetite_impulse_data": {},
                            "symptoms_data": {}
                        }
                    ],
                    count=1
                )
        
        mock_chain = MagicMock()
        mock_chain.execute = mock_execute
        mock_chain.select = MagicMock(return_value=mock_chain)
        mock_chain.gte = MagicMock(return_value=mock_chain)
        mock_chain.lt = MagicMock(return_value=mock_chain)
        mock_chain.head = MagicMock(return_value=mock_chain)
        
        mock.table = MagicMock(return_value=mock_chain)
        return mock
    
    app.dependency_overrides[verify_admin_authorization] = mock_verify_admin
    app.dependency_overrides[get_supabase_service] = mock_service_client
    
    try:
        response = admin_client.get("/api/admin/stats",
            headers={"Authorization": "Bearer valid-token"}
        )
        
        assert response.status_code == 200
        data = response.json()
        
        # Check required fields from EnhancedStatsResponse
        assert "total_users" in data
        assert "total_checkins" in data
        assert "real_patients_count" in data
        assert "synthetic_patients_count" in data
        assert "checkins_today" in data
        assert "checkins_last_7_days" in data
        assert "avg_checkins_per_active_patient" in data
        assert "mood_distribution" in data
    finally:
        app.dependency_overrides.clear()


def test_verify_admin_authorization_missing_token():
    """Test verify_admin_authorization with missing token"""
    from api.dependencies import verify_admin_authorization
    from fastapi import HTTPException
    
    with pytest.raises(HTTPException) as exc_info:
        import asyncio
        asyncio.run(verify_admin_authorization(authorization=None))
    
    assert exc_info.value.status_code == 401
    assert "bearer token" in exc_info.value.detail.lower()


def test_verify_admin_authorization_invalid_format():
    """Test verify_admin_authorization with invalid token format"""
    from api.dependencies import verify_admin_authorization
    from fastapi import HTTPException
    
    with pytest.raises(HTTPException) as exc_info:
        import asyncio
        asyncio.run(verify_admin_authorization(authorization="InvalidFormat"))
    
    assert exc_info.value.status_code == 401
