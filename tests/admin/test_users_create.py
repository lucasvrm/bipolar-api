"""
Tests for /api/admin/users/create endpoint.
Validates idempotent user creation and source field handling.
"""
import pytest
import uuid
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    """Create test client with rate limiting disabled."""
    from main import app
    app.state.limiter.enabled = False
    yield TestClient(app)
    app.state.limiter.enabled = True


class MockUser:
    """Mock Supabase User object"""
    def __init__(self, email, user_id=None):
        self.id = user_id or str(uuid.uuid4())
        self.email = email
        self.user_metadata = {"role": "admin"}


class MockUserResponse:
    """Mock UserResponse from Supabase auth.get_user()"""
    def __init__(self, user):
        self.user = user


class MockAuthResponse:
    """Mock response from Supabase auth.admin.create_user()"""
    def __init__(self, user_id):
        self.user = MagicMock()
        self.user.id = user_id
        self.user.email = "test@example.com"


class MockSupabaseResponse:
    """Mock response from Supabase queries"""
    def __init__(self, data, count=None):
        self.data = data
        self.count = count


def create_mock_supabase():
    """Create a mock Supabase client for testing"""
    mock_client = MagicMock()
    
    # Mock auth.get_user for admin verification
    admin_user = MockUser("admin@example.com")
    mock_client.auth.get_user.return_value = MockUserResponse(admin_user)
    
    # Mock auth.admin.create_user
    def mock_create_user(user_data):
        user_id = str(uuid.uuid4())
        return MockAuthResponse(user_id)
    
    mock_client.auth.admin.create_user = mock_create_user
    
    # Mock table operations
    def create_chain():
        chain = MagicMock()
        chain.select.return_value = chain
        chain.eq.return_value = chain
        chain.update.return_value = chain
        chain.insert.return_value = chain
        chain.execute.return_value = MockSupabaseResponse([])
        return chain
    
    mock_client.table.return_value = create_chain()
    
    return mock_client


def test_create_user_success(client):
    """Test successful user creation"""
    with patch("api.dependencies.get_supabase_service_role_client") as mock_get_supabase, \
         patch("api.dependencies.get_supabase_anon_auth_client") as mock_get_anon:
        
        mock_service = create_mock_supabase()
        mock_anon = create_mock_supabase()
        
        mock_get_supabase.return_value = mock_service
        mock_get_anon.return_value = mock_anon
        
        # Mock profile check (no existing user)
        mock_service.table.return_value.select.return_value.eq.return_value.execute.return_value = MockSupabaseResponse([])
        
        # Mock profile update (success)
        updated_profile = [{"id": "test-id", "email": "newuser@example.com", "role": "patient"}]
        mock_service.table.return_value.update.return_value.eq.return_value.execute.return_value = MockSupabaseResponse(updated_profile)
        
        response = client.post(
            "/api/admin/users/create",
            json={
                "email": "newuser@example.com",
                "password": "SecurePass123!",
                "role": "patient",
                "full_name": "New User"
            },
            headers={"Authorization": "Bearer test-token"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert "user_id" in data
        assert data["email"] == "newuser@example.com"
        assert data["role"] == "patient"


def test_create_user_idempotent(client):
    """Test idempotent behavior - creating user with existing email returns existing user"""
    with patch("api.dependencies.get_supabase_service_role_client") as mock_get_supabase, \
         patch("api.dependencies.get_supabase_anon_auth_client") as mock_get_anon:
        
        mock_service = create_mock_supabase()
        mock_anon = create_mock_supabase()
        
        mock_get_supabase.return_value = mock_service
        mock_get_anon.return_value = mock_anon
        
        # Mock existing user
        existing_user_id = str(uuid.uuid4())
        existing_profile = [{
            "id": existing_user_id,
            "email": "existing@example.com",
            "role": "patient"
        }]
        mock_service.table.return_value.select.return_value.eq.return_value.execute.return_value = MockSupabaseResponse(existing_profile)
        
        response = client.post(
            "/api/admin/users/create",
            json={
                "email": "existing@example.com",
                "password": "AnyPassword123!",
                "role": "patient"
            },
            headers={"Authorization": "Bearer test-token"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["message"] == "Usuário já existente"
        assert data["user_id"] == existing_user_id


def test_create_user_invalid_role(client):
    """Test creation with invalid role"""
    with patch("api.dependencies.get_supabase_anon_auth_client") as mock_get_anon:
        mock_anon = create_mock_supabase()
        mock_get_anon.return_value = mock_anon
        
        response = client.post(
            "/api/admin/users/create",
            json={
                "email": "test@example.com",
                "password": "SecurePass123!",
                "role": "invalid_role"
            },
            headers={"Authorization": "Bearer test-token"}
        )
        
        assert response.status_code == 400
        assert "Role inválida" in response.json()["detail"]


def test_create_user_weak_password(client):
    """Test creation with weak password"""
    with patch("api.dependencies.get_supabase_anon_auth_client") as mock_get_anon:
        mock_anon = create_mock_supabase()
        mock_get_anon.return_value = mock_anon
        
        response = client.post(
            "/api/admin/users/create",
            json={
                "email": "test@example.com",
                "password": "weak",
                "role": "patient"
            },
            headers={"Authorization": "Bearer test-token"}
        )
        
        assert response.status_code == 400
        assert "Senha mínima 8 caracteres" in response.json()["detail"]


def test_create_user_no_auth(client):
    """Test creation without authorization"""
    response = client.post(
        "/api/admin/users/create",
        json={
            "email": "test@example.com",
            "password": "SecurePass123!",
            "role": "patient"
        }
    )
    
    assert response.status_code == 401
