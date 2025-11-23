"""
Pydantic schemas for admin user management endpoints.
"""
from typing import Optional, Literal
from pydantic import BaseModel, Field


class CreateUserRequest(BaseModel):
    """Request body for creating a new user."""
    email: str = Field(..., description="User email address")
    password: str = Field(..., min_length=6, description="User password (minimum 6 characters)")
    role: Literal["patient", "therapist"] = Field(..., description="User role")
    full_name: Optional[str] = Field(None, description="User's full name")
    
    model_config = {
        "json_schema_extra": {
            "example": {
                "email": "patient@example.com",
                "password": "securePassword123",
                "role": "patient",
                "full_name": "João Silva"
            }
        }
    }


class CreateUserResponse(BaseModel):
    """Response for successful user creation."""
    status: str
    message: str
    user_id: str
    email: str
    role: str


class UserListItem(BaseModel):
    """Individual user item in list response."""
    id: str
    email: str
    role: str
    created_at: str
    is_test_patient: bool = False


class ListUsersResponse(BaseModel):
    """Response for listing users."""
    status: str
    users: list[UserListItem]
    total: int
