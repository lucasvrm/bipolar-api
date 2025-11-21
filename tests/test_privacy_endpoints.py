# tests/test_privacy_endpoints.py
"""
Tests for privacy and data operations endpoints.
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


def create_mock_supabase_client(return_data=None):
    """Create a mock Supabase client"""
    mock_client = MagicMock()
    
    if return_data is None:
        return_data = []
    
    async def mock_execute():
        return MockSupabaseResponse(return_data)
    
    # Create generic chain that works for all operations
    def create_chain():
        mock_method = MagicMock()
        
        # Support various chain methods
        for method in ['execute', 'upsert', 'delete', 'eq', 'select', 'limit', 'order']:
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


def test_consent_endpoint_requires_auth():
    """Test that consent endpoint requires authorization"""
    test_user_id = "123e4567-e89b-12d3-a456-426614174000"
    
    with patch.dict(os.environ, {
        "SUPABASE_URL": "https://test.supabase.co",
        "SUPABASE_SERVICE_KEY": "test-service-key"
    }):
        response = client.post(
            f"/user/{test_user_id}/consent",
            json={"analytics": True, "research": False}
        )
        
        assert response.status_code == 401
        assert "Authorization required" in response.json()["detail"]


def test_consent_endpoint_with_auth():
    """Test consent endpoint with proper authorization"""
    test_user_id = "123e4567-e89b-12d3-a456-426614174000"
    consent_record = {
        "user_id": test_user_id,
        "analytics": True,
        "research": False,
        "personalization": True,
        "updated_at": "2024-01-15T10:30:00Z"
    }
    
    mock_client = create_mock_supabase_client([consent_record])
    
    async def mock_client_factory(*args, **kwargs):
        return mock_client
    
    with patch.dict(os.environ, {
        "SUPABASE_URL": "https://test.supabase.co",
        "SUPABASE_SERVICE_KEY": "test-service-key"
    }):
        with patch("api.dependencies.acreate_client", side_effect=mock_client_factory):
            response = client.post(
                f"/user/{test_user_id}/consent",
                json={"analytics": True, "research": False},
                headers={"Authorization": "Bearer test-service-key"}
            )
            
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "success"
            assert "Consent preferences updated" in data["message"]


def test_consent_endpoint_invalid_uuid():
    """Test consent endpoint with invalid UUID"""
    invalid_uuid = "not-a-uuid"
    
    with patch.dict(os.environ, {
        "SUPABASE_URL": "https://test.supabase.co",
        "SUPABASE_SERVICE_KEY": "test-service-key"
    }):
        response = client.post(
            f"/user/{invalid_uuid}/consent",
            json={"analytics": True},
            headers={"Authorization": "Bearer test-token"}
        )
        
        assert response.status_code == 400
        assert "Invalid UUID format" in response.json()["detail"]


def test_consent_endpoint_wrong_token():
    """Test consent endpoint with wrong authorization token"""
    test_user_id = "123e4567-e89b-12d3-a456-426614174000"
    
    with patch.dict(os.environ, {
        "SUPABASE_URL": "https://test.supabase.co",
        "SUPABASE_SERVICE_KEY": "correct-service-key"
    }):
        response = client.post(
            f"/user/{test_user_id}/consent",
            json={"analytics": True},
            headers={"Authorization": "Bearer wrong-token"}
        )
        
        # Should reject invalid tokens
        assert response.status_code == 401
        assert "Invalid authorization token" in response.json()["detail"]


def test_export_endpoint_requires_auth():
    """Test that export endpoint requires authorization"""
    test_user_id = "223e4567-e89b-12d3-a456-426614174001"
    
    with patch.dict(os.environ, {
        "SUPABASE_URL": "https://test.supabase.co",
        "SUPABASE_SERVICE_KEY": "test-service-key"
    }):
        response = client.get(f"/user/{test_user_id}/export")
        
        assert response.status_code == 401


def test_export_endpoint_with_auth():
    """Test export endpoint with proper authorization"""
    test_user_id = "223e4567-e89b-12d3-a456-426614174001"
    
    # Create mock data
    checkin_data = {
        "id": "checkin-1",
        "user_id": test_user_id,
        "checkin_date": "2024-01-15T10:30:00Z",
        "hoursSlept": 7.5
    }
    
    consent_data = {
        "user_id": test_user_id,
        "analytics": True,
        "research": False
    }
    
    # Create a mock client that returns different data based on the table
    mock_client = MagicMock()
    
    async def mock_execute_checkins():
        return MockSupabaseResponse([checkin_data])
    
    async def mock_execute_consent():
        return MockSupabaseResponse([consent_data])
    
    # Track which table is being queried
    table_responses = {
        'check_ins': mock_execute_checkins,
        'user_consent': mock_execute_consent
    }
    
    def mock_table(table_name):
        chain = MagicMock()
        chain.select = MagicMock(return_value=chain)
        chain.eq = MagicMock(return_value=chain)
        chain.execute = table_responses.get(table_name, mock_execute_checkins)
        return chain
    
    mock_client.table = mock_table
    
    async def mock_client_factory(*args, **kwargs):
        return mock_client
    
    with patch.dict(os.environ, {
        "SUPABASE_URL": "https://test.supabase.co",
        "SUPABASE_SERVICE_KEY": "test-service-key"
    }):
        with patch("api.dependencies.acreate_client", side_effect=mock_client_factory):
            response = client.get(
                f"/user/{test_user_id}/export",
                headers={"Authorization": "Bearer test-service-key"}
            )
            
            assert response.status_code == 200
            data = response.json()
            
            # Verify structure
            assert "user_id" in data
            assert data["user_id"] == test_user_id
            assert "export_date" in data
            assert "data" in data
            assert "metadata" in data
            
            # Verify data content
            assert "check_ins" in data["data"]
            assert "consent" in data["data"]
            
            # Verify metadata
            assert "total_check_ins" in data["metadata"]
            assert "format_version" in data["metadata"]


def test_export_endpoint_invalid_uuid():
    """Test export endpoint with invalid UUID"""
    invalid_uuid = "not-a-uuid"
    
    with patch.dict(os.environ, {
        "SUPABASE_URL": "https://test.supabase.co",
        "SUPABASE_SERVICE_KEY": "test-service-key"
    }):
        response = client.get(
            f"/user/{invalid_uuid}/export",
            headers={"Authorization": "Bearer test-token"}
        )
        
        assert response.status_code == 400
        assert "Invalid UUID format" in response.json()["detail"]


def test_erase_endpoint_requires_auth():
    """Test that erase endpoint requires authorization"""
    test_user_id = "323e4567-e89b-12d3-a456-426614174002"
    
    with patch.dict(os.environ, {
        "SUPABASE_URL": "https://test.supabase.co",
        "SUPABASE_SERVICE_KEY": "test-service-key"
    }):
        response = client.post(f"/user/{test_user_id}/erase")
        
        assert response.status_code == 401


def test_erase_endpoint_with_auth():
    """Test erase endpoint with proper authorization"""
    test_user_id = "323e4567-e89b-12d3-a456-426614174002"
    
    # Create mock data for deletion
    deleted_checkins = [{"id": "checkin-1"}, {"id": "checkin-2"}]
    deleted_consent = [{"user_id": test_user_id}]
    
    # Create a mock client
    mock_client = MagicMock()
    
    async def mock_execute_delete_checkins():
        return MockSupabaseResponse(deleted_checkins)
    
    async def mock_execute_delete_consent():
        return MockSupabaseResponse(deleted_consent)
    
    table_responses = {
        'check_ins': mock_execute_delete_checkins,
        'user_consent': mock_execute_delete_consent
    }
    
    def mock_table(table_name):
        chain = MagicMock()
        chain.delete = MagicMock(return_value=chain)
        chain.eq = MagicMock(return_value=chain)
        chain.execute = table_responses.get(table_name, mock_execute_delete_checkins)
        return chain
    
    mock_client.table = mock_table
    
    async def mock_client_factory(*args, **kwargs):
        return mock_client
    
    with patch.dict(os.environ, {
        "SUPABASE_URL": "https://test.supabase.co",
        "SUPABASE_SERVICE_KEY": "test-service-key"
    }):
        with patch("api.dependencies.acreate_client", side_effect=mock_client_factory):
            response = client.post(
                f"/user/{test_user_id}/erase",
                headers={"Authorization": "Bearer test-service-key"}
            )
            
            assert response.status_code == 200
            data = response.json()
            
            # Verify structure
            assert data["status"] == "success"
            assert "erasure completed" in data["message"].lower()
            assert "summary" in data
            
            # Verify summary
            summary = data["summary"]
            assert "user_id" in summary
            assert "erasure_date" in summary
            assert "deleted_records" in summary
            
            # Verify deletion counts
            assert summary["deleted_records"]["check_ins"] == 2
            assert summary["deleted_records"]["consent"] == 1


def test_erase_endpoint_invalid_uuid():
    """Test erase endpoint with invalid UUID"""
    invalid_uuid = "not-a-uuid"
    
    with patch.dict(os.environ, {
        "SUPABASE_URL": "https://test.supabase.co",
        "SUPABASE_SERVICE_KEY": "test-service-key"
    }):
        response = client.post(
            f"/user/{invalid_uuid}/erase",
            headers={"Authorization": "Bearer test-token"}
        )
        
        assert response.status_code == 400
        assert "Invalid UUID format" in response.json()["detail"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
