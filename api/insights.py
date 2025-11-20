# api/insights.py
from fastapi import APIRouter

router = APIRouter(
    prefix="/insights",
    tags=["Profiles & SHAP Analysis"]
)

# Nossos endpoints virão aqui nas próximas etapas...
