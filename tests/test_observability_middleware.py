# tests/test_observability_middleware.py
"""
Tests for observability middleware.
"""
import pytest
import sys
import os
from unittest.mock import patch

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from fastapi.testclient import TestClient
from main import app

client = TestClient(app)


def test_middleware_adds_request_id_header():
    """Test that middleware adds X-Request-ID header to response"""
    response = client.get("/")
    
    assert "X-Request-ID" in response.headers
    # Should be a valid UUID
    request_id = response.headers["X-Request-ID"]
    assert len(request_id) == 36
    assert request_id.count('-') == 4


def test_middleware_adds_response_time_header():
    """Test that middleware adds X-Response-Time header to response"""
    response = client.get("/")
    
    assert "X-Response-Time" in response.headers
    # Should be in format "123.45ms"
    response_time = response.headers["X-Response-Time"]
    assert response_time.endswith("ms")
    assert float(response_time[:-2]) >= 0


def test_middleware_unique_request_ids():
    """Test that each request gets a unique request ID"""
    response1 = client.get("/")
    response2 = client.get("/")
    
    request_id_1 = response1.headers["X-Request-ID"]
    request_id_2 = response2.headers["X-Request-ID"]
    
    assert request_id_1 != request_id_2


def test_middleware_works_with_predictions_endpoint():
    """Test that middleware works correctly with predictions endpoint"""
    test_user_id = "123e4567-e89b-12d3-a456-426614174000"
    
    with patch.dict(os.environ, {
        "SUPABASE_URL": "https://test.supabase.co",
        "SUPABASE_SERVICE_KEY": "test-key"
    }):
        # Mock the supabase client to avoid actual DB calls
        from unittest.mock import MagicMock, AsyncMock
        
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.data = []
        
        def mock_execute():
            return mock_response
        
        chain = MagicMock()
        chain.execute = mock_execute
        chain.limit = MagicMock(return_value=chain)
        chain.order = MagicMock(return_value=chain)
        chain.eq = MagicMock(return_value=chain)
        chain.select = MagicMock(return_value=chain)
        
        mock_client.table = MagicMock(return_value=chain)
        
        def mock_get_client(*args, **kwargs):
            return mock_client
        
        with patch("api.dependencies.acreate_client", side_effect=mock_get_client):
            response = client.get(f"/data/predictions/{test_user_id}")
            
            # Should have observability headers
            assert "X-Request-ID" in response.headers
            assert "X-Response-Time" in response.headers


def test_middleware_works_with_privacy_endpoints():
    """Test that middleware works correctly with privacy endpoints"""
    test_user_id = "123e4567-e89b-12d3-a456-426614174000"
    
    with patch.dict(os.environ, {
        "SUPABASE_URL": "https://test.supabase.co",
        "SUPABASE_SERVICE_KEY": "test-service-key"
    }):
        response = client.get(
            f"/user/{test_user_id}/export",
            headers={"Authorization": "Bearer test-service-key"}
        )
        
        # Should have observability headers even if endpoint fails
        assert "X-Request-ID" in response.headers
        assert "X-Response-Time" in response.headers


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
