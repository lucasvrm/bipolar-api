"""
Pydantic schemas for synthetic data management endpoints.
"""
from datetime import datetime
from typing import Optional, Literal
from pydantic import BaseModel, Field


class CleanDataRequest(BaseModel):
    """Request body for cleaning synthetic data endpoint."""
    model_config = {"json_schema_extra": {
        "examples": [
            {
                "action": "delete_all"
            },
            {
                "action": "delete_last_n",
                "quantity": 10
            },
            {
                "action": "delete_by_mood",
                "mood_pattern": "stable"
            },
            {
                "action": "delete_before_date",
                "before_date": "2024-01-01T00:00:00Z"
            }
        ]
    }}

    action: Literal["delete_all", "delete_last_n", "delete_before_date"] = Field(
        description="Type of deletion action to perform"
    )
    quantity: Optional[int] = Field(
        default=None,
        ge=1,
        description="Number of patients to delete (required for delete_last_n)"
    )
    mood_pattern: Optional[str] = Field(
        default=None,
        description="Mood pattern to filter by (required for delete_by_mood): stable, cycling, or random"
    )
    before_date: Optional[str] = Field(
        default=None,
        description="ISO datetime string - delete patients created before this date (required for delete_before_date)"
    )


class CleanDataResponse(BaseModel):
    """Response body for cleaning synthetic data endpoint."""
    status: str
    message: str
    deleted_count: int


class ToggleTestFlagResponse(BaseModel):
    """Response body for toggling test flag endpoint."""
    id: str
    is_test_patient: bool
    message: str


class EnhancedStatsResponse(BaseModel):
    """Response body for enhanced stats endpoint."""
    # Legacy fields (keep for backwards compatibility)
    total_users: int
    total_checkins: int
    
    # New required fields
    real_patients_count: int
    synthetic_patients_count: int
    checkins_today: int
    checkins_last_7_days: int
    checkins_last_7_days_previous: int
    avg_checkins_per_active_patient: float
    avg_adherence_last_30d: float
    avg_current_mood: float
    mood_distribution: dict
    critical_alerts_last_30d: int
    patients_with_recent_radar: int


class DangerZoneCleanupRequest(BaseModel):
    """Request body for danger zone cleanup endpoint."""
    model_config = {"json_schema_extra": {
        "examples": [
            {
                "action": "delete_all"
            },
            {
                "action": "delete_last_n",
                "quantity": 5
            },
            {
                "action": "delete_by_mood",
                "mood_pattern": "stable"
            },
            {
                "action": "delete_before_date",
                "before_date": "2024-01-01T00:00:00Z"
            }
        ]
    }}

    action: Literal["delete_all", "delete_last_n", "delete_by_mood", "delete_before_date"] = Field(
        description="Type of deletion action: delete_all, delete_last_n, delete_by_mood, delete_before_date"
    )
    quantity: Optional[int] = Field(
        default=None,
        ge=1,
        description="Number of test patients to delete (required for delete_last_n)"
    )
    mood_pattern: Optional[str] = Field(
        default=None,
        description="Mood pattern to filter by (required for delete_by_mood): stable, cycling, or random"
    )
    before_date: Optional[str] = Field(
        default=None,
        description="ISO datetime string - delete test patients created before this date (required for delete_before_date)"
    )


class DangerZoneCleanupResponse(BaseModel):
    """Response body for danger zone cleanup endpoint."""
    deleted: int
    message: str


class SyntheticDataStatistics(BaseModel):
    """Statistics from synthetic data generation."""
    users_created: int
    patients_created: int
    therapists_created: int
    total_checkins: int
    mood_pattern: str
    checkins_per_user: int = Field(default=0)
    generated_at: str = Field(description="ISO datetime when data was generated")


class SyntheticDataGenerationResponse(BaseModel):
    """Response body for synthetic data generation endpoint."""
    status: str
    statistics: SyntheticDataStatistics
    patient_ids: list = Field(default_factory=list)
    therapist_ids: list = Field(default_factory=list)
