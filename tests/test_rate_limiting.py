"""
Tests for rate limiting functionality.

These tests verify that rate limiting is properly enforced on API endpoints
to prevent excessive requests and protect the server from abuse.
"""
import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock
import os

# Set environment variables before importing main
os.environ["SUPABASE_URL"] = "https://test.supabase.co"
os.environ["SUPABASE_SERVICE_KEY"] = "test-key"
# Use memory storage for tests (not Redis)
os.environ["RATE_LIMIT_STORAGE_URI"] = "memory://"
# Set aggressive rate limits for testing
os.environ["RATE_LIMIT_DEFAULT"] = "5/minute"
os.environ["RATE_LIMIT_PREDICTIONS"] = "3/minute"
os.environ["RATE_LIMIT_DATA_ACCESS"] = "3/minute"

from main import app
from api.rate_limiter import limiter


@pytest.fixture
def client():
    """Create a test client for the API."""
    # Reset rate limiter state between tests
    # Note: MemoryStorage doesn't have a global clear, so we create a new client each time
    return TestClient(app)


@pytest.fixture
def mock_supabase():
    """Mock Supabase client to avoid actual database calls."""
    with patch("api.dependencies.get_supabase_client") as mock:
        mock_client = MagicMock()
        # Mock response for check-ins query
        mock_response = MagicMock()
        mock_response.data = [{
            "id": "test-checkin-id",
            "user_id": "test-user-id",
            "checkin_date": "2024-01-01T00:00:00Z",
            "hoursSlept": 7,
            "depressedMood": 3,
            "energyLevel": 5,
            "anxietyStress": 3
        }]
        mock_client.table.return_value.select.return_value.eq.return_value.order.return_value.limit.return_value.execute = MagicMock(return_value=mock_response)
        
        async def get_mock_client():
            return mock_client
        
        mock.return_value = get_mock_client()
        yield mock


def test_rate_limit_on_predictions_endpoint(client, mock_supabase):
    """
    Test that rate limiting is enforced on the predictions endpoint.
    
    Makes more requests than the limit allows and verifies that:
    1. Initial requests succeed (200 OK)
    2. Subsequent requests are rate limited (429 Too Many Requests)
    3. Rate limit response includes appropriate error message
    """
    user_id = "12345678-1234-1234-1234-123456789012"
    endpoint = f"/data/predictions/{user_id}"
    
    # Make requests up to the limit (3/minute for predictions)
    successful_requests = 0
    for i in range(3):
        response = client.get(endpoint)
        if response.status_code == 200:
            successful_requests += 1
    
    assert successful_requests == 3, "Expected 3 successful requests before rate limit"
    
    # Next request should be rate limited
    response = client.get(endpoint)
    assert response.status_code == 429, "Expected 429 Too Many Requests after exceeding limit"
    assert "rate_limit_exceeded" in response.json()["error"]
    assert "Retry-After" in response.headers


def test_rate_limit_on_latest_checkin_endpoint(client, mock_supabase):
    """
    Test that rate limiting is enforced on the latest_checkin endpoint.
    
    Verifies that the data access endpoint respects its configured rate limit.
    """
    user_id = "12345678-1234-1234-1234-123456789012"
    endpoint = f"/data/latest_checkin/{user_id}"
    
    # Make requests up to the limit (3/minute for data access)
    successful_requests = 0
    for i in range(3):
        response = client.get(endpoint)
        if response.status_code == 200:
            successful_requests += 1
    
    assert successful_requests == 3, "Expected 3 successful requests before rate limit"
    
    # Next request should be rate limited
    response = client.get(endpoint)
    assert response.status_code == 429, "Expected 429 Too Many Requests after exceeding limit"
    assert "rate_limit_exceeded" in response.json()["error"]


def test_rate_limit_different_users_independent(client, mock_supabase):
    """
    Test that rate limits are applied independently per user.
    
    Verifies that different users have separate rate limit counters.
    """
    user_id_1 = "12345678-1234-1234-1234-123456789012"
    user_id_2 = "87654321-4321-4321-4321-210987654321"
    
    # User 1 makes requests up to the limit
    for i in range(3):
        response = client.get(f"/data/predictions/{user_id_1}")
        assert response.status_code == 200
    
    # User 1 is now rate limited
    response = client.get(f"/data/predictions/{user_id_1}")
    assert response.status_code == 429
    
    # User 2 should still be able to make requests
    response = client.get(f"/data/predictions/{user_id_2}")
    assert response.status_code == 200, "Different user should have independent rate limit"


def test_rate_limit_response_format(client, mock_supabase):
    """
    Test that rate limit exceeded response has proper format.
    
    Verifies the response includes:
    - Error field with "rate_limit_exceeded"
    - Message field with helpful text
    - Detail field with specifics
    - Retry-After header
    """
    user_id = "12345678-1234-1234-1234-123456789012"
    endpoint = f"/data/predictions/{user_id}"
    
    # Exhaust rate limit
    for i in range(3):
        client.get(endpoint)
    
    # Get rate limited response
    response = client.get(endpoint)
    
    assert response.status_code == 429
    
    json_data = response.json()
    assert "error" in json_data
    assert json_data["error"] == "rate_limit_exceeded"
    assert "message" in json_data
    assert "Too many requests" in json_data["message"]
    assert "detail" in json_data
    
    assert "Retry-After" in response.headers
    assert int(response.headers["Retry-After"]) > 0


def test_rate_limit_prediction_of_day_endpoint(client, mock_supabase):
    """
    Test that rate limiting is enforced on the prediction_of_day endpoint.
    """
    user_id = "12345678-1234-1234-1234-123456789012"
    endpoint = f"/data/prediction_of_day/{user_id}"
    
    # Make requests up to the limit (3/minute for predictions)
    for i in range(3):
        response = client.get(endpoint)
        assert response.status_code == 200
    
    # Next request should be rate limited
    response = client.get(endpoint)
    assert response.status_code == 429


def test_health_check_not_rate_limited(client):
    """
    Test that health check endpoint is not affected by rate limiting.
    
    The root endpoint should always be accessible for monitoring.
    """
    # Make many requests to health check
    for i in range(10):
        response = client.get("/")
        assert response.status_code == 200, "Health check should not be rate limited"
        assert "healthy" in response.json()["status"]
