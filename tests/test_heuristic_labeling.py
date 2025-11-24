"""
Tests for heuristic labeling and safe defaults.
"""
import pytest
import sys
import os
from unittest.mock import MagicMock, patch
import logging

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


def test_methodology_field_included_in_heuristic_predictions():
    """Test that methodology field is included in heuristic predictions"""
    test_user_id = "223e4567-e89b-12d3-a456-426614174001"
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
    
    with patch.dict(os.environ, {
        "SUPABASE_URL": "https://test.supabase.co",
        "SUPABASE_SERVICE_KEY": "test-key"
    }):
        with patch("api.dependencies.acreate_client", return_value=mock_client):
            import api.dependencies
            api.dependencies._cached_anon_client = None

            response = client.get(f"/data/predictions/{test_user_id}")
            
            assert response.status_code == 200
            data = response.json()
            
            # Check that all predictions have methodology field
            for pred in data["predictions"]:
                assert "methodology" in pred, f"Prediction {pred['type']} missing methodology field"
                assert pred["methodology"] == "HEURISTIC_V1_UNVALIDATED", \
                    f"Prediction {pred['type']} has incorrect methodology: {pred.get('methodology')}"


def test_warning_logged_for_heuristic_usage(caplog):
    """Test that warning is logged when heuristic is used"""
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
    
    with patch.dict(os.environ, {
        "SUPABASE_URL": "https://test.supabase.co",
        "SUPABASE_SERVICE_KEY": "test-key"
    }):
        with patch("api.dependencies.acreate_client", return_value=mock_client):
            import api.dependencies
            api.dependencies._cached_anon_client = None

            with caplog.at_level(logging.WARNING):
                response = client.get(f"/data/predictions/{test_user_id}")
            
            assert response.status_code == 200
            
            # Check that warning was logged
            warning_logs = [record for record in caplog.records if record.levelname == "WARNING"]
            heuristic_warnings = [log for log in warning_logs if "Using unvalidated heuristic" in log.message]
            
            # Should have warnings for each prediction type (5 types)
            assert len(heuristic_warnings) >= 1, "Expected at least one warning about heuristic usage"
            
            # Check that user_id is included in warning
            assert any(test_user_id in log.message for log in heuristic_warnings), \
                "Expected user_id in warning message"


def test_insufficient_data_when_critical_fields_missing():
    """Test that prediction returns 'Insufficient Data' when critical fields are missing"""
    test_user_id = "423e4567-e89b-12d3-a456-426614174003"
    # Missing depressedMood and hoursSlept
    checkin_data = {
        "id": "test-checkin-123",
        "user_id": test_user_id,
        "checkin_date": "2024-01-15T10:30:00Z",
        "energyLevel": 5,
        "anxietyStress": 6,
        "medicationAdherence": 1,
        "medicationTiming": 1,
        "compulsionIntensity": 0
    }
    
    mock_client = create_mock_supabase_client([checkin_data])
    
    with patch.dict(os.environ, {
        "SUPABASE_URL": "https://test.supabase.co",
        "SUPABASE_SERVICE_KEY": "test-key"
    }):
        with patch("api.dependencies.acreate_client", return_value=mock_client):
            import api.dependencies
            api.dependencies._cached_anon_client = None

            response = client.get(f"/data/predictions/{test_user_id}")
            
            assert response.status_code == 200
            data = response.json()
            
            # Check predictions that require critical fields
            for pred in data["predictions"]:
                if pred["type"] in ["relapse_risk", "suicidality_risk", "sleep_disturbance_risk", "mood_state"]:
                    # These should have insufficient data
                    assert pred["label"] == "Dados insuficientes", \
                        f"Prediction {pred['type']} should have 'Dados insuficientes' label"
                    assert pred["value"] == 0.0, \
                        f"Prediction {pred['type']} should have value 0.0"
                    assert pred["methodology"] == "HEURISTIC_V1_UNVALIDATED", \
                        f"Prediction {pred['type']} should still have methodology marked"


def test_relapse_risk_requires_sleep_and_mood():
    """Test that relapse_risk returns insufficient data when sleep or mood is missing"""
    test_user_id = "523e4567-e89b-12d3-a456-426614174004"
    # Missing hoursSlept
    checkin_data = {
        "id": "test-checkin-123",
        "user_id": test_user_id,
        "checkin_date": "2024-01-15T10:30:00Z",
        "depressedMood": 4,
        "energyLevel": 5,
        "anxietyStress": 6,
    }
    
    mock_client = create_mock_supabase_client([checkin_data])
    
    with patch.dict(os.environ, {
        "SUPABASE_URL": "https://test.supabase.co",
        "SUPABASE_SERVICE_KEY": "test-key"
    }):
        with patch("api.dependencies.acreate_client", return_value=mock_client):
            import api.dependencies
            api.dependencies._cached_anon_client = None

            response = client.get(f"/data/predictions/{test_user_id}?types=relapse_risk")
            
            assert response.status_code == 200
            data = response.json()
            
            relapse_pred = data["predictions"][0]
            assert relapse_pred["type"] == "relapse_risk"
            assert relapse_pred["label"] == "Dados insuficientes"
            assert relapse_pred["value"] == 0.0
            assert relapse_pred["methodology"] == "HEURISTIC_V1_UNVALIDATED"


def test_suicidality_risk_requires_mood():
    """Test that suicidality_risk returns insufficient data when mood is missing"""
    test_user_id = "623e4567-e89b-12d3-a456-426614174005"
    # Missing depressedMood
    checkin_data = {
        "id": "test-checkin-123",
        "user_id": test_user_id,
        "checkin_date": "2024-01-15T10:30:00Z",
        "hoursSlept": 6.5,
        "energyLevel": 5,
        "anxietyStress": 6,
    }
    
    mock_client = create_mock_supabase_client([checkin_data])
    
    with patch.dict(os.environ, {
        "SUPABASE_URL": "https://test.supabase.co",
        "SUPABASE_SERVICE_KEY": "test-key"
    }):
        with patch("api.dependencies.acreate_client", return_value=mock_client):
            import api.dependencies
            api.dependencies._cached_anon_client = None

            response = client.get(f"/data/predictions/{test_user_id}?types=suicidality_risk")
            
            assert response.status_code == 200
            data = response.json()
            
            suicidality_pred = data["predictions"][0]
            assert suicidality_pred["type"] == "suicidality_risk"
            assert suicidality_pred["label"] == "Dados insuficientes"
            assert suicidality_pred["value"] == 0.0
            assert suicidality_pred["methodology"] == "HEURISTIC_V1_UNVALIDATED"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
