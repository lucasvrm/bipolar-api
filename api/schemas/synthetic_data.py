"""
Pydantic schemas for synthetic data management endpoints.
"""
from typing import Optional, Literal, List, Dict
from pydantic import BaseModel, Field

class GenerateDataRequest(BaseModel):
    """
    Request body para geração de dados sintéticos.
    Campo testMode removido (não utilizado).
    """
    model_config = {
        "json_schema_extra": {
            "example": {
                "patientsCount": 5,
                "therapistsCount": 2,
                "checkinsPerUser": 30,
                "moodPattern": "stable",
                "seed": 42,
                "clearDb": False
            }
        },
        "populate_by_name": True
    }

    patientsCount: Optional[int] = Field(default=2, ge=0, le=500, description="Número de pacientes (max 500)")
    therapistsCount: Optional[int] = Field(default=1, ge=0, le=50, description="Número de terapeutas")
    checkinsPerUser: int = Field(default=30, ge=1, le=365, description="Check-ins por paciente")
    moodPattern: str = Field(default="stable", description="Padrão de humor: stable, cycling, random, depressive, manic")
    seed: Optional[int] = Field(default=None, description="Seed para reproducibilidade")
    clearDb: bool = Field(default=False, description="Limpa dados sintéticos existentes antes de gerar")

class SyntheticDataStatistics(BaseModel):
    users_created: int
    patients_created: int
    therapists_created: int
    total_checkins: int
    mood_pattern: str
    checkins_per_user: int
    generated_at: str
    # Campos extras informativos
    duration_ms: Optional[float] = None
    limits_applied: Optional[Dict[str, int]] = None
    domains_used: Optional[List[str]] = None

class SyntheticDataGenerationResponse(BaseModel):
    status: str
    statistics: SyntheticDataStatistics
    generatedAt: str

class StatsResponse(BaseModel):
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
    status: str
    message: str
    removedRecords: int
    sampleIds: List[str]
    dryRun: bool
    cleanedAt: str

class CleanupDataRequest(BaseModel):
    confirm: bool = False
    dryRun: bool = False

class DangerZoneCleanupRequest(BaseModel):
    action: Literal["delete_all", "delete_last_n", "delete_by_mood", "delete_before_date"]
    quantity: Optional[int] = Field(default=None, ge=1)
    mood_pattern: Optional[str] = None
    before_date: Optional[str] = None
    dryRun: bool = Field(default=False, description="Se true, simula a exclusão")

# Aliases legacy
EnhancedStatsResponse = StatsResponse
CleanDataRequest = DangerZoneCleanupRequest
CleanDataResponse = CleanupResponse
