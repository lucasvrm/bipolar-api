# api/clinical.py
from fastapi import APIRouter, HTTPException, Query
from api.models import MODELS
from api.schemas import PatientDataInput
from feature_engineering import create_features_for_prediction

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
def predict_state(data: PatientDataInput, explain: bool = Query(False, description="Se true, inclui a explicação SHAP da predição.")):
    """
    Recebe os dados de um paciente, aplica o modelo multiclasse e retorna
    a previsão do estado clínico (Eutimia, Mania, Depressão, Misto)
    para os próximos 3 dias, junto com as probabilidades.
    """
    # 1. Obter o modelo carregado
    model = MODELS.get('lgbm_multiclass_v1')
    if not model:
        raise HTTPException(status_code=503, detail="Modelo de classificação multiclasse não está disponível.")

    # 2. Preparar os dados para o modelo usando o módulo de feature engineering
    try:
        input_df = create_features_for_prediction(data.features)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Erro ao processar features: {e}")

    # 3. Fazer a predição
    prediction_proba = model.predict_proba(input_df)[0]
    predicted_class_index = int(prediction_proba.argmax())

    # 4. Formatar a resposta
    probabilities = {STATE_MAP[i]: float(prob) for i, prob in enumerate(prediction_proba)}

    # 5. (Opcional) Calcular a explicação SHAP
    response = {
        "patient_id": data.patient_id,
        "prediction_horizon_days": 3,
        "predicted_state_code": predicted_class_index,
        "predicted_state_label": STATE_MAP.get(predicted_class_index, "Desconhecido"),
        "probabilities": probabilities
    }

    if explain:
        explainer = MODELS.get('shap_explainer_v1')
        if explainer:
            # Calcula os valores SHAP para a instância fornecida
            shap_values = explainer.shap_values(input_df)
            
            # Foco na classe que foi prevista
            class_shap_values = shap_values[predicted_class_index][0]
            
            # Obtém as 3 features mais impactantes
            feature_names = input_df.columns
            contrib = sorted(zip(feature_names, class_shap_values), key=lambda x: abs(x[1]), reverse=True)
            
            top_contributors = []
            for feature, impact in contrib[:3]:
                top_contributors.append({
                    "feature": feature,
                    "value": data.features.get(feature),
                    "impact": float(impact)
                })

            response["explanation"] = {
                "base_value": float(explainer.expected_value[predicted_class_index]),
                "top_contributors": top_contributors
            }

    return response
