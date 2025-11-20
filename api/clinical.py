# api/clinical.py
from fastapi import APIRouter

router = APIRouter(
    prefix="/predict",
    tags=["Clinical Predictions"]
)

# Nossos endpoints virão aqui nas próximas etapas...
