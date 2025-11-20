# api/clinical.py
from fastapi import APIRouter, HTTPException
from typing import Dict
from .models import MODELS  # Importa o dicionário de modelos carregados
from .schemas import PatientDataInput  # Importa o schema Pydantic
import pandas as pd
import numpy as np

router = APIRouter(
    prefix="/predict",
    tags=["Clinical Predictions"]
)

# Mapeamento de classes
STATE_MAP = {
    0: "Eutimia",
    1: "Mania",
    2: "Depressão",
    3: "Estado Misto"
}

@router.post("/state", summary="Prevê o estado clínico multiclasse em T+3 dias")
def predict_state(data: PatientDataInput):
    """
    Recebe os dados de um paciente, aplica o modelo multiclasse e retorna
    a previsão do estado clínico (Eutimia, Mania, Depressão, Misto)
    para os próximos 3 dias, junto com as probabilidades.
    """
    # 1. Obter o modelo carregado
    model = MODELS.get('lgbm_multiclass_v1')
    if not model:
        raise HTTPException(status_code=503, detail="Modelo de classificação multiclasse não está disponível.")

    # 2. Preparar os dados para o modelo
    # O modelo espera um DataFrame do pandas com as features na ordem correta.
    try:
        # Supondo que as features em data.features já estão prontas
        # Em um caso real, aqui entraria o feature engineering
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
        raise HTTPException(status_code=400, detail=f"Erro ao preparar os dados para o modelo: {e}")

    # 3. Fazer a predição
    prediction_proba = model.predict_proba(input_df)[0]
    predicted_class_index = int(prediction_proba.argmax())

    # 4. Formatar a resposta
    probabilities = {STATE_MAP[i]: float(prob) for i, prob in enumerate(prediction_proba)}

    return {
        "patient_id": data.patient_id,
        "prediction_horizon_days": 3,
        "predicted_state_code": predicted_class_index,
        "predicted_state_label": STATE_MAP.get(predicted_class_index, "Desconhecido"),
        "probabilities": probabilities
    }
