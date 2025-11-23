"""
Tests for account management endpoints (deletion and data export).
"""
import pytest
import sys
import os
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timedelta, timezone

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from fastapi.testclient import TestClient
from main import app

client = TestClient(app)


class MockSupabaseResponse:
    """Mock response from Supabase"""
    def __init__(self, data, count=None):
        self.data = data
        self.count = count


class MockUser:
    """Mock user object"""
    def __init__(self, user_id, email="test@example.com"):
        self.id = user_id
        self.email = email
        self.user_metadata = {}


class MockUserResponse:
    """Mock user response"""
    def __init__(self, user):
        self.user = user


def create_mock_supabase_client(return_data=None, auth_user=None):
    """Create a mock Supabase client"""
    mock_client = MagicMock()
    
    if return_data is None:
        return_data = []
    
    def mock_execute():
        return MockSupabaseResponse(return_data)
    
    # Create generic chain that works for all operations
    def create_chain():
        mock_method = MagicMock()
        
        # Support various chain methods
        for method in ['execute', 'upsert', 'delete', 'eq', 'select', 'update', 'lte', 'is_', 'insert']:
            if method == 'execute':
                setattr(mock_method, method, mock_execute)
            else:
                setattr(mock_method, method, MagicMock(return_value=mock_method))
        
        return mock_method
    
    mock_client.table = MagicMock(return_value=create_chain())
    
    # Mock auth
    mock_auth = MagicMock()
    
    if auth_user:
        def mock_get_user(token):
            return MockUserResponse(auth_user)
    else:
        def mock_get_user(token):
            return MockUserResponse(MockUser("test-user-id"))
    
    mock_auth.get_user = mock_get_user
    mock_client.auth = mock_auth
    
    return mock_client


# ===== Export Tests =====

def test_export_requires_auth():
    """Test that export endpoint requires authorization"""
    with patch.dict(os.environ, {
        "SUPABASE_URL": "https://test.supabase.co",
        "SUPABASE_SERVICE_KEY": "test-service-key"
   ,
        "SUPABASE_ANON_KEY": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    }):
        response = client.post("/account/export")
        
        assert response.status_code == 401
        assert "Authorization required" in response.json()["detail"]


def test_export_patient_data():
    """Test exporting patient data"""
    test_user_id = "123e4567-e89b-12d3-a456-426614174000"
    
    profile_data = [{
        "id": test_user_id,
        "email": "patient@example.com",
        "role": "patient",
        "is_admin": False,
        "created_at": "2024-01-01T00:00:00Z"
    }]
    
    mock_client = create_mock_supabase_client(
        return_data=profile_data,
        auth_user=MockUser(test_user_id, "patient@example.com")
    )
    
    # Setup different responses for different tables
    def mock_table(table_name):
        chain = MagicMock()
        
        if table_name == 'profiles':
            data = profile_data
        elif table_name == 'check_ins':
            data = [{"id": "check1", "user_id": test_user_id, "checkin_date": "2024-01-01"}]
        elif table_name == 'crisis_plan':
            data = []
        else:
            data = []
        
        def mock_execute():
            return MockSupabaseResponse(data)
        
        for method in ['execute', 'eq', 'select', 'insert']:
            if method == 'execute':
                setattr(chain, method, mock_execute)
            else:
                setattr(chain, method, MagicMock(return_value=chain))
        
        return chain
    
    mock_client.table = mock_table
    
    def mock_client_factory(*args, **kwargs):
        return mock_client
    
    with patch.dict(os.environ, {
        "SUPABASE_URL": "https://test.supabase.co",
        "SUPABASE_SERVICE_KEY": "test-service-key"
   ,
        "SUPABASE_ANON_KEY": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    }):
        with patch("api.dependencies.get_supabase_anon_auth_client", side_effect=mock_client_factory):
            response = client.post(
                "/account/export",
                headers={"Authorization": "Bearer valid-token"}
            )
            
            assert response.status_code == 200
            assert response.headers['content-type'] == 'application/zip'


# ===== Delete Request Tests =====

def test_delete_request_requires_auth():
    """Test that delete request requires authorization"""
    with patch.dict(os.environ, {
        "SUPABASE_URL": "https://test.supabase.co",
        "SUPABASE_SERVICE_KEY": "test-service-key"
   ,
        "SUPABASE_ANON_KEY": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    }):
        response = client.post("/account/delete-request")
        
        assert response.status_code == 401


def test_delete_request_therapist_with_patients():
    """Test that therapist with active patients cannot delete account"""
    test_user_id = "123e4567-e89b-12d3-a456-426614174000"
    
    profile_data = [{
        "id": test_user_id,
        "email": "therapist@example.com",
        "role": "therapist"
    }]
    
    mock_client = create_mock_supabase_client(
        return_data=profile_data,
        auth_user=MockUser(test_user_id, "therapist@example.com")
    )
    
    # Setup different responses for different tables
    call_count = {'count': 0}
    
    def mock_table(table_name):
        chain = MagicMock()
        
        if table_name == 'profiles':
            data = profile_data
        elif table_name == 'therapist_patients' and call_count['count'] == 0:
            call_count['count'] += 1
            # Return active patients
            data = [
                {"therapist_id": test_user_id, "patient_id": "patient1", "status": "active"},
                {"therapist_id": test_user_id, "patient_id": "patient2", "status": "active"}
            ]
        else:
            data = []
        
        def mock_execute():
            return MockSupabaseResponse(data, count=len(data))
        
        for method in ['execute', 'eq', 'select', 'insert', 'update']:
            if method == 'execute':
                setattr(chain, method, mock_execute)
            else:
                setattr(chain, method, MagicMock(return_value=chain))
        
        return chain
    
    mock_client.table = mock_table
    
    def mock_client_factory(*args, **kwargs):
        return mock_client
    
    with patch.dict(os.environ, {
        "SUPABASE_URL": "https://test.supabase.co",
        "SUPABASE_SERVICE_KEY": "test-service-key"
   ,
        "SUPABASE_ANON_KEY": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    }):
        with patch("api.dependencies.get_supabase_anon_auth_client", side_effect=mock_client_factory):
            response = client.post(
                "/account/delete-request",
                headers={"Authorization": "Bearer valid-token"}
            )
            
            assert response.status_code == 403
            assert "paciente(s) ativo(s)" in response.json()["detail"]


def test_delete_request_patient_success():
    """Test successful deletion request for patient"""
    test_user_id = "123e4567-e89b-12d3-a456-426614174000"
    
    profile_data = [{
        "id": test_user_id,
        "email": "patient@example.com",
        "role": "patient"
    }]
    
    mock_client = create_mock_supabase_client(
        return_data=profile_data,
        auth_user=MockUser(test_user_id, "patient@example.com")
    )
    
    # Setup different responses for different tables
    def mock_table(table_name):
        chain = MagicMock()
        
        if table_name == 'profiles' and hasattr(chain, '_is_select'):
            # Second call to get token
            data = [{"deletion_token": "new-token-uuid"}]
        elif table_name == 'profiles':
            data = profile_data
        elif table_name == 'therapist_patients':
            # Patient has a therapist
            data = [{"therapist_id": "therapist-id", "patient_id": test_user_id, "status": "active"}]
        else:
            data = []
        
        def mock_execute():
            return MockSupabaseResponse(data)
        
        for method in ['execute', 'eq', 'select', 'insert', 'update']:
            if method == 'execute':
                setattr(chain, method, mock_execute)
            else:
                if method == 'select':
                    chain._is_select = True
                setattr(chain, method, MagicMock(return_value=chain))
        
        return chain
    
    mock_client.table = mock_table
    
    def mock_client_factory(*args, **kwargs):
        return mock_client
    
    with patch.dict(os.environ, {
        "SUPABASE_URL": "https://test.supabase.co",
        "SUPABASE_SERVICE_KEY": "test-service-key"
   ,
        "SUPABASE_ANON_KEY": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    }):
        with patch("api.dependencies.get_supabase_anon_auth_client", side_effect=mock_client_factory):
            response = client.post(
                "/account/delete-request",
                headers={"Authorization": "Bearer valid-token"}
            )
            
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "success"
            assert "deletion_scheduled_at" in data
            assert "deletion_date" in data


# ===== Undo Delete Tests =====

def test_undo_delete_invalid_token():
    """Test undo delete with invalid token"""
    mock_client = create_mock_supabase_client(return_data=[])
    
    def mock_client_factory(*args, **kwargs):
        return mock_client
    
    with patch.dict(os.environ, {
        "SUPABASE_URL": "https://test.supabase.co",
        "SUPABASE_SERVICE_KEY": "test-service-key"
   ,
        "SUPABASE_ANON_KEY": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    }):
        with patch("api.dependencies.get_supabase_anon_auth_client", side_effect=mock_client_factory):
            response = client.post(
                "/account/undo-delete",
                json={"token": "123e4567-e89b-12d3-a456-426614174000"}
            )
            
            assert response.status_code == 404
            assert "inválido ou expirado" in response.json()["detail"]


def test_undo_delete_success():
    """Test successful undo of deletion"""
    test_user_id = "123e4567-e89b-12d3-a456-426614174000"
    test_token = "abc12345-e89b-12d3-a456-426614174999"
    
    # Future deletion date (still in grace period)
    future_date = (datetime.now(timezone.utc) + timedelta(days=10)).isoformat()
    
    profile_data = [{
        "id": test_user_id,
        "email": "patient@example.com",
        "deletion_scheduled_at": future_date
    }]
    
    mock_client = create_mock_supabase_client(return_data=profile_data)
    
    def mock_client_factory(*args, **kwargs):
        return mock_client
    
    with patch.dict(os.environ, {
        "SUPABASE_URL": "https://test.supabase.co",
        "SUPABASE_SERVICE_KEY": "test-service-key"
   ,
        "SUPABASE_ANON_KEY": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    }):
        with patch("api.dependencies.get_supabase_anon_auth_client", side_effect=mock_client_factory):
            response = client.post(
                "/account/undo-delete",
                json={"token": test_token}
            )
            
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "success"
            assert "cancelada com sucesso" in data["message"]


def test_undo_delete_expired():
    """Test undo delete with expired token (past deletion date)"""
    test_user_id = "123e4567-e89b-12d3-a456-426614174000"
    test_token = "abc12345-e89b-12d3-a456-426614174999"
    
    # Past deletion date (grace period expired)
    past_date = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    
    profile_data = [{
        "id": test_user_id,
        "email": "patient@example.com",
        "deletion_scheduled_at": past_date
    }]
    
    mock_client = create_mock_supabase_client(return_data=profile_data)
    
    def mock_client_factory(*args, **kwargs):
        return mock_client
    
    with patch.dict(os.environ, {
        "SUPABASE_URL": "https://test.supabase.co",
        "SUPABASE_SERVICE_KEY": "test-service-key"
   ,
        "SUPABASE_ANON_KEY": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    }):
        with patch("api.dependencies.get_supabase_anon_auth_client", side_effect=mock_client_factory):
            response = client.post(
                "/account/undo-delete",
                json={"token": test_token}
            )
            
            assert response.status_code == 400
            assert "expirou" in response.json()["detail"]


def test_undo_delete_invalid_uuid():
    """Test undo delete with invalid UUID format"""
    with patch.dict(os.environ, {
        "SUPABASE_URL": "https://test.supabase.co",
        "SUPABASE_SERVICE_KEY": "test-service-key"
   ,
        "SUPABASE_ANON_KEY": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    }):
        response = client.post(
            "/account/undo-delete",
            json={"token": "not-a-valid-uuid"}
        )
        
        assert response.status_code == 400
        assert "Invalid UUID" in response.json()["detail"] or "inválido" in response.json()["detail"]
