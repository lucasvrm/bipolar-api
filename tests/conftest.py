"""
Pytest configuration and fixtures for the Bipolar API tests.

This file provides shared fixtures and configuration for all tests,
including proper mocking of external dependencies like Supabase.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock
from fastapi.testclient import TestClient
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

# Import app after setting env vars
from main import app


class MockQueryBuilder:
    """Mock for the Supabase query builder that supports method chaining."""
    
    def __init__(self, data=None):
        self.data = data or []
        
    def select(self, *args, **kwargs):
        return self
    
    def eq(self, *args, **kwargs):
        return self
    
    def order(self, *args, **kwargs):
        return self
    
    def limit(self, *args, **kwargs):
        return self
    
    async def execute(self):
        """Return the mocked response."""
        mock_response = MagicMock()
        mock_response.data = self.data
        return mock_response
    
    def __await__(self):
        """Make the entire chain awaitable."""
        return self.execute().__await__()


@pytest.fixture
def mock_supabase():
    """
    Mock Supabase client to prevent real API calls during tests.
    
    This fixture properly mocks the async Supabase client and its methods
    to avoid network calls and DNS resolution attempts.
    
    Returns an AsyncMock that simulates the Supabase client with proper
    query builder chain methods.
    """
    # Create a proper AsyncMock for the Supabase client
    mock_client = AsyncMock()
    
    # Mock data to return
    mock_data = [{
        "id": "test-checkin-id",
        "user_id": "test-user-id",
        "checkin_date": "2024-01-01T00:00:00Z",
        "hoursSlept": 7,
        "depressedMood": 3,
        "energyLevel": 5,
        "anxietyStress": 3
    }]
    
    # Mock the table method to return our custom query builder
    def mock_table(*args, **kwargs):
        return MockQueryBuilder(data=mock_data)
    
    mock_client.table = mock_table
    
    return mock_client


@pytest.fixture
def client(mock_supabase):
    """
    Create a test client for the API with mocked Supabase dependency.
    
    This fixture ensures consistent mocking and rate limiter cleanup.
    Use this fixture in tests that need Supabase mocking and/or rate limiter reset.
    """
    from api.dependencies import get_supabase_client
    from api.rate_limiter import limiter
    
    # Clear rate limiter counters before each test
    # This ensures each test starts with a clean slate
    limiter._storage.storage.clear()
    
    # Clear any previous dependency overrides
    app.dependency_overrides.clear()
    
    # Override the dependency to return our mock
    async def override_get_supabase_client():
        return mock_supabase
    
    app.dependency_overrides[get_supabase_client] = override_get_supabase_client
    
    # Create test client
    test_client = TestClient(app)
    
    yield test_client
    
    # Clean up dependency overrides after the test so other tests can use their own mocks
    app.dependency_overrides.clear()
