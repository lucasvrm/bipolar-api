"""
Tests for api/dependencies.py
"""
import os
import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from fastapi import HTTPException
from api.dependencies import verify_admin_authorization

# Tests updated to work with sync client


@pytest.mark.asyncio
async def test_verify_admin_auth_raises_401_on_invalid_token():
    """Test that verify_admin_authorization raises 401 when token is invalid."""
    
    # Mock the client returned by get_supabase_anon_auth_client
    mock_client = MagicMock()
    mock_auth = MagicMock()
    
    # Mock get_user to raise exception
    mock_auth.get_user.side_effect = Exception("Invalid token signature")
    
    mock_client.auth = mock_auth
    
    # Mock the dependency that returns the client
    with patch("api.dependencies.get_supabase_anon_auth_client", return_value=mock_client):
        with pytest.raises(HTTPException) as exc_info:
            await verify_admin_authorization(authorization="Bearer token")
        
        assert exc_info.value.status_code == 401
        assert "Invalid or expired token" in exc_info.value.detail

