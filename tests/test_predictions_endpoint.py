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
    
    async def mock_execute():
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


async def async_mock_client_factory(data):
    """Async factory that returns a mock client"""
    return create_mock_supabase_client(data)


def test_predictions_endpoint_no_checkins():
    """Test endpoint with user that has no check-ins"""
    test_user_id = "123e4567-e89b-12d3-a456-426614174000"
    mock_client = create_mock_supabase_client([])
    
    async def mock_acreate_client(*args, **kwargs):
        return mock_client
    
    with patch.dict(os.environ, {
        "SUPABASE_URL": "https://test.supabase.co",
        "SUPABASE_SERVICE_KEY": "test-key"
    }):
        with patch("api.dependencies.acreate_client", side_effect=mock_acreate_client):
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
                assert pred["probability"] == 0.0
                assert pred["label"] == "Dados insuficientes"
                assert "No check-in data available" in pred["explanation"]
            
            # Should not have per_checkin data
            assert "per_checkin" not in data


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
    
    async def mock_acreate_client(*args, **kwargs):
        return mock_client
    
    with patch.dict(os.environ, {
        "SUPABASE_URL": "https://test.supabase.co",
        "SUPABASE_SERVICE_KEY": "test-key"
    }):
        with patch("api.dependencies.acreate_client", side_effect=mock_acreate_client):
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
                assert "details" in pred
                assert "model_version" in pred
                assert "explanation" in pred
                assert "source" in pred
                
                # Check for sensitive field in suicidality_risk
                if pred["type"] == "suicidality_risk":
                    assert "sensitive" in pred
                    assert pred["sensitive"] is True
                    assert "disclaimer" in pred
                    assert "resources" in pred


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
    
    async def mock_acreate_client(*args, **kwargs):
        return mock_client
    
    with patch.dict(os.environ, {
        "SUPABASE_URL": "https://test.supabase.co",
        "SUPABASE_SERVICE_KEY": "test-key"
    }):
        with patch("api.dependencies.acreate_client", side_effect=mock_acreate_client):
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
    
    async def mock_acreate_client(*args, **kwargs):
        return mock_client
    
    with patch.dict(os.environ, {
        "SUPABASE_URL": "https://test.supabase.co",
        "SUPABASE_SERVICE_KEY": "test-key"
    }):
        with patch("api.dependencies.acreate_client", side_effect=mock_acreate_client):
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
        assert "Invalid prediction types" in response.json()["detail"]


def test_predictions_endpoint_missing_env_vars():
    """Test endpoint with missing environment variables"""
    test_user_id = "623e4567-e89b-12d3-a456-426614174005"
    with patch.dict(os.environ, {}, clear=True):
        response = client.get(f"/data/predictions/{test_user_id}")
        
        # Should return 500 with clear error message
        assert response.status_code == 500
        detail = response.json()["detail"].lower()
        assert "supabase" in detail or "ambiente" in detail


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

