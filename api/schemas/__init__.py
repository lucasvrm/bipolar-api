"""Pydantic schemas for API models."""
from pydantic import BaseModel
from typing import Dict, Any
from .checkin_jsonb import (
    SleepData,
    MoodData,
    SymptomsData,
    RiskRoutineData,
    AppetiteImpulseData,
    MedsContextData
)


class PatientDataInput(BaseModel):
    """Patient data input for predictions."""
    patient_id: str
    features: Dict[str, Any]  # Um dicionário flexível para as features


__all__ = [
    "PatientDataInput",
    "SleepData",
    "MoodData",
    "SymptomsData",
    "RiskRoutineData",
    "AppetiteImpulseData",
    "MedsContextData"
]
