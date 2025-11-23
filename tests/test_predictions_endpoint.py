# tests/test_predictions_endpoint.py
"""
Tests for the multi-type predictions endpoint.
"""
import pytest
import sys
import os
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from fastapi.testclient import TestClient
from main import app

client = TestClient(app)


class MockSupabaseResponse:
    """Mock response from Supabase"""
    def __init__(self, data):
        self.data = data


def create_mock_supabase_client(data):
    """Create a mock Supabase client that returns the given data"""
    mock_client = MagicMock()
    
    def mock_execute():
        return MockSupabaseResponse(data)
    
    # Create the chain
    mock_limit = MagicMock()
    mock_limit.execute = mock_execute
    
    mock_order = MagicMock()
    mock_order.limit.return_value = mock_limit
    
    mock_eq = MagicMock()
    mock_eq.order.return_value = mock_order
    
    mock_select = MagicMock()
    mock_select.eq.return_value = mock_eq
    
    mock_table = MagicMock()
    mock_table.select.return_value = mock_select
    
    mock_client.table.return_value = mock_table
    
    return mock_client


def async_mock_client_factory(data):
    """Sync factory that returns a mock client"""
    return create_mock_supabase_client(data)


def test_predictions_endpoint_no_checkins():
    """Test endpoint with user that has no check-ins"""
    test_user_id = "123e4567-e89b-12d3-a456-426614174000"
    mock_client = create_mock_supabase_client([])
    
    def mock_acreate_client(*args, **kwargs):
        return mock_client
    
    with patch.dict(os.environ, {
        "SUPABASE_URL": "https://test.supabase.co",
        "SUPABASE_SERVICE_KEY": "test-key"
    }):
        with patch("api.dependencies.acreate_client", side_effect=mock_acreate_client):
            # Force reset of cached client to ensure mock is used
            import api.dependencies
            api.dependencies._cached_anon_client = None

            response = client.get(f"/data/predictions/{test_user_id}")
            
            assert response.status_code == 200
            data = response.json()
            
            # Verify structure
            assert "user_id" in data
            assert data["user_id"] == test_user_id
            assert "window_days" in data
            assert data["window_days"] == 3
            assert "generated_at" in data
            assert "predictions" in data
            
            # Should have 5 predictions (all types)
            assert len(data["predictions"]) == 5
            
            # All predictions should have probability 0 or null
            for pred in data["predictions"]:
                assert pred["type"] in [
                    "mood_state",
                    "relapse_risk",
                    "suicidality_risk",
                    "medication_adherence_risk",
                    "sleep_disturbance_risk"
                ]
                # Some may be 0, some might be None depending on how pydantic handles it, but schema says 0.0
                assert pred["probability"] == 0.0
                assert pred["label"] in ["Sem dados", "Dados insuficientes"]
                assert "No check-in data available" in pred["explanation"]


def test_predictions_endpoint_with_checkin():
    """Test endpoint with user that has one check-in"""
    test_user_id = "223e4567-e89b-12d3-a456-426614174001"
    # Mock check-in data
    checkin_data = {
        "id": "test-checkin-123",
        "user_id": test_user_id,
        "checkin_date": "2024-01-15T10:30:00Z",
        "hoursSlept": 6.5,
        "sleepQuality": 6,
        "energyLevel": 5,
        "depressedMood": 4,
        "anxietyStress": 6,
        "medicationAdherence": 1,
        "medicationTiming": 1,
        "compulsionIntensity": 0
    }
    
    mock_client = create_mock_supabase_client([checkin_data])
    
    def mock_acreate_client(*args, **kwargs):
        return mock_client
    
    with patch.dict(os.environ, {
        "SUPABASE_URL": "https://test.supabase.co",
        "SUPABASE_SERVICE_KEY": "test-key"
    }):
        with patch("api.dependencies.acreate_client", side_effect=mock_acreate_client):
            # Force reset of cached client to ensure mock is used
            import api.dependencies
            api.dependencies._cached_anon_client = None

            response = client.get(f"/data/predictions/{test_user_id}")
            
            assert response.status_code == 200
            data = response.json()
            
            # Verify structure
            assert data["user_id"] == test_user_id
            assert data["window_days"] == 3
            assert len(data["predictions"]) == 5
            
            # All predictions should have valid structure
            for pred in data["predictions"]:
                assert "type" in pred
                assert "label" in pred
                assert "probability" in pred
                assert pred["probability"] is not None
                assert isinstance(pred["probability"], (int, float))
                assert 0 <= pred["probability"] <= 1
                assert "explanation" in pred


def test_predictions_endpoint_with_type_filter():
    """Test endpoint with specific prediction types"""
    test_user_id = "323e4567-e89b-12d3-a456-426614174002"
    checkin_data = {
        "id": "test-checkin-123",
        "user_id": test_user_id,
        "checkin_date": "2024-01-15T10:30:00Z",
        "hoursSlept": 6.5,
        "sleepQuality": 6,
        "energyLevel": 5,
        "depressedMood": 4,
        "anxietyStress": 6,
        "medicationAdherence": 1,
        "medicationTiming": 1,
        "compulsionIntensity": 0
    }
    
    mock_client = create_mock_supabase_client([checkin_data])
    
    def mock_acreate_client(*args, **kwargs):
        return mock_client
    
    with patch.dict(os.environ, {
        "SUPABASE_URL": "https://test.supabase.co",
        "SUPABASE_SERVICE_KEY": "test-key"
    }):
        with patch("api.dependencies.acreate_client", side_effect=mock_acreate_client):
            # Force reset of cached client to ensure mock is used
            import api.dependencies
            api.dependencies._cached_anon_client = None

            response = client.get(
                f"/data/predictions/{test_user_id}?types=mood_state,relapse_risk"
            )
            
            assert response.status_code == 200
            data = response.json()
            
            # Should only have 2 predictions
            assert len(data["predictions"]) == 2
            types = [p["type"] for p in data["predictions"]]
            assert "mood_state" in types
            assert "relapse_risk" in types


def test_predictions_endpoint_with_window_days():
    """Test endpoint with custom window_days parameter"""
    test_user_id = "423e4567-e89b-12d3-a456-426614174003"
    checkin_data = {
        "id": "test-checkin-123",
        "user_id": test_user_id,
        "checkin_date": "2024-01-15T10:30:00Z",
        "hoursSlept": 6.5,
        "sleepQuality": 6,
        "energyLevel": 5,
        "depressedMood": 4,
        "anxietyStress": 6,
        "medicationAdherence": 1,
        "medicationTiming": 1,
        "compulsionIntensity": 0
    }
    
    mock_client = create_mock_supabase_client([checkin_data])
    
    def mock_acreate_client(*args, **kwargs):
        return mock_client
    
    with patch.dict(os.environ, {
        "SUPABASE_URL": "https://test.supabase.co",
        "SUPABASE_SERVICE_KEY": "test-key"
    }):
        with patch("api.dependencies.acreate_client", side_effect=mock_acreate_client):
            # Force reset of cached client to ensure mock is used
            import api.dependencies
            api.dependencies._cached_anon_client = None

            response = client.get(f"/data/predictions/{test_user_id}?window_days=7")
            
            assert response.status_code == 200
            data = response.json()
            assert data["window_days"] == 7


def test_predictions_endpoint_invalid_type():
    """Test endpoint with invalid prediction type"""
    test_user_id = "523e4567-e89b-12d3-a456-426614174004"
    with patch.dict(os.environ, {
        "SUPABASE_URL": "https://test.supabase.co",
        "SUPABASE_SERVICE_KEY": "test-key"
    }):
        response = client.get(
            f"/data/predictions/{test_user_id}?types=invalid_type"
        )
        
        assert response.status_code == 400
        assert "invalid types" in str(response.json()["detail"]).lower()


def test_predictions_endpoint_missing_env_vars():
    """Test endpoint with missing environment variables.
    NOTE: This test asserts 500 because standard missing env var triggers 500.
    We want to verify the 'Invalid API key' response specifically in another test or here.
    But since we mocked os.environ to be empty, it will fail at `_create_anon_client`
    with 'Configuração Supabase incompleta (ANON).', which raises 500.
    This is correct behavior for MISSING keys.
    """
    test_user_id = "623e4567-e89b-12d3-a456-426614174005"
    with patch.dict(os.environ, {}, clear=True):
        # Force reset of cached client to ensure it tries to create new one and fails
        import api.dependencies
        api.dependencies._cached_anon_client = None

        response = client.get(f"/data/predictions/{test_user_id}")
        
        # Should return 500 with clear error message
        assert response.status_code == 500
        detail = response.json()["detail"].lower()
        assert "supabase" in detail or "ambiente" in detail or "configuração" in detail


def test_predictions_endpoint_invalid_api_key_response():
    """
    Test endpoint when Supabase returns 'Invalid API key' (401).
    This simulates the production issue where the server returns 401 due to bad config.
    We want the API to return 500 in this case to avoid frontend auth loop.
    """
    test_user_id = "823e4567-e89b-12d3-a456-426614174008"

    # Create a mock that RAISES an APIError resembling the one in production
    mock_client = MagicMock()
    def mock_execute_raising_error():
        from postgrest.exceptions import APIError
        # Create error with the specific details seen in logs
        error = APIError({
            "message": "JSON could not be generated",
            "code": "401",
            "hint": "Refer to full message for details",
            "details": '{"message":"Invalid API key","hint":"Double check your Supabase `anon` or `service_role` API key."}'
        })
        raise error

    # Setup the chain to raise error on execute()
    mock_limit = MagicMock()
    mock_limit.execute = mock_execute_raising_error
    mock_order = MagicMock()
    mock_order.limit.return_value = mock_limit
    mock_eq = MagicMock()
    mock_eq.order.return_value = mock_order
    mock_select = MagicMock()
    mock_select.eq.return_value = mock_eq
    mock_table = MagicMock()
    mock_table.select.return_value = mock_select
    mock_client.table.return_value = mock_table

    def mock_acreate_client(*args, **kwargs):
        return mock_client

    with patch.dict(os.environ, {
        "SUPABASE_URL": "https://test.supabase.co",
        "SUPABASE_SERVICE_KEY": "test-key"
    }):
        with patch("api.dependencies.acreate_client", side_effect=mock_acreate_client):
            import api.dependencies
            api.dependencies._cached_anon_client = None

            response = client.get(f"/data/predictions/{test_user_id}")

            # THIS IS THE KEY ASSERTION: It must be 500, not 401
            assert response.status_code == 500
            assert "configuration invalid" in response.json()["detail"].lower()


def test_prediction_of_day_endpoint_no_checkins():
    """Test prediction_of_day endpoint with user that has no check-ins"""
    valid_uuid = "123e4567-e89b-12d3-a456-426614174000"
    mock_client = create_mock_supabase_client([])
    
    def mock_acreate_client(*args, **kwargs):
        return mock_client
    
    with patch.dict(os.environ, {
        "SUPABASE_URL": "https://test.supabase.co",
        "SUPABASE_SERVICE_KEY": "test-key"
    }):
        with patch("api.dependencies.acreate_client", side_effect=mock_acreate_client):
            # Force reset of cached client to ensure mock is used
            import api.dependencies
            api.dependencies._cached_anon_client = None

            response = client.get(f"/data/prediction_of_day/{valid_uuid}")
            
            assert response.status_code == 200
            data = response.json()
            
            # Verify structure - should only have 3 fields
            assert "type" in data
            assert "label" in data
            assert "probability" in data
            assert len(data) == 3
            
            # Verify content
            assert data["type"] == "mood_state"
            assert data["label"] == "Dados insuficientes"
            assert data["probability"] == 0.0


def test_prediction_of_day_endpoint_with_checkin():
    """Test prediction_of_day endpoint with user that has one check-in"""
    valid_uuid = "223e4567-e89b-12d3-a456-426614174001"
    # Mock check-in data
    checkin_data = {
        "id": "test-checkin-123",
        "user_id": valid_uuid,
        "checkin_date": "2024-01-15T10:30:00Z",
        "hoursSlept": 6.5,
        "sleepQuality": 6,
        "energyLevel": 5,
        "depressedMood": 4,
        "anxietyStress": 6,
        "medicationAdherence": 1,
        "medicationTiming": 1,
        "compulsionIntensity": 0
    }
    
    mock_client = create_mock_supabase_client([checkin_data])
    
    def mock_acreate_client(*args, **kwargs):
        return mock_client
    
    with patch.dict(os.environ, {
        "SUPABASE_URL": "https://test.supabase.co",
        "SUPABASE_SERVICE_KEY": "test-key"
    }):
        with patch("api.dependencies.acreate_client", side_effect=mock_acreate_client):
            # Force reset of cached client to ensure mock is used
            import api.dependencies
            api.dependencies._cached_anon_client = None

            response = client.get(f"/data/prediction_of_day/{valid_uuid}")
            
            assert response.status_code == 200
            data = response.json()
            
            # Verify structure - should only have 3 fields
            assert "type" in data
            assert "label" in data
            assert "probability" in data
            assert len(data) == 3
            
            # Verify content
            assert data["type"] == "mood_state"
            assert data["label"] is not None
            assert data["label"] != "Dados insuficientes"
            
            # Verify probability is valid and normalized
            assert data["probability"] is not None
            assert isinstance(data["probability"], (int, float))
            assert 0 <= data["probability"] <= 1
            
            # Label should be one of the mood states
            assert data["label"] in ["Eutimia", "Mania", "Depressão", "Estado Misto"]


def test_prediction_of_day_endpoint_probability_normalization():
    """Test that probabilities are properly normalized and subnormals handled"""
    valid_uuid = "323e4567-e89b-12d3-a456-426614174002"
    # Mock check-in data with extreme values
    checkin_data = {
        "id": "test-checkin-extreme",
        "user_id": valid_uuid,
        "checkin_date": "2024-01-15T10:30:00Z",
        "hoursSlept": 10,
        "sleepQuality": 10,
        "energyLevel": 10,
        "depressedMood": 0,
        "anxietyStress": 0,
        "medicationAdherence": 1,
        "medicationTiming": 1,
        "compulsionIntensity": 0
    }
    
    mock_client = create_mock_supabase_client([checkin_data])
    
    def mock_acreate_client(*args, **kwargs):
        return mock_client
    
    with patch.dict(os.environ, {
        "SUPABASE_URL": "https://test.supabase.co",
        "SUPABASE_SERVICE_KEY": "test-key"
    }):
        with patch("api.dependencies.acreate_client", side_effect=mock_acreate_client):
            # Force reset of cached client to ensure mock is used
            import api.dependencies
            api.dependencies._cached_anon_client = None

            response = client.get(f"/data/prediction_of_day/{valid_uuid}")
            
            assert response.status_code == 200
            data = response.json()
            
            # Probability must be in range [0, 1]
            assert 0.0 <= data["probability"] <= 1.0
            
            # If probability is very small, it should be exactly 0
            # (testing subnormal handling)
            if data["probability"] < 1e-6:
                assert data["probability"] == 0.0


def test_prediction_of_day_endpoint_missing_env_vars():
    """Test prediction_of_day endpoint with missing environment variables"""
    test_user_id = "723e4567-e89b-12d3-a456-426614174007"
    with patch.dict(os.environ, {}, clear=True):
        # Force reset of cached client to ensure it tries to create new one and fails
        import api.dependencies
        api.dependencies._cached_anon_client = None

        response = client.get(f"/data/prediction_of_day/{test_user_id}")
        
        # Should return 500 with clear error message
        assert response.status_code == 500
        detail = response.json()["detail"].lower()
        assert "supabase" in detail or "configuração" in detail


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
