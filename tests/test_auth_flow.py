"""
Tests for authentication flow with HTTP fallback mechanism.

This test suite validates:
1. verify_admin_authorization with valid admin tokens
2. verify_admin_authorization with invalid tokens
3. verify_admin_authorization with non-admin emails
4. HTTP fallback activation on library errors
5. Fallback function in isolation
"""

import os
import pytest
from unittest.mock import patch, MagicMock, Mock
from fastapi import HTTPException
import urllib.error

from api.dependencies import verify_admin_authorization, get_admin_emails
from api.auth_fallback import supabase_get_user_http, should_use_fallback


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
            assert "Invalid or expired token" in exc_info.value.detail
    
    @pytest.mark.asyncio
    async def test_missing_bearer_token_raises_401(self):
        """Test that missing bearer token raises 401."""
        with pytest.raises(HTTPException) as exc_info:
            await verify_admin_authorization(authorization=None)
        
        assert exc_info.value.status_code == 401
        assert "Missing bearer token" in exc_info.value.detail
    
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
                assert "Not authorized as admin" in exc_info.value.detail
    
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
            assert "Invalid token payload" in exc_info.value.detail
    
    @pytest.mark.asyncio
    async def test_fallback_triggered_on_invalid_api_key_error(self):
        """Test that HTTP fallback is triggered on 'Invalid API key' error."""
        # Mock client to fail with Invalid API key
        mock_client = MagicMock()
        mock_client.auth.get_user.side_effect = Exception("Invalid API key")
        
        # Mock successful HTTP fallback
        mock_user_data = {
            "id": "user-123",
            "email": "admin@example.com"
        }
        
        with patch("api.dependencies.get_supabase_anon_auth_client", return_value=mock_client):
            with patch("api.dependencies.supabase_get_user_http", return_value=mock_user_data):
                with patch.dict(os.environ, {"ADMIN_EMAILS": "admin@example.com"}):
                    # Clear cache
                    import api.dependencies
                    api.dependencies._admin_emails_cache = None
                    
                    result = await verify_admin_authorization(authorization="Bearer token")
                    assert result is True
    
    @pytest.mark.asyncio
    async def test_fallback_failure_raises_401(self):
        """Test that when both library and fallback fail, 401 is raised."""
        # Mock client to fail
        mock_client = MagicMock()
        mock_client.auth.get_user.side_effect = Exception("Invalid API key")
        
        # Mock fallback to also fail
        with patch("api.dependencies.get_supabase_anon_auth_client", return_value=mock_client):
            with patch("api.dependencies.supabase_get_user_http", side_effect=RuntimeError("Auth HTTP error 401")):
                with pytest.raises(HTTPException) as exc_info:
                    await verify_admin_authorization(authorization="Bearer token")
                
                assert exc_info.value.status_code == 401


class TestAuthFallback:
    """Tests for the HTTP fallback authentication mechanism."""
    
    def test_supabase_get_user_http_success(self):
        """Test successful HTTP authentication."""
        mock_response_data = {
            "id": "user-123",
            "email": "test@example.com",
            "aud": "authenticated"
        }
        
        # Mock urllib.request.urlopen
        mock_response = MagicMock()
        mock_response.read.return_value = b'{"id":"user-123","email":"test@example.com","aud":"authenticated"}'
        mock_response.__enter__ = Mock(return_value=mock_response)
        mock_response.__exit__ = Mock(return_value=False)
        
        with patch("urllib.request.urlopen", return_value=mock_response):
            with patch.dict(os.environ, {
                "SUPABASE_URL": "https://test.supabase.co",
                "SUPABASE_ANON_KEY": "test-anon-key"
            }):
                result = supabase_get_user_http("test-token")
                assert result["id"] == "user-123"
                assert result["email"] == "test@example.com"
    
    def test_supabase_get_user_http_missing_config(self):
        """Test that missing config raises RuntimeError."""
        with patch.dict(os.environ, {"SUPABASE_URL": "", "SUPABASE_ANON_KEY": ""}):
            with pytest.raises(RuntimeError) as exc_info:
                supabase_get_user_http("test-token")
            
            assert "Ambiente incompleto" in str(exc_info.value)
    
    def test_supabase_get_user_http_401_error(self):
        """Test that 401 HTTP error is properly handled."""
        mock_error = urllib.error.HTTPError(
            url="https://test.supabase.co/auth/v1/user",
            code=401,
            msg="Unauthorized",
            hdrs={},
            fp=None
        )
        mock_error.read = Mock(return_value=b'{"message":"Invalid token"}')
        
        with patch("urllib.request.urlopen", side_effect=mock_error):
            with patch.dict(os.environ, {
                "SUPABASE_URL": "https://test.supabase.co",
                "SUPABASE_ANON_KEY": "test-anon-key"
            }):
                with pytest.raises(RuntimeError) as exc_info:
                    supabase_get_user_http("invalid-token")
                
                assert "Auth HTTP error 401" in str(exc_info.value)
    
    def test_should_use_fallback_for_invalid_api_key(self):
        """Test that 'Invalid API key' error triggers fallback."""
        error = Exception('{"message":"Invalid API key","hint":"Double check..."}')
        assert should_use_fallback(error) is True
    
    def test_should_use_fallback_for_bad_jwt(self):
        """Test that 'bad_jwt' error triggers fallback."""
        error = Exception("bad_jwt: invalid number of segments")
        assert should_use_fallback(error) is True
    
    def test_should_not_use_fallback_for_legitimate_errors(self):
        """Test that legitimate auth errors don't trigger fallback."""
        error = Exception("JWT expired")
        assert should_use_fallback(error) is False
        
        error2 = Exception("Invalid signature")
        assert should_use_fallback(error2) is False


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
