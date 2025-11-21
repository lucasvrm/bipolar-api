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
        
        # Check required top-level fields exist
        assert checkin["user_id"] == user_id
        assert "checkin_date" in checkin
        
        # Check JSONB column fields exist
        assert "sleep_data" in checkin
        assert "mood_data" in checkin
        assert "symptoms_data" in checkin
        assert "risk_routine_data" in checkin
        assert "appetite_impulse_data" in checkin
        assert "meds_context_data" in checkin
        
        # Check fields within JSONB columns
        assert "hoursSlept" in checkin["sleep_data"]
        assert "sleepQuality" in checkin["sleep_data"]
        assert "energyLevel" in checkin["mood_data"]
        assert "depressedMood" in checkin["mood_data"]
        assert "anxietyStress" in checkin["mood_data"]
        assert "activation" in checkin["mood_data"]
        assert "elevation" in checkin["mood_data"]
        assert "medicationAdherence" in checkin["meds_context_data"]
        assert "medicationTiming" in checkin["meds_context_data"]
        assert "compulsionIntensity" in checkin["appetite_impulse_data"]
    
    def test_generate_realistic_checkin_mood_states(self):
        """Test that different mood states produce appropriate values."""
        from data_generator import generate_realistic_checkin
        
        user_id = "test-user-123"
        checkin_date = datetime.now(timezone.utc)
        
        # Test manic state
        manic_checkin = generate_realistic_checkin(user_id, checkin_date, "MANIC")
        assert manic_checkin["sleep_data"]["hoursSlept"] < 7  # Low sleep in manic
        assert manic_checkin["mood_data"]["energyLevel"] >= 7  # High energy in manic
        assert manic_checkin["mood_data"]["activation"] >= 7  # High activation in manic
        
        # Test depressed state
        depressed_checkin = generate_realistic_checkin(user_id, checkin_date, "DEPRESSED")
        assert depressed_checkin["sleep_data"]["hoursSlept"] >= 8  # More sleep in depression
        assert depressed_checkin["mood_data"]["energyLevel"] <= 4  # Low energy in depression
        assert depressed_checkin["mood_data"]["depressedMood"] >= 6  # High depressed mood
        
        # Test euthymic state
        euthymic_checkin = generate_realistic_checkin(user_id, checkin_date, "EUTHYMIC")
        assert 6.5 <= euthymic_checkin["sleep_data"]["hoursSlept"] <= 8.5  # Normal sleep
        assert 5 <= euthymic_checkin["mood_data"]["energyLevel"] <= 8  # Normal energy
    
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


class TestCleanupEndpoint:
    """Test the cleanup-data endpoint."""
    
    def test_cleanup_data_without_auth_returns_401(self, client, mock_env):
        """Test that request without authorization header is rejected."""
        with patch("api.dependencies.acreate_client", side_effect=mock_acreate_client):
            response = client.post(
                "/api/admin/cleanup-data",
                json={"confirm": True}
            )
            
            assert response.status_code == 401
            assert "authorization required" in response.json()["detail"].lower()


class TestStatsEndpoint:
    """Test the /api/admin/stats endpoint."""
    
    def test_stats_without_auth_returns_401(self, client, mock_env):
        """Test that request without authorization header is rejected."""
        with patch("api.dependencies.acreate_client", side_effect=mock_acreate_client):
            response = client.get("/api/admin/stats")
            
            assert response.status_code == 401
            assert "authorization required" in response.json()["detail"].lower()
    
    def test_stats_with_invalid_token_returns_401(self, client, mock_env):
        """Test that request with invalid token is rejected."""
        with patch("api.dependencies.acreate_client", side_effect=mock_acreate_client):
            response = client.get(
                "/api/admin/stats",
                headers={"Authorization": "Bearer invalid-token"}
            )
            
            assert response.status_code == 401
            assert "invalid" in response.json()["detail"].lower()
    
    def test_stats_with_valid_service_key_returns_counts(self, client, mock_env, service_key):
        """Test that stats endpoint returns correct counts."""
        # Create mock that returns count data
        mock_client = MagicMock()
        
        # Mock response with count attribute
        class MockCountResponse:
            def __init__(self, count_value):
                self.count = count_value
                self.data = []
        
        async def mock_profiles_execute():
            return MockCountResponse(150)
        
        async def mock_checkins_execute():
            return MockCountResponse(3500)
        
        # Create separate mocks for profiles and check_ins tables
        profiles_mock = MagicMock()
        profiles_mock.select = MagicMock(return_value=profiles_mock)
        profiles_mock.execute = mock_profiles_execute
        
        checkins_mock = MagicMock()
        checkins_mock.select = MagicMock(return_value=checkins_mock)
        checkins_mock.execute = mock_checkins_execute
        
        # Mock table method to return appropriate mock based on table name
        def mock_table(table_name):
            if table_name == 'profiles':
                return profiles_mock
            elif table_name == 'check_ins':
                return checkins_mock
            return MagicMock()
        
        mock_client.table = mock_table
        
        async def mock_create_stats(*args, **kwargs):
            return mock_client
        
        with patch("api.dependencies.acreate_client", side_effect=mock_create_stats):
            response = client.get(
                "/api/admin/stats",
                headers={"Authorization": f"Bearer {service_key}"}
            )
            
            assert response.status_code == 200
            data = response.json()
            assert "total_users" in data
            assert "total_checkins" in data
            assert data["total_users"] == 150
            assert data["total_checkins"] == 3500
    
    def test_stats_handles_zero_counts(self, client, mock_env, service_key):
        """Test that stats endpoint handles zero counts correctly."""
        mock_client = MagicMock()
        
        class MockCountResponse:
            def __init__(self, count_value):
                self.count = count_value
                self.data = []
        
        async def mock_execute():
            return MockCountResponse(0)
        
        chain_mock = MagicMock()
        chain_mock.select = MagicMock(return_value=chain_mock)
        chain_mock.execute = mock_execute
        
        mock_client.table = MagicMock(return_value=chain_mock)
        
        async def mock_create_zero(*args, **kwargs):
            return mock_client
        
        with patch("api.dependencies.acreate_client", side_effect=mock_create_zero):
            response = client.get(
                "/api/admin/stats",
                headers={"Authorization": f"Bearer {service_key}"}
            )
            
            assert response.status_code == 200
            data = response.json()
            assert data["total_users"] == 0
            assert data["total_checkins"] == 0


class TestUsersEndpoint:
    """Test the /api/admin/users endpoint."""
    
    def test_users_without_auth_returns_401(self, client, mock_env):
        """Test that request without authorization header is rejected."""
        with patch("api.dependencies.acreate_client", side_effect=mock_acreate_client):
            response = client.get("/api/admin/users")
            
            assert response.status_code == 401
            assert "authorization required" in response.json()["detail"].lower()
    
    def test_users_with_invalid_token_returns_401(self, client, mock_env):
        """Test that request with invalid token is rejected."""
        with patch("api.dependencies.acreate_client", side_effect=mock_acreate_client):
            response = client.get(
                "/api/admin/users",
                headers={"Authorization": "Bearer invalid-token"}
            )
            
            assert response.status_code == 401
            assert "invalid" in response.json()["detail"].lower()
    
    def test_users_with_valid_service_key_returns_users_list(self, client, mock_env, service_key):
        """Test that users endpoint returns list of users."""
        mock_client = MagicMock()
        
        # Mock users data
        users_data = [
            {"id": "user-1", "email": "user1@example.com", "full_name": "User One"},
            {"id": "user-2", "email": "user2@example.com", "full_name": "User Two"},
            {"id": "user-3", "email": "user3@example.com", "full_name": None},
        ]
        
        async def mock_execute():
            return MockSupabaseResponse(users_data)
        
        # Setup the mock chain
        chain_mock = MagicMock()
        chain_mock.select = MagicMock(return_value=chain_mock)
        chain_mock.order = MagicMock(return_value=chain_mock)
        chain_mock.limit = MagicMock(return_value=chain_mock)
        chain_mock.execute = mock_execute
        
        mock_client.table = MagicMock(return_value=chain_mock)
        
        async def mock_create_users(*args, **kwargs):
            return mock_client
        
        with patch("api.dependencies.acreate_client", side_effect=mock_create_users):
            response = client.get(
                "/api/admin/users",
                headers={"Authorization": f"Bearer {service_key}"}
            )
            
            assert response.status_code == 200
            data = response.json()
            assert isinstance(data, list)
            assert len(data) == 3
            
            # Check first user structure
            assert "id" in data[0]
            assert "email" in data[0]
            assert "full_name" in data[0]
            assert data[0]["id"] == "user-1"
            assert data[0]["email"] == "user1@example.com"
            assert data[0]["full_name"] == "User One"
            
            # Check user with None full_name
            assert data[2]["full_name"] is None
    
    def test_users_returns_empty_list_when_no_users(self, client, mock_env, service_key):
        """Test that users endpoint returns empty list when no users exist."""
        mock_client = MagicMock()
        
        async def mock_execute():
            return MockSupabaseResponse([])
        
        chain_mock = MagicMock()
        chain_mock.select = MagicMock(return_value=chain_mock)
        chain_mock.order = MagicMock(return_value=chain_mock)
        chain_mock.limit = MagicMock(return_value=chain_mock)
        chain_mock.execute = mock_execute
        
        mock_client.table = MagicMock(return_value=chain_mock)
        
        async def mock_create_empty(*args, **kwargs):
            return mock_client
        
        with patch("api.dependencies.acreate_client", side_effect=mock_create_empty):
            response = client.get(
                "/api/admin/users",
                headers={"Authorization": f"Bearer {service_key}"}
            )
            
            assert response.status_code == 200
            data = response.json()
            assert isinstance(data, list)
            assert len(data) == 0


class TestCleanupEndpoint:
    """Test the cleanup-data endpoint."""
    
    
    def test_cleanup_data_with_invalid_token_returns_401(self, client, mock_env):
        """Test that request with invalid token is rejected."""
        with patch("api.dependencies.acreate_client", side_effect=mock_acreate_client):
            response = client.post(
                "/api/admin/cleanup-data",
                headers={"Authorization": "Bearer invalid-token"},
                json={"confirm": True}
            )
            
            assert response.status_code == 401
            assert "invalid" in response.json()["detail"].lower()
    
    def test_cleanup_data_without_confirmation_returns_400(self, client, mock_env, service_key):
        """Test that request without confirmation is rejected."""
        with patch("api.dependencies.acreate_client", side_effect=mock_acreate_client):
            response = client.post(
                "/api/admin/cleanup-data",
                headers={"Authorization": f"Bearer {service_key}"},
                json={"confirm": False}
            )
            
            assert response.status_code == 400
            assert "confirmation" in response.json()["detail"].lower()
    
    def test_cleanup_data_with_valid_auth_and_confirmation_succeeds(self, client, mock_env, service_key):
        """Test that cleanup with valid auth and confirmation succeeds."""
        # Create mock that returns profiles with example.com emails
        mock_client = MagicMock()
        
        # Mock profiles select response
        profiles_data = [
            {"id": "user-1", "email": "test1@example.com"},
            {"id": "user-2", "email": "test2@example.org"},
            {"id": "user-3", "email": "real@gmail.com"}
        ]
        
        async def mock_execute():
            return MockSupabaseResponse(profiles_data)
        
        # Mock for delete operations
        async def mock_delete_execute():
            return MockSupabaseResponse([{"id": "deleted"}])
        
        # Setup the mock chain
        select_mock = MagicMock()
        select_mock.execute = mock_execute
        
        delete_mock = MagicMock()
        delete_mock.eq = MagicMock(return_value=delete_mock)
        delete_mock.execute = mock_delete_execute
        
        table_mock = MagicMock()
        table_mock.select = MagicMock(return_value=select_mock)
        table_mock.delete = MagicMock(return_value=delete_mock)
        
        mock_client.table = MagicMock(return_value=table_mock)
        
        async def mock_create_custom(*args, **kwargs):
            return mock_client
        
        with patch("api.dependencies.acreate_client", side_effect=mock_create_custom):
            response = client.post(
                "/api/admin/cleanup-data",
                headers={"Authorization": f"Bearer {service_key}"},
                json={"confirm": True}
            )
            
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "success"
            assert "statistics" in data
            assert "profiles_deleted" in data["statistics"]
            assert "checkins_deleted" in data["statistics"]


class TestPydanticSchemas:
    """Test the Pydantic schema validation."""
    
    def test_sleep_data_validation(self):
        """Test SleepData model validation."""
        from api.schemas.checkin_jsonb import SleepData
        
        # Valid data
        valid_data = SleepData(
            hoursSlept=7.5,
            sleepQuality=8,
            perceivedSleepNeed=8.0,
            sleepHygiene=7,
            hasNapped=0,
            nappingDurationMin=0
        )
        assert valid_data.hoursSlept == 7.5
        assert valid_data.sleepQuality == 8
        
        # Test validation - hours slept should be 0-24
        with pytest.raises(Exception):  # Pydantic ValidationError
            SleepData(
                hoursSlept=25,  # Invalid
                sleepQuality=8,
                perceivedSleepNeed=8.0,
                sleepHygiene=7,
                hasNapped=0,
                nappingDurationMin=0
            )
    
    def test_mood_data_validation(self):
        """Test MoodData model validation."""
        from api.schemas.checkin_jsonb import MoodData
        
        # Valid data
        valid_data = MoodData(
            energyLevel=7,
            depressedMood=3,
            anxietyStress=4,
            elevation=5,
            activation=6,
            motivationToStart=7
        )
        assert valid_data.energyLevel == 7
        assert valid_data.depressedMood == 3
        
        # Test validation - values should be 0-10
        with pytest.raises(Exception):  # Pydantic ValidationError
            MoodData(
                energyLevel=11,  # Invalid
                depressedMood=3,
                anxietyStress=4,
                elevation=5,
                activation=6,
                motivationToStart=7
            )
    
    def test_symptoms_data_validation(self):
        """Test SymptomsData model validation."""
        from api.schemas.checkin_jsonb import SymptomsData
        
        valid_data = SymptomsData(
            thoughtSpeed=5,
            distractibility=4,
            memoryConcentration=7,
            ruminationAxis=3
        )
        assert valid_data.thoughtSpeed == 5
        
    def test_all_models_work_together(self):
        """Test that all models can be instantiated and dumped."""
        from api.schemas.checkin_jsonb import (
            SleepData, MoodData, SymptomsData, 
            RiskRoutineData, AppetiteImpulseData, MedsContextData
        )
        
        sleep = SleepData(
            hoursSlept=7.5, sleepQuality=8, perceivedSleepNeed=8.0,
            sleepHygiene=7, hasNapped=0, nappingDurationMin=0
        )
        mood = MoodData(
            energyLevel=7, depressedMood=3, anxietyStress=4,
            elevation=5, activation=6, motivationToStart=7
        )
        symptoms = SymptomsData(
            thoughtSpeed=5, distractibility=4,
            memoryConcentration=7, ruminationAxis=3
        )
        risk = RiskRoutineData(
            socialConnection=6, socialRhythmEvent=0,
            exerciseDurationMin=30, exerciseFeeling=7,
            sexualRiskBehavior=0, tasksPlanned=5, tasksCompleted=4
        )
        appetite = AppetiteImpulseData(
            generalAppetite=7, dietTracking=1, skipMeals=0,
            compulsionEpisode=0, compulsionIntensity=0,
            substanceUsage=0, substanceUnits=0,
            caffeineDoses=2, libido=5
        )
        meds = MedsContextData(
            medicationAdherence=1, medicationTiming=1,
            medicationChangeRecent=0, contextualStressors=0
        )
        
        # All should dump to dicts
        assert isinstance(sleep.model_dump(), dict)
        assert isinstance(mood.model_dump(), dict)
        assert isinstance(symptoms.model_dump(), dict)
        assert isinstance(risk.model_dump(), dict)
        assert isinstance(appetite.model_dump(), dict)
        assert isinstance(meds.model_dump(), dict)
