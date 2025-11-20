# api/schemas.py
from pydantic import BaseModel
from typing import List, Dict, Any

class PatientDataInput(BaseModel):
    patient_id: str
    features: Dict[str, Any] # Um dicionário flexível para as features
