"""
Tests for check-in persistence and parameter validation.
Validates the fixes for:
1. Zero parameter handling (patients=0, therapists=0)
2. Check-in counting only after successful insertion
3. Proper error handling and logging
"""
import pytest
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
        import uuid
        self.id = str(uuid.uuid4())
        self.email = email
        self.user_metadata = {"role": "admin"}


class MockUserResponse:
    """Mock UserResponse from Supabase auth.get_user()"""
    def __init__(self, user):
        self.user = user


class MockSupabaseResponse:
    """Mock response from Supabase queries"""
    def __init__(self, data, count=None, error=None):
        self.data = data
        self.count = count
        self.error = error


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


def test_explicit_zero_therapists(client):
    """Test that explicitly requesting 0 therapists is respected"""
    with patch("api.dependencies.get_supabase_service_role_client") as mock_get_supabase, \
         patch("api.dependencies.get_supabase_anon_auth_client") as mock_get_anon, \
         patch("api.admin.generate_and_populate_data", new_callable=AsyncMock) as mock_generate, \
         patch("api.audit.log_audit_action", new_callable=AsyncMock):
        
        mock_service = create_mock_supabase()
        mock_anon = create_mock_supabase()
        
        mock_get_supabase.return_value = mock_service
        mock_get_anon.return_value = mock_anon
        
        # Mock generation with 1 patient, 0 therapists (exactly as requested)
        mock_generate.return_value = {
            "status": "success",
            "statistics": {
                "patients_created": 1,
                "therapists_created": 0,  # Should be 0, not default 1
                "users_created": 1,
                "total_checkins": 30,
                "mood_pattern": "stable",
                "checkins_per_user": 30,
                "generated_at": "2024-11-23T10:00:00Z"
            }
        }
        
        response = client.post(
            "/api/admin/generate-data",
            json={
                "patientsCount": 1,
                "therapistsCount": 0,  # Explicitly zero
                "checkinsPerUser": 30,
                "moodPattern": "stable",
                "clearDb": False
            },
            headers={"Authorization": "Bearer test-token"}
        )
        
        assert response.status_code == 200
        data = response.json()
        
        # Verify mock was called with correct parameters
        mock_generate.assert_called_once()
        call_kwargs = mock_generate.call_args[1]
        assert call_kwargs["patients_count"] == 1
        assert call_kwargs["therapists_count"] == 0  # Must be 0, not 1


def test_explicit_zero_patients(client):
    """Test that explicitly requesting 0 patients is respected"""
    with patch("api.dependencies.get_supabase_service_role_client") as mock_get_supabase, \
         patch("api.dependencies.get_supabase_anon_auth_client") as mock_get_anon, \
         patch("api.admin.generate_and_populate_data", new_callable=AsyncMock) as mock_generate, \
         patch("api.audit.log_audit_action", new_callable=AsyncMock):
        
        mock_service = create_mock_supabase()
        mock_anon = create_mock_supabase()
        
        mock_get_supabase.return_value = mock_service
        mock_get_anon.return_value = mock_anon
        
        # Mock generation with 0 patients, 2 therapists
        mock_generate.return_value = {
            "status": "success",
            "statistics": {
                "patients_created": 0,  # Should be 0
                "therapists_created": 2,
                "users_created": 2,
                "total_checkins": 0,  # No check-ins for therapists
                "mood_pattern": "stable",
                "checkins_per_user": 30,
                "generated_at": "2024-11-23T10:00:00Z"
            }
        }
        
        response = client.post(
            "/api/admin/generate-data",
            json={
                "patientsCount": 0,  # Explicitly zero
                "therapistsCount": 2,
                "checkinsPerUser": 30,
                "moodPattern": "stable",
                "clearDb": False
            },
            headers={"Authorization": "Bearer test-token"}
        )
        
        assert response.status_code == 200
        data = response.json()
        
        # Verify mock was called with correct parameters
        mock_generate.assert_called_once()
        call_kwargs = mock_generate.call_args[1]
        assert call_kwargs["patients_count"] == 0  # Must be 0, not 2
        assert call_kwargs["therapists_count"] == 2


@pytest.mark.asyncio
async def test_checkin_count_only_after_success():
    """Test that check-ins are only counted after successful database insert"""
    from data_generator import generate_and_populate_data
    import uuid
    
    # Create mock supabase client
    mock_supabase = MagicMock()
    
    # Mock auth user creation - return valid user IDs
    patient_id = str(uuid.uuid4())
    
    class MockAuthResp:
        class User:
            def __init__(self):
                self.id = patient_id
        
        def __init__(self):
            self.user = self.User()
    
    mock_supabase.auth.admin.create_user.return_value = MockAuthResp()
    
    # Mock profile update - successful
    mock_supabase.table.return_value.update.return_value.eq.return_value.execute.return_value = \
        MockSupabaseResponse(data=[{"id": patient_id}])
    
    # Mock profile validation query
    mock_supabase.table.return_value.select.return_value.in_.return_value.execute.return_value = \
        MockSupabaseResponse(data=[{"id": patient_id}])
    
    # Mock check-in insertion - simulate partial failure
    # First chunk succeeds with 50 records, second chunk fails
    insert_responses = [
        MockSupabaseResponse(data=[{"id": i} for i in range(50)]),  # 50 successful
        Exception("Database constraint violation"),  # Failure
    ]
    insert_call_count = 0
    
    def mock_insert_side_effect(*args):
        nonlocal insert_call_count
        if insert_call_count < len(insert_responses):
            response = insert_responses[insert_call_count]
            insert_call_count += 1
            if isinstance(response, Exception):
                raise response
            return MagicMock(execute=MagicMock(return_value=response))
        return MagicMock(execute=MagicMock(return_value=MockSupabaseResponse(data=[])))
    
    mock_supabase.table.return_value.insert.side_effect = mock_insert_side_effect
    
    # Generate data with 1 patient, 100 check-ins (will create 2 chunks of 50 each)
    result = await generate_and_populate_data(
        supabase=mock_supabase,
        patients_count=1,
        therapists_count=0,
        checkins_per_patient=100,
        pattern="stable",
        clear_db=False,
    )
    
    # Should only count the 50 successful check-ins from first chunk
    # NOT the 50 from the failed chunk
    assert result["statistics"]["total_checkins"] == 50, \
        f"Expected 50 check-ins (only successful chunk), got {result['statistics']['total_checkins']}"
    
    assert result["statistics"]["patients_created"] == 1


@pytest.mark.asyncio
async def test_checkin_foreign_key_validation():
    """Test that check-ins are validated against existing profile IDs"""
    from data_generator import generate_and_populate_data
    import uuid
    
    mock_supabase = MagicMock()
    
    # Create 2 patient IDs
    patient_id_1 = str(uuid.uuid4())
    patient_id_2 = str(uuid.uuid4())
    patient_ids = [patient_id_1, patient_id_2]
    
    call_counter = {"count": 0}
    
    class MockAuthResp:
        class User:
            def __init__(self, uid):
                self.id = uid
        
        def __init__(self, uid):
            self.user = self.User(uid)
    
    def mock_create_user(*args, **kwargs):
        uid = patient_ids[call_counter["count"]]
        call_counter["count"] += 1
        return MockAuthResp(uid)
    
    mock_supabase.auth.admin.create_user.side_effect = mock_create_user
    
    # Mock profile update - successful for both
    mock_supabase.table.return_value.update.return_value.eq.return_value.execute.return_value = \
        MockSupabaseResponse(data=[{"id": "dummy"}])
    
    # Mock profile validation - only first patient exists in DB (simulating FK issue)
    mock_supabase.table.return_value.select.return_value.in_.return_value.execute.return_value = \
        MockSupabaseResponse(data=[{"id": patient_id_1}])  # Only patient 1 exists
    
    # Mock check-in insertion
    mock_supabase.table.return_value.insert.return_value.execute.return_value = \
        MockSupabaseResponse(data=[{"id": i} for i in range(30)])  # 30 for validated patient
    
    # Generate with 2 patients, but only 1 has valid profile
    result = await generate_and_populate_data(
        supabase=mock_supabase,
        patients_count=2,
        therapists_count=0,
        checkins_per_patient=30,
        pattern="stable",
        clear_db=False,
    )
    
    # Should create 2 patients
    assert result["statistics"]["patients_created"] == 2
    
    # But only generate check-ins for the 1 validated patient (30 check-ins)
    assert result["statistics"]["total_checkins"] == 30, \
        f"Should only create check-ins for validated patient, got {result['statistics']['total_checkins']}"


def test_default_values_when_fields_omitted(client):
    """Test that default values are used when fields are completely omitted"""
    with patch("api.dependencies.get_supabase_service_role_client") as mock_get_supabase, \
         patch("api.dependencies.get_supabase_anon_auth_client") as mock_get_anon, \
         patch("api.admin.generate_and_populate_data", new_callable=AsyncMock) as mock_generate, \
         patch("api.audit.log_audit_action", new_callable=AsyncMock):
        
        mock_service = create_mock_supabase()
        mock_anon = create_mock_supabase()
        
        mock_get_supabase.return_value = mock_service
        mock_get_anon.return_value = mock_anon
        
        mock_generate.return_value = {
            "status": "success",
            "statistics": {
                "patients_created": 2,  # Default
                "therapists_created": 1,  # Default
                "users_created": 3,
                "total_checkins": 60,
                "mood_pattern": "stable",
                "checkins_per_user": 30,
                "generated_at": "2024-11-23T10:00:00Z"
            }
        }
        
        # Don't specify patientsCount or therapistsCount - should use defaults
        response = client.post(
            "/api/admin/generate-data",
            json={
                "moodPattern": "stable",
                "clearDb": False
            },
            headers={"Authorization": "Bearer test-token"}
        )
        
        assert response.status_code == 200
        
        # Verify defaults were used
        mock_generate.assert_called_once()
        call_kwargs = mock_generate.call_args[1]
        assert call_kwargs["patients_count"] == 2  # Default from schema
        assert call_kwargs["therapists_count"] == 1  # Default from schema
