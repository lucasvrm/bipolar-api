# tests/test_uuid_validation.py
"""
Tests for UUID validation in API endpoints.
"""
import pytest
import sys
import os
from unittest.mock import AsyncMock, MagicMock, patch

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


# Test cases for /data/latest_checkin/{user_id}
def test_latest_checkin_invalid_uuid_returns_400():
    """Test that invalid UUID returns 400 Bad Request"""
    with patch.dict(os.environ, {
        "SUPABASE_URL": "https://test.supabase.co",
        "SUPABASE_SERVICE_KEY": "test-key"
    }):
        # Test various invalid UUID formats
        invalid_uuids = [
            "not-a-uuid",
            "12345",
            "invalid-uuid-format",
            "123e4567-e89b-12d3-a456", # incomplete UUID
            "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx", # invalid characters
        ]
        
        for invalid_uuid in invalid_uuids:
            response = client.get(f"/data/latest_checkin/{invalid_uuid}")
            assert response.status_code == 400, f"Expected 400 for invalid UUID: {invalid_uuid}"
            assert "Invalid UUID format" in response.json()["detail"]
            assert "user_id" in response.json()["detail"]


def test_latest_checkin_valid_uuid_calls_supabase():
    """Test that valid UUID successfully calls Supabase"""
    valid_uuid = "123e4567-e89b-12d3-a456-426614174000"
    
    checkin_data = {
        "id": "checkin-123",
        "user_id": valid_uuid,
        "checkin_date": "2024-01-15T10:30:00Z",
        "hoursSlept": 7.5,
        "sleepQuality": 8
    }
    
    mock_client = create_mock_supabase_client([checkin_data])
    
    async def mock_acreate_client(*args, **kwargs):
        return mock_client
    
    with patch.dict(os.environ, {
        "SUPABASE_URL": "https://test.supabase.co",
        "SUPABASE_SERVICE_KEY": "test-key"
    }):
        with patch("api.dependencies.acreate_client", side_effect=mock_acreate_client):
            response = client.get(f"/data/latest_checkin/{valid_uuid}")
            
            # Should succeed and return data
            assert response.status_code == 200
            data = response.json()
            assert data["user_id"] == valid_uuid
            assert data["id"] == "checkin-123"


# Test cases for /data/predictions/{user_id}
def test_predictions_invalid_uuid_returns_400():
    """Test that invalid UUID returns 400 Bad Request"""
    with patch.dict(os.environ, {
        "SUPABASE_URL": "https://test.supabase.co",
        "SUPABASE_SERVICE_KEY": "test-key"
    }):
        # Test various invalid UUID formats
        invalid_uuids = [
            "not-a-uuid",
            "12345",
            "invalid-uuid-format",
            "123e4567-e89b-12d3-a456", # incomplete UUID
            "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx", # invalid characters
        ]
        
        for invalid_uuid in invalid_uuids:
            response = client.get(f"/data/predictions/{invalid_uuid}")
            assert response.status_code == 400, f"Expected 400 for invalid UUID: {invalid_uuid}"
            assert "Invalid UUID format" in response.json()["detail"]
            assert "user_id" in response.json()["detail"]


def test_predictions_valid_uuid_calls_supabase():
    """Test that valid UUID successfully calls Supabase"""
    valid_uuid = "123e4567-e89b-12d3-a456-426614174000"
    
    checkin_data = {
        "id": "checkin-123",
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
    
    async def mock_acreate_client(*args, **kwargs):
        return mock_client
    
    with patch.dict(os.environ, {
        "SUPABASE_URL": "https://test.supabase.co",
        "SUPABASE_SERVICE_KEY": "test-key"
    }):
        with patch("api.dependencies.acreate_client", side_effect=mock_acreate_client):
            response = client.get(f"/data/predictions/{valid_uuid}")
            
            # Should succeed
            assert response.status_code == 200
            data = response.json()
            assert data["user_id"] == valid_uuid
            assert "predictions" in data
            assert len(data["predictions"]) == 5  # All prediction types


def test_predictions_valid_uuid_with_query_params():
    """Test that valid UUID with query parameters works correctly"""
    valid_uuid = "123e4567-e89b-12d3-a456-426614174000"
    
    checkin_data = {
        "id": "checkin-123",
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
    
    async def mock_acreate_client(*args, **kwargs):
        return mock_client
    
    with patch.dict(os.environ, {
        "SUPABASE_URL": "https://test.supabase.co",
        "SUPABASE_SERVICE_KEY": "test-key"
    }):
        with patch("api.dependencies.acreate_client", side_effect=mock_acreate_client):
            response = client.get(
                f"/data/predictions/{valid_uuid}?types=mood_state&window_days=7"
            )
            
            # Should succeed
            assert response.status_code == 200
            data = response.json()
            assert data["user_id"] == valid_uuid
            assert data["window_days"] == 7
            assert len(data["predictions"]) == 1
            assert data["predictions"][0]["type"] == "mood_state"


# Test edge case: UUID-like strings that are not valid
def test_uuid_edge_cases():
    """Test edge cases for UUID validation"""
    with patch.dict(os.environ, {
        "SUPABASE_URL": "https://test.supabase.co",
        "SUPABASE_SERVICE_KEY": "test-key"
    }):
        edge_cases = [
            "",  # empty string
            " ",  # whitespace
        ]
        
        # Empty and whitespace should return 400
        for test_case in edge_cases:
            response = client.get(f"/data/predictions/{test_case}")
            assert response.status_code in [400, 404], f"Expected 400 or 404 for: '{test_case}'"
        
        # Nil UUID has valid format, so should pass validation and return 200 with empty predictions
        mock_client = create_mock_supabase_client([])
        
        async def mock_acreate_client(*args, **kwargs):
            return mock_client
        
        with patch("api.dependencies.acreate_client", side_effect=mock_acreate_client):
            response = client.get(f"/data/predictions/00000000-0000-0000-0000-000000000000")
            # Should pass validation and return successful response with no predictions
            assert response.status_code == 200


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
