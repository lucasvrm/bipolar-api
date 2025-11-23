"""
Pydantic schemas for admin user management endpoints.
"""
from typing import Optional, Literal, Dict, Any
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
    source: Optional[str] = None
    deleted_at: Optional[str] = None


class ListUsersResponse(BaseModel):
    """Response for listing users."""
    status: str
    users: list[UserListItem]
    total: int


class UpdateUserRequest(BaseModel):
    """Request body for updating an existing user."""
    role: Optional[Literal["patient", "therapist"]] = Field(None, description="User role")
    username: Optional[str] = Field(None, description="Username")
    email: Optional[str] = Field(None, description="Email address")
    is_test_patient: Optional[bool] = Field(None, description="Whether user is a test patient")
    source: Optional[str] = Field(None, description="User source (e.g., 'admin_manual', 'synthetic', 'signup')")
    
    model_config = {
        "json_schema_extra": {
            "example": {
                "role": "therapist",
                "username": "dr_silva"
            }
        }
    }


class UpdateUserResponse(BaseModel):
    """Response for successful user update."""
    status: str
    message: str
    user_id: str


class UserDetailAggregates(BaseModel):
    """Aggregated information about a user."""
    checkins_count: int = 0
    clinical_notes_as_patient: int = 0
    clinical_notes_as_therapist: int = 0
    has_crisis_plan: bool = False
    assigned_therapist_id: Optional[str] = None
    assigned_patients_count: int = 0


class UserDetailResponse(BaseModel):
    """Detailed user information response."""
    status: str
    user: Dict[str, Any]
    aggregates: UserDetailAggregates


class DeleteUserResponse(BaseModel):
    """Response for user deletion."""
    status: str
    message: str
    user_id: str
    deletion_type: Literal["hard", "soft"]


class BulkUsersRequest(BaseModel):
    """Request for bulk user generation."""
    role: Literal["patient", "therapist"] = Field(..., description="Role of users to generate")
    count: int = Field(..., ge=1, le=500, description="Number of users to generate")
    is_test_patient: bool = Field(True, description="Mark users as test patients")
    source: str = Field("synthetic", description="Source identifier (e.g., 'synthetic', 'seed')")
    auto_assign_therapists: bool = Field(False, description="Auto-assign therapists to patients (patients only)")
    
    model_config = {
        "json_schema_extra": {
            "example": {
                "role": "patient",
                "count": 10,
                "is_test_patient": True,
                "source": "synthetic",
                "auto_assign_therapists": True
            }
        }
    }


class BulkUsersResponse(BaseModel):
    """Response for bulk user generation."""
    status: str
    message: str
    users_created: int
    user_ids: list[str]
    patients_count: int = 0
    therapists_count: int = 0


class BulkCheckinsRequest(BaseModel):
    """Request for bulk check-ins generation."""
    target_users: Optional[list[str]] = Field(None, description="List of user IDs to generate check-ins for")
    all_test_patients: bool = Field(False, description="Generate for all test patients")
    start_date: Optional[str] = Field(None, description="Start date (ISO format)")
    end_date: Optional[str] = Field(None, description="End date (ISO format)")
    last_n_days: Optional[int] = Field(None, ge=1, le=365, description="Generate for last N days")
    checkins_per_day_min: int = Field(1, ge=0, le=5, description="Minimum check-ins per day")
    checkins_per_day_max: int = Field(1, ge=1, le=5, description="Maximum check-ins per day")
    mood_pattern: str = Field("stable", description="Mood pattern: stable, cycling, random, manic, depressive")
    
    model_config = {
        "json_schema_extra": {
            "example": {
                "all_test_patients": True,
                "last_n_days": 30,
                "checkins_per_day_min": 1,
                "checkins_per_day_max": 1,
                "mood_pattern": "stable"
            }
        }
    }


class BulkCheckinsResponse(BaseModel):
    """Response for bulk check-ins generation."""
    status: str
    message: str
    checkins_created: int
    users_affected: int
    date_range: Dict[str, str]


class DeleteTestUsersResponse(BaseModel):
    """Response for delete test users operation."""
    status: str
    message: str
    users_deleted: int
    checkins_deleted: int
    clinical_notes_deleted: int
    crisis_plans_deleted: int
    therapist_assignments_deleted: int


class ClearDatabaseRequest(BaseModel):
    """Request for full database cleanup."""
    confirm_text: str = Field(..., description="User must type exact confirmation text")
    delete_audit_logs: bool = Field(False, description="Whether to delete audit logs (optional)")
    
    model_config = {
        "json_schema_extra": {
            "example": {
                "confirm_text": "DELETE ALL DATA",
                "delete_audit_logs": False
            }
        }
    }


class ClearDatabaseResponse(BaseModel):
    """Response for full database cleanup."""
    status: str
    message: str
    checkins_deleted: int
    clinical_notes_deleted: int
    crisis_plans_deleted: int
    therapist_assignments_deleted: int
    test_users_deleted: int
    normal_users_soft_deleted: int
    audit_logs_deleted: int = 0
