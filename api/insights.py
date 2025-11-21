# api/insights.py
from fastapi import APIRouter, HTTPException
from api.models import MODELS
from api.schemas import PatientDataInput
import pandas as pd

router = APIRouter(
    prefix="/insights",
    tags=["Profiles & SHAP Analysis"]
)

# Mapeamento para os clusters K-Means
CLUSTER_MAP = {
    0: {"profile": "Estável e Contido", "description": "Um dia de baixa volatilidade e energia moderada, típico de fases de estabilidade."},
    1: {"profile": "Crise Depressiva", "description": "Caracterizado por baixo humor, baixa energia e alto isolamento social."},
    2: {"profile": "Energizado e Instável", "description": "Alta energia e alta volatilidade de humor. Sinal de alerta para estados mistos ou hipomania."},
    3: {"profile": "Eufórico/Produtivo", "description": "Alta energia com humor estável. Pode ser um dia produtivo ou de hipomania funcional."},
    4: {"profile": "Recuperação/Fadiga", "description": "Baixa energia, mas com humor se estabilizando após um período de alta intensidade."}
}

@router.post("/analyze/day_profile", summary="Analisa o perfil do dia atual usando K-Means")
def get_day_profile(data: PatientDataInput):
    """
    Usa um modelo K-Means para classificar o dia atual do paciente em
    um dos perfis de humor pré-definidos.
    """
    kmeans_model = MODELS.get('kmeans_clusters_v1')
    scaler = MODELS.get('scaler_clusters_v1')
    if not kmeans_model or not scaler:
        raise HTTPException(status_code=503, detail="Modelos de clusterização não disponíveis.")

    try:
        # As features para o K-Means são específicas
        cluster_features = ['energyLevel', 'mood_volatility_30d', 'sleep_zscore_30d', 'social_withdrawal_7d']
        input_data = {feat: data.features.get(feat) for feat in cluster_features}
        input_df = pd.DataFrame([input_data])
        
        # Aplicar o scaler
        scaled_data = scaler.transform(input_df)
        
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Erro ao preparar dados para clusterização: {e}")

    # Prever o cluster
    cluster_prediction = int(kmeans_model.predict(scaled_data)[0])
    cluster_info = CLUSTER_MAP.get(cluster_prediction, {"profile": "Desconhecido", "description": ""})

    return {
        "patient_id": data.patient_id,
        "cluster_id": cluster_prediction,
        **cluster_info
    }
