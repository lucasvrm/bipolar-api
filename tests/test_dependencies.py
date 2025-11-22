"""
Tests for api/dependencies.py
"""
import os
import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from fastapi import HTTPException
from api.dependencies import _create_anon_client, verify_admin_authorization

# Mock acreate_client to avoid real network calls
@pytest.fixture
def mock_acreate_client():
    with patch("api.dependencies.acreate_client", new_callable=AsyncMock) as mock:
        yield mock

@pytest.mark.asyncio
async def test_create_anon_client_strips_whitespace(mock_acreate_client):
    """Test that _create_anon_client strips whitespace from the key."""
    # Create a key that passes length check (100+)
    valid_key_part = "a" * 105
    dirty_key = f"  {valid_key_part}  \n"

    with patch.dict(os.environ, {
        "SUPABASE_URL": "https://example.com",
        "SUPABASE_ANON_KEY": dirty_key
    }):
        await _create_anon_client()

        # Verify acreate_client was called with stripped key
        args, _ = mock_acreate_client.call_args
        # args[0] is url, args[1] is key
        assert args[1] == valid_key_part

@pytest.mark.asyncio
async def test_verify_admin_auth_raises_500_on_invalid_api_key(mock_acreate_client):
    """Test that verify_admin_authorization raises 500 when auth.get_user fails with Invalid API key."""

    # Mock the client returned by get_supabase_anon_auth_client
    mock_client = MagicMock()
    mock_auth = MagicMock()

    # Mock get_user to raise exception
    async def mock_get_user(*args, **kwargs):
        raise Exception('{"message":"Invalid API key","hint":"Double check..."}')

    mock_auth.get_user = mock_get_user
    mock_client.auth = mock_auth

    # Mock the dependency that returns the client
    with patch("api.dependencies.get_supabase_anon_auth_client", return_value=mock_client):
        with pytest.raises(HTTPException) as exc_info:
            await verify_admin_authorization(authorization="Bearer token")

        assert exc_info.value.status_code == 500
        assert "configuration invalid" in exc_info.value.detail
