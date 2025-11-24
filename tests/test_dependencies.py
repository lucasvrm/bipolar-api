"""
Tests for api/dependencies.py
"""
import os
import pytest
import threading
import time
from unittest.mock import patch, MagicMock, AsyncMock
from fastapi import HTTPException
from api.dependencies import (
    verify_admin_authorization,
    get_supabase_anon_client,
    get_supabase_anon_auth_client,
    get_supabase_service_role_client,
    get_admin_emails,
    reset_caches_for_testing
)

# Tests updated to work with sync client


@pytest.fixture(autouse=True)
def reset_dependency_caches():
    """Fixture to reset all dependency caches before each test."""
    reset_caches_for_testing()
    yield
    reset_caches_for_testing()


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
        assert "inválido ou expirado" in exc_info.value.detail.lower()


def test_thread_safe_anon_client_initialization():
    """Test that concurrent calls to get_supabase_anon_client are thread-safe."""
    call_count = [0]
    lock = threading.Lock()
    clients = []
    
    def mock_create_client(url, key, options=None):
        """Mock that simulates slow client creation"""
        with lock:
            call_count[0] += 1
        time.sleep(0.01)  # Simulate slow initialization
        return MagicMock()
    
    # Mock environment variables
    with patch.dict(os.environ, {
        'SUPABASE_URL': 'https://test.supabase.co',
        'SUPABASE_ANON_KEY': 'a' * 150  # Long enough to pass validation
    }):
        with patch("api.dependencies.acreate_client", side_effect=mock_create_client):
            # Create multiple threads that will call get_supabase_anon_client concurrently
            threads = []
            for _ in range(10):
                def get_client():
                    client = get_supabase_anon_client()
                    clients.append(client)
                
                thread = threading.Thread(target=get_client)
                threads.append(thread)
                thread.start()
            
            # Wait for all threads to complete
            for thread in threads:
                thread.join()
    
    # Verify that create_client was called only once (double-checked locking worked)
    assert call_count[0] == 1, f"Expected 1 client creation, got {call_count[0]}"
    
    # Verify all threads got the same client instance
    assert len(set(id(c) for c in clients)) == 1, "All threads should get the same client instance"


def test_thread_safe_service_client_initialization():
    """Test that concurrent calls to get_supabase_service_role_client are thread-safe."""
    call_count = [0]
    lock = threading.Lock()
    clients = []
    
    def mock_create_client(url, key, options=None):
        """Mock that simulates slow client creation"""
        with lock:
            call_count[0] += 1
        time.sleep(0.01)  # Simulate slow initialization
        return MagicMock()
    
    # Mock environment variables
    with patch.dict(os.environ, {
        'SUPABASE_URL': 'https://test.supabase.co',
        'SUPABASE_SERVICE_KEY': 's' * 200  # Long enough to pass validation
    }):
        with patch("api.dependencies.acreate_client", side_effect=mock_create_client):
            # Create multiple threads that will call get_supabase_service_role_client concurrently
            threads = []
            for _ in range(10):
                def get_client():
                    client = get_supabase_service_role_client()
                    clients.append(client)
                
                thread = threading.Thread(target=get_client)
                threads.append(thread)
                thread.start()
            
            # Wait for all threads to complete
            for thread in threads:
                thread.join()
    
    # Verify that create_client was called only once (double-checked locking worked)
    assert call_count[0] == 1, f"Expected 1 client creation, got {call_count[0]}"
    
    # Verify all threads got the same client instance
    assert len(set(id(c) for c in clients)) == 1, "All threads should get the same client instance"


def test_thread_safe_admin_emails_initialization():
    """Test that concurrent calls to get_admin_emails are thread-safe."""
    email_sets = []
    
    # Mock environment variables
    with patch.dict(os.environ, {
        'ADMIN_EMAILS': 'admin1@test.com,admin2@test.com,admin3@test.com'
    }):
        # Create multiple threads that will call get_admin_emails concurrently
        threads = []
        for _ in range(10):
            def get_emails():
                emails = get_admin_emails()
                email_sets.append(emails)
            
            thread = threading.Thread(target=get_emails)
            threads.append(thread)
            thread.start()
        
        # Wait for all threads to complete
        for thread in threads:
            thread.join()
    
    # Verify all threads got the same set instance
    assert len(set(id(e) for e in email_sets)) == 1, "All threads should get the same email set instance"
    
    # Verify the content is correct
    assert email_sets[0] == {'admin1@test.com', 'admin2@test.com', 'admin3@test.com'}


def test_get_supabase_anon_client_is_alias():
    """Test that get_supabase_anon_client returns the same as get_supabase_anon_auth_client."""
    with patch.dict(os.environ, {
        'SUPABASE_URL': 'https://test.supabase.co',
        'SUPABASE_ANON_KEY': 'a' * 150
    }):
        with patch("api.dependencies.acreate_client", return_value=MagicMock()):
            client1 = get_supabase_anon_client()
            client2 = get_supabase_anon_auth_client()
            
            # Both should return the same cached instance
            assert client1 is client2


