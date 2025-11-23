"""
Tests for authentication flow.

This test suite validates:
1. verify_admin_authorization with valid admin tokens
2. verify_admin_authorization with invalid tokens
3. verify_admin_authorization with non-admin emails
4. Error handling and user-friendly messages
"""

import os
import pytest
from unittest.mock import patch, MagicMock, Mock
from fastapi import HTTPException

from api.dependencies import verify_admin_authorization, get_admin_emails


class TestVerifyAdminAuthorization:
    """Tests for the verify_admin_authorization dependency."""
    
    @pytest.mark.asyncio
    async def test_valid_admin_token_returns_true(self):
        """Test that a valid admin token returns True."""
        # Mock user response
        mock_user = MagicMock()
        mock_user.email = "admin@example.com"
        
        mock_user_resp = MagicMock()
        mock_user_resp.user = mock_user
        
        # Mock client
        mock_client = MagicMock()
        mock_client.auth.get_user.return_value = mock_user_resp
        
        with patch("api.dependencies.get_supabase_anon_auth_client", return_value=mock_client):
            with patch.dict(os.environ, {"ADMIN_EMAILS": "admin@example.com,admin2@test.com"}):
                # Clear cache to pick up new env
                import api.dependencies
                api.dependencies._admin_emails_cache = None
                
                result = await verify_admin_authorization(authorization="Bearer valid-token-here")
                assert result is True
    
    @pytest.mark.asyncio
    async def test_invalid_token_raises_401(self):
        """Test that an invalid token raises 401."""
        # Mock client to raise exception
        mock_client = MagicMock()
        mock_client.auth.get_user.side_effect = Exception("Invalid token signature")
        
        with patch("api.dependencies.get_supabase_anon_auth_client", return_value=mock_client):
            with pytest.raises(HTTPException) as exc_info:
                await verify_admin_authorization(authorization="Bearer invalid-token")
            
            assert exc_info.value.status_code == 401
            assert "inválido ou expirado" in exc_info.value.detail.lower()
    
    @pytest.mark.asyncio
    async def test_missing_bearer_token_raises_401(self):
        """Test that missing bearer token raises 401."""
        with pytest.raises(HTTPException) as exc_info:
            await verify_admin_authorization(authorization=None)
        
        assert exc_info.value.status_code == 401
        assert "autorização" in exc_info.value.detail.lower()
    
    @pytest.mark.asyncio
    async def test_malformed_token_raises_401(self):
        """Test that malformed token (abc.def) raises 401."""
        mock_client = MagicMock()
        mock_client.auth.get_user.side_effect = Exception("JWT malformed")
        
        with patch("api.dependencies.get_supabase_anon_auth_client", return_value=mock_client):
            with pytest.raises(HTTPException) as exc_info:
                await verify_admin_authorization(authorization="Bearer abc.def")
            
            assert exc_info.value.status_code == 401
    
    @pytest.mark.asyncio
    async def test_non_admin_email_raises_403(self):
        """Test that valid token with non-admin email raises 403."""
        # Mock user response with non-admin email
        mock_user = MagicMock()
        mock_user.email = "user@example.com"
        
        mock_user_resp = MagicMock()
        mock_user_resp.user = mock_user
        
        mock_client = MagicMock()
        mock_client.auth.get_user.return_value = mock_user_resp
        
        with patch("api.dependencies.get_supabase_anon_auth_client", return_value=mock_client):
            with patch.dict(os.environ, {"ADMIN_EMAILS": "admin@example.com"}):
                # Clear cache
                import api.dependencies
                api.dependencies._admin_emails_cache = None
                
                with pytest.raises(HTTPException) as exc_info:
                    await verify_admin_authorization(authorization="Bearer valid-token")
                
                assert exc_info.value.status_code == 403
                assert "permissões de administrador" in exc_info.value.detail.lower() or "acesso negado" in exc_info.value.detail.lower()
    
    @pytest.mark.asyncio
    async def test_token_without_email_raises_401(self):
        """Test that token without email raises 401."""
        # Mock user response without email
        mock_user = MagicMock()
        mock_user.email = None
        
        mock_user_resp = MagicMock()
        mock_user_resp.user = mock_user
        
        mock_client = MagicMock()
        mock_client.auth.get_user.return_value = mock_user_resp
        
        with patch("api.dependencies.get_supabase_anon_auth_client", return_value=mock_client):
            with pytest.raises(HTTPException) as exc_info:
                await verify_admin_authorization(authorization="Bearer token-no-email")
            
            assert exc_info.value.status_code == 401
            assert "Token sem email válido" in exc_info.value.detail


class TestAdminEmailsCache:
    """Tests for admin emails caching."""
    
    def test_get_admin_emails_caches_result(self):
        """Test that admin emails are cached."""
        import api.dependencies
        
        with patch.dict(os.environ, {"ADMIN_EMAILS": "admin1@test.com,admin2@test.com"}):
            # Clear cache
            api.dependencies._admin_emails_cache = None
            
            # First call
            emails1 = get_admin_emails()
            assert len(emails1) == 2
            assert "admin1@test.com" in emails1
            
            # Modify env (shouldn't affect cached result)
            os.environ["ADMIN_EMAILS"] = "different@test.com"
            
            # Second call should return cached value
            emails2 = get_admin_emails()
            assert emails1 == emails2
            
            # Clear cache for other tests
            api.dependencies._admin_emails_cache = None
    
    def test_get_admin_emails_normalizes_case(self):
        """Test that email comparison is case-insensitive."""
        import api.dependencies
        
        with patch.dict(os.environ, {"ADMIN_EMAILS": "Admin@Test.COM,user@EXAMPLE.com"}):
            api.dependencies._admin_emails_cache = None
            
            emails = get_admin_emails()
            assert "admin@test.com" in emails
            assert "user@example.com" in emails
            
            # Clear cache
            api.dependencies._admin_emails_cache = None
