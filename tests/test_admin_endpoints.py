# tests/test_admin_endpoints.py
"""
Tests for admin endpoints including data generation functionality.
"""
import pytest
import os
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    """Create test client with rate limiting disabled."""
    # Import here to avoid circular imports
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


def create_mock_supabase_client(return_data=None, num_records=30):
    """Create a mock Supabase client"""
    mock_client = MagicMock()
    
    if return_data is None:
        return_data = [{"id": f"test-checkin-{i}"} for i in range(num_records)]
    
    async def mock_execute():
        return MockSupabaseResponse(return_data)
    
    # Create generic chain that works for all operations
    def create_chain():
        mock_method = MagicMock()
        
        # Support various chain methods
        for method in ['execute', 'insert', 'upsert', 'delete', 'eq', 'select', 'limit', 'order']:
            if method == 'execute':
                setattr(mock_method, method, mock_execute)
            else:
                setattr(mock_method, method, MagicMock(return_value=mock_method))
        
        return mock_method
    
    mock_client.table = MagicMock(return_value=create_chain())
    
    return mock_client


async def mock_acreate_client(*args, **kwargs):
    """Async factory that returns a mock client"""
    return create_mock_supabase_client()


@pytest.fixture
def mock_supabase():
    """Mock Supabase client for testing."""
    return mock_acreate_client


@pytest.fixture
def service_key():
    """Return the test service key."""
    return "test-service-key-12345"


@pytest.fixture
def mock_env(service_key, monkeypatch):
    """Mock environment variables."""
    monkeypatch.setenv("SUPABASE_URL", "https://test.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_KEY", service_key)


class TestAdminAuthentication:
    """Test admin authentication for the generate-data endpoint."""
    
    def test_generate_data_without_auth_returns_401(self, client, mock_env):
        """Test that request without authorization header is rejected."""
        with patch("api.dependencies.acreate_client", side_effect=mock_acreate_client):
            response = client.post(
                "/api/admin/generate-data",
                json={"num_users": 1, "checkins_per_user": 10}
            )
            
            assert response.status_code == 401
            assert "authorization required" in response.json()["detail"].lower()
    
    def test_generate_data_with_invalid_token_returns_401(self, client, mock_env):
        """Test that request with invalid token is rejected."""
        with patch("api.dependencies.acreate_client", side_effect=mock_acreate_client):
            response = client.post(
                "/api/admin/generate-data",
                headers={"Authorization": "Bearer invalid-token"},
                json={"num_users": 1, "checkins_per_user": 10}
            )
            
            assert response.status_code == 401
            assert "invalid" in response.json()["detail"].lower()
    
    def test_generate_data_with_valid_service_key_succeeds(self, client, mock_env, service_key):
        """Test that request with valid service key is accepted."""
        with patch("api.dependencies.acreate_client", side_effect=mock_acreate_client):
            response = client.post(
                "/api/admin/generate-data",
                headers={"Authorization": f"Bearer {service_key}"},
                json={"num_users": 1, "checkins_per_user": 10}
            )
            
            # Should succeed or at least not fail auth
            assert response.status_code != 401


class TestDataGeneration:
    """Test the data generation functionality."""
    
    def test_generate_data_default_parameters(self, client, mock_env, service_key):
        """Test data generation with default parameters."""
        with patch("api.dependencies.acreate_client", side_effect=mock_acreate_client):
            response = client.post(
                "/api/admin/generate-data",
                headers={"Authorization": f"Bearer {service_key}"},
                json={}  # Use defaults
            )
            
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "success"
            assert "statistics" in data
            assert data["statistics"]["users_created"] == 5  # default
            assert data["statistics"]["checkins_per_user"] == 30  # default
            assert data["statistics"]["mood_pattern"] == "stable"  # default
    
    def test_generate_data_custom_parameters(self, client, mock_env, service_key):
        """Test data generation with custom parameters."""
        with patch("api.dependencies.acreate_client", side_effect=mock_acreate_client):
            response = client.post(
                "/api/admin/generate-data",
                headers={"Authorization": f"Bearer {service_key}"},
                json={
                    "num_users": 10,
                    "checkins_per_user": 50,
                    "mood_pattern": "cycling"
                }
            )
            
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "success"
            assert data["statistics"]["users_created"] == 10
            assert data["statistics"]["checkins_per_user"] == 50
            assert data["statistics"]["mood_pattern"] == "cycling"
    
    def test_generate_data_invalid_mood_pattern(self, client, mock_env, service_key):
        """Test that invalid mood pattern is rejected."""
        with patch("api.dependencies.acreate_client", side_effect=mock_acreate_client):
            response = client.post(
                "/api/admin/generate-data",
                headers={"Authorization": f"Bearer {service_key}"},
                json={
                    "num_users": 1,
                    "checkins_per_user": 10,
                    "mood_pattern": "invalid_pattern"
                }
            )
            
            assert response.status_code == 400
            assert "invalid mood_pattern" in response.json()["detail"].lower()
    
    def test_generate_data_validates_num_users_range(self, client, mock_env, service_key):
        """Test that num_users is validated within range."""
        with patch("api.dependencies.acreate_client", side_effect=mock_acreate_client):
            # Test too small
            response = client.post(
                "/api/admin/generate-data",
                headers={"Authorization": f"Bearer {service_key}"},
                json={"num_users": 0}
            )
            assert response.status_code == 422  # Validation error
            
            # Test too large
            response = client.post(
                "/api/admin/generate-data",
                headers={"Authorization": f"Bearer {service_key}"},
                json={"num_users": 101}
            )
            assert response.status_code == 422  # Validation error
    
    def test_generate_data_validates_checkins_per_user_range(self, client, mock_env, service_key):
        """Test that checkins_per_user is validated within range."""
        with patch("api.dependencies.acreate_client", side_effect=mock_acreate_client):
            # Test too small
            response = client.post(
                "/api/admin/generate-data",
                headers={"Authorization": f"Bearer {service_key}"},
                json={"checkins_per_user": 0}
            )
            assert response.status_code == 422  # Validation error
            
            # Test too large
            response = client.post(
                "/api/admin/generate-data",
                headers={"Authorization": f"Bearer {service_key}"},
                json={"checkins_per_user": 366}
            )
            assert response.status_code == 422  # Validation error
    
    def test_generate_data_returns_user_ids(self, client, mock_env, service_key):
        """Test that generated user IDs are returned in response."""
        with patch("api.dependencies.acreate_client", side_effect=mock_acreate_client):
            response = client.post(
                "/api/admin/generate-data",
                headers={"Authorization": f"Bearer {service_key}"},
                json={"num_users": 3, "checkins_per_user": 5}
            )
            
            assert response.status_code == 200
            data = response.json()
            assert "statistics" in data
            assert "user_ids" in data["statistics"]
            assert len(data["statistics"]["user_ids"]) == 3
            
            # Check that user_ids are valid UUIDs (basic format check)
            for user_id in data["statistics"]["user_ids"]:
                assert isinstance(user_id, str)
                assert len(user_id) == 36  # UUID string length
                assert user_id.count('-') == 4  # UUID has 4 hyphens


class TestDataGeneratorModule:
    """Test the data_generator module functions directly."""
    
    def test_generate_realistic_checkin_structure(self):
        """Test that generated check-in has correct structure."""
        from data_generator import generate_realistic_checkin
        
        user_id = "test-user-123"
        checkin_date = datetime.now(timezone.utc)
        
        checkin = generate_realistic_checkin(user_id, checkin_date)
        
        # Check required fields exist
        assert checkin["user_id"] == user_id
        assert "checkin_date" in checkin
        assert "hoursSlept" in checkin
        assert "sleepQuality" in checkin
        assert "energyLevel" in checkin
        assert "depressedMood" in checkin
        assert "anxietyStress" in checkin
        assert "activation" in checkin
        assert "elevation" in checkin
        assert "medicationAdherence" in checkin
        assert "medicationTiming" in checkin
        assert "compulsionIntensity" in checkin
    
    def test_generate_realistic_checkin_mood_states(self):
        """Test that different mood states produce appropriate values."""
        from data_generator import generate_realistic_checkin
        
        user_id = "test-user-123"
        checkin_date = datetime.now(timezone.utc)
        
        # Test manic state
        manic_checkin = generate_realistic_checkin(user_id, checkin_date, "MANIC")
        assert manic_checkin["hoursSlept"] < 7  # Low sleep in manic
        assert manic_checkin["energyLevel"] >= 7  # High energy in manic
        assert manic_checkin["activation"] >= 7  # High activation in manic
        
        # Test depressed state
        depressed_checkin = generate_realistic_checkin(user_id, checkin_date, "DEPRESSED")
        assert depressed_checkin["hoursSlept"] >= 8  # More sleep in depression
        assert depressed_checkin["energyLevel"] <= 4  # Low energy in depression
        assert depressed_checkin["depressedMood"] >= 6  # High depressed mood
        
        # Test euthymic state
        euthymic_checkin = generate_realistic_checkin(user_id, checkin_date, "EUTHYMIC")
        assert 6.5 <= euthymic_checkin["hoursSlept"] <= 8.5  # Normal sleep
        assert 5 <= euthymic_checkin["energyLevel"] <= 8  # Normal energy
    
    def test_generate_user_checkin_history_count(self):
        """Test that correct number of check-ins are generated."""
        from data_generator import generate_user_checkin_history
        
        user_id = "test-user-123"
        num_checkins = 20
        
        checkins = generate_user_checkin_history(user_id, num_checkins=num_checkins)
        
        assert len(checkins) == num_checkins
        
        # Verify all have same user_id
        for checkin in checkins:
            assert checkin["user_id"] == user_id
    
    def test_generate_user_checkin_history_chronological(self):
        """Test that check-ins are in chronological order."""
        from data_generator import generate_user_checkin_history
        from datetime import datetime
        
        user_id = "test-user-123"
        checkins = generate_user_checkin_history(user_id, num_checkins=10)
        
        # Extract dates and verify they're in order
        dates = [datetime.fromisoformat(c["checkin_date"].replace('Z', '+00:00')) for c in checkins]
        
        for i in range(len(dates) - 1):
            assert dates[i] < dates[i + 1], "Check-ins should be in chronological order"
    
    def test_generate_user_checkin_history_patterns(self):
        """Test that different mood patterns work."""
        from data_generator import generate_user_checkin_history
        
        user_id = "test-user-123"
        
        # Test each pattern type
        for pattern in ['stable', 'cycling', 'random']:
            checkins = generate_user_checkin_history(
                user_id,
                num_checkins=10,
                mood_pattern=pattern
            )
            assert len(checkins) == 10
