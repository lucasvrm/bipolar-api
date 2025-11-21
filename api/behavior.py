# api/behavior.py
from fastapi import APIRouter, HTTPException
from api.models import MODELS
from api.schemas import PatientDataInput
from feature_engineering import create_features_for_prediction

router = APIRouter(
    prefix="/predict",
    tags=["Behavior & Adherence"]
)

@router.post("/adherence", summary="Prevê o risco de não adesão à medicação em T+1 dia")
def predict_adherence(data: PatientDataInput):
    """
    Prevê a probabilidade de um paciente não aderir corretamente à
    medicação no dia seguinte.
    """
    # 1. Obter o modelo de adesão
    model = MODELS.get('lgbm_adherence_v1')
    if not model:
        raise HTTPException(status_code=503, detail="Modelo de adesão não está disponível.")

    # 2. Preparar os dados usando o módulo de feature engineering
    try:
        input_df = create_features_for_prediction(data.features)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Erro ao processar features: {e}")

    # 3. Fazer a predição de probabilidade da classe '1' (risco)
    # predict_proba retorna [[prob_classe_0, prob_classe_1]]
    adherence_risk_probability = float(model.predict_proba(input_df)[0][1])

    # 4. Definir um rótulo de risco baseado em limiares
    if adherence_risk_probability > 0.7:
        risk_label = "Risco Alto"
    elif adherence_risk_probability > 0.4:
        risk_label = "Risco Moderado"
    else:
        risk_label = "Risco Baixo"

    return {
        "patient_id": data.patient_id,
        "prediction_horizon_days": 1,
        "adherence_risk_probability": adherence_risk_probability,
        "adherence_risk_label": risk_label
    }
