# api/behavior.py
from fastapi import APIRouter, HTTPException
from .models import MODELS
from .schemas import PatientDataInput
import pandas as pd

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

    # 2. Preparar os dados
    try:
        input_df = pd.DataFrame([data.features])
        
        # Garantir que a ordem das colunas bate com o treino
        if hasattr(model, 'feature_name_'):
            input_df = input_df[model.feature_name_]
        
        # Correção de Tipos (Essencial para LightGBM)
        # Converte colunas de texto para 'category' e números para 'float'
        for col in input_df.columns:
            if input_df[col].dtype == 'object':
                input_df[col] = input_df[col].astype('category')
            else:
                input_df[col] = input_df[col].astype('float32')
                
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Erro ao preparar dados para o modelo de adesão: {e}")

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
