"""
Tests for data generator retry logic.

Tests verify the UUID generation and retry mechanism for handling duplicates.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import HTTPException
from postgrest.exceptions import APIError


class MockAuthUser:
    """Mock user from auth response"""
    def __init__(self, user_id):
        self.id = user_id


class MockAuthResponse:
    """Mock response from auth.admin.create_user"""
    def __init__(self, user_id):
        self.user = MockAuthUser(user_id)


class MockSupabaseResponse:
    """Mock response from Supabase table operations"""
    def __init__(self, data):
        self.data = data


class TestCreateUserWithRetry:
    """Tests for create_user_with_retry function."""

    @pytest.mark.asyncio
    async def test_successful_user_creation_first_try(self):
        """Test successful user creation on first attempt."""
        from data_generator import create_user_with_retry
        
        mock_client = MagicMock()
        
        # Mock auth response
        mock_auth = MagicMock()
        mock_auth.admin = MagicMock()
        
        async def mock_create_user(*args, **kwargs):
            return MockAuthResponse("test-uuid-123")
        
        mock_auth.admin.create_user = mock_create_user
        mock_client.auth = mock_auth
        
        # Mock table insert
        async def mock_insert_execute():
            return MockSupabaseResponse(data=[{"id": "test-uuid-123"}])
        
        mock_insert_chain = MagicMock()
        mock_insert_chain.execute = mock_insert_execute
        
        mock_table = MagicMock()
        mock_table.insert = MagicMock(return_value=mock_insert_chain)
        
        mock_client.table = MagicMock(return_value=mock_table)
        
        # Call the function
        user_id, email, password = await create_user_with_retry(mock_client, "patient")
        
        # Verify results
        assert user_id == "test-uuid-123"
        assert "@" in email  # Should be a valid email from Faker
        assert len(password) == 20  # Password length as specified

    @pytest.mark.asyncio
    async def test_retry_on_duplicate_error(self):
        """Test retry logic when duplicate UUID is detected."""
        from data_generator import create_user_with_retry
        
        mock_client = MagicMock()
        
        # Mock auth to return different UUIDs
        call_count = [0]
        
        async def mock_create_user(*args, **kwargs):
            call_count[0] += 1
            return MockAuthResponse(f"test-uuid-{call_count[0]}")
        
        mock_auth = MagicMock()
        mock_auth.admin = MagicMock()
        mock_auth.admin.create_user = mock_create_user
        mock_client.auth = mock_auth
        
        # Mock table insert - fail first time, succeed second time
        insert_call_count = [0]
        
        async def mock_insert_execute():
            insert_call_count[0] += 1
            if insert_call_count[0] == 1:
                # First attempt: raise duplicate error
                raise APIError({"message": "duplicate key value violates unique constraint"})
            else:
                # Second attempt: succeed
                return MockSupabaseResponse(data=[{"id": f"test-uuid-{call_count[0]}"}])
        
        mock_insert_chain = MagicMock()
        mock_insert_chain.execute = mock_insert_execute
        
        mock_table = MagicMock()
        mock_table.insert = MagicMock(return_value=mock_insert_chain)
        
        mock_client.table = MagicMock(return_value=mock_table)
        
        # Call the function
        user_id, email, password = await create_user_with_retry(mock_client, "patient", max_retries=3)
        
        # Verify that it succeeded on second attempt
        assert user_id == "test-uuid-2"
        assert insert_call_count[0] == 2  # Should have tried twice

    @pytest.mark.asyncio
    async def test_failure_after_max_retries(self):
        """Test that it fails after max retries are exhausted."""
        from data_generator import create_user_with_retry
        
        mock_client = MagicMock()
        
        # Mock auth
        async def mock_create_user(*args, **kwargs):
            return MockAuthResponse("test-uuid-123")
        
        mock_auth = MagicMock()
        mock_auth.admin = MagicMock()
        mock_auth.admin.create_user = mock_create_user
        mock_client.auth = mock_auth
        
        # Mock table insert - always fail with duplicate error
        async def mock_insert_execute():
            raise APIError({"message": "duplicate key value violates unique constraint"})
        
        mock_insert_chain = MagicMock()
        mock_insert_chain.execute = mock_insert_execute
        
        mock_table = MagicMock()
        mock_table.insert = MagicMock(return_value=mock_insert_chain)
        
        mock_client.table = MagicMock(return_value=mock_table)
        
        # Call the function and expect HTTPException
        with pytest.raises(HTTPException) as exc_info:
            await create_user_with_retry(mock_client, "patient", max_retries=3)
        
        # Verify it's a 500 error about duplicates
        assert exc_info.value.status_code == 500
        assert "duplicate" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    async def test_non_duplicate_error_raised_immediately(self):
        """Test that non-duplicate errors are raised immediately without retry."""
        from data_generator import create_user_with_retry
        
        mock_client = MagicMock()
        
        # Mock auth
        async def mock_create_user(*args, **kwargs):
            return MockAuthResponse("test-uuid-123")
        
        mock_auth = MagicMock()
        mock_auth.admin = MagicMock()
        mock_auth.admin.create_user = mock_create_user
        mock_client.auth = mock_auth
        
        # Mock table insert - fail with non-duplicate error
        async def mock_insert_execute():
            raise APIError({"message": "connection timeout"})
        
        mock_insert_chain = MagicMock()
        mock_insert_chain.execute = mock_insert_execute
        
        mock_table = MagicMock()
        mock_table.insert = MagicMock(return_value=mock_insert_chain)
        
        mock_client.table = MagicMock(return_value=mock_table)
        
        # Call the function and expect HTTPException
        with pytest.raises(HTTPException) as exc_info:
            await create_user_with_retry(mock_client, "patient", max_retries=3)
        
        # Verify it's a 500 error and not about duplicates
        assert exc_info.value.status_code == 500
        assert "connection timeout" in exc_info.value.detail.lower()
