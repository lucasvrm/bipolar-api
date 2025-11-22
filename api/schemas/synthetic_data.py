"""
Pydantic schemas for synthetic data management endpoints.
"""
from datetime import datetime
from typing import Optional, Literal, List, Dict, Any
from pydantic import BaseModel, Field


class GenerateDataRequest(BaseModel):
    """Request body for generation of synthetic data."""
    model_config = {
        "json_schema_extra": {
            "example": {
                "patientsCount": 5,
                "therapistsCount": 2,
                "checkinsPerUser": 30,
                "moodPattern": "stable",
                "seed": 42,
                "clearDb": False,
            }
        },
        "populate_by_name": True # Allow using field names or aliases
    }

    # Primary fields (camelCase)
    patientsCount: Optional[int] = Field(default=2, ge=0, le=500, description="Number of patients to generate (max 500)")
    therapistsCount: Optional[int] = Field(default=1, ge=0, le=50, description="Number of therapists to generate")
    checkinsPerUser: int = Field(default=30, ge=1, le=365, description="Number of check-ins per patient")
    moodPattern: str = Field(default="stable", description="Mood pattern: stable, cycling, random, depressive, manic")
    seed: Optional[int] = Field(default=None, description="Random seed for reproducibility")
    clearDb: bool = Field(default=False, description="Whether to clear existing synthetic data first")

    # Removed snake_case duplicate fields to avoid Pydantic ConfigError


class SyntheticDataStatistics(BaseModel):
    """Statistics from synthetic data generation."""
    users_created: int
    patients_created: int
    therapists_created: int
    total_checkins: int
    mood_pattern: str
    checkins_per_user: int
    generated_at: str


class SyntheticDataGenerationResponse(BaseModel):
    """Response body for synthetic data generation endpoint."""
    status: str
    statistics: SyntheticDataStatistics
    generatedAt: str


class StatsResponse(BaseModel):
    """
    Standardized response for admin stats.
    Replaces EnhancedStatsResponse.
    """
    total_users: int
    total_checkins: int
    real_patients_count: int
    synthetic_patients_count: int
    checkins_today: int
    checkins_last_7_days: int
    checkins_last_7_days_previous: int
    avg_checkins_per_active_patient: float
    avg_adherence_last_30d: float
    avg_current_mood: float
    mood_distribution: Dict[str, int]
    critical_alerts_last_30d: int
    patients_with_recent_radar: int


class CleanupResponse(BaseModel):
    """Standardized response for cleanup operations."""
    status: str
    message: str
    removedRecords: int
    sampleIds: List[str]
    dryRun: bool
    cleanedAt: str


class CleanupDataRequest(BaseModel):
    """Request for simple cleanup."""
    confirm: bool = False
    dryRun: bool = False


class DangerZoneCleanupRequest(BaseModel):
    """Request body for danger zone cleanup endpoint."""
    action: Literal["delete_all", "delete_last_n", "delete_by_mood", "delete_before_date"]
    quantity: Optional[int] = Field(default=None, ge=1)
    mood_pattern: Optional[str] = None
    before_date: Optional[str] = None
    dryRun: bool = Field(default=False, description="If true, only simulates deletion")

# Legacy/Alias for compatibility with existing code imports
EnhancedStatsResponse = StatsResponse
CleanDataRequest = DangerZoneCleanupRequest
CleanDataResponse = CleanupResponse
