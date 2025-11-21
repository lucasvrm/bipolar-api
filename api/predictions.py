# api/predictions.py
import logging
import os
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from supabase import AsyncClient
from postgrest.exceptions import APIError
import pandas as pd
import numpy as np

from .dependencies import get_supabase_client
from .models import MODELS
from .utils import validate_uuid_or_400
from feature_engineering import create_features_for_prediction

# Logger específico para este módulo
logger = logging.getLogger("bipolar-api.predictions")

router = APIRouter(prefix="/data", tags=["Predictions"])

# Mapeamento de classes de humor
MOOD_STATE_MAP = {
    0: "Eutimia",
    1: "Mania",
    2: "Depressão",
    3: "Estado Misto"
}

# Tipos de predição suportados
SUPPORTED_TYPES = [
    "mood_state",
    "relapse_risk",
    "suicidality_risk",
    "medication_adherence_risk",
    "sleep_disturbance_risk"
]


def calculate_heuristic_probability(checkin_data: Dict[str, Any], prediction_type: str) -> float:
    """
    Calcula probabilidade baseada em heurísticas quando modelo específico não está disponível.
    
    Heurísticas clínicas:
    - relapse_risk: Combina fatores de sono (<8h = risco), humor depressivo, 
      energia extrema (muito alta/baixa), e ansiedade. Valores esperados: 0-10 para mood/anxiety/energy, horas para sono.
    - suicidality_risk: Conservador, peso maior para depressão (50%), ansiedade (30%), impulsividade (20%).
      Escalas esperadas: 0-10.
    - medication_adherence_risk: Inverso da adesão reportada. Valores esperados: 0-1.
    - sleep_disturbance_risk: Alto risco se <6h ou >10h (60%), qualidade ruim (40%). 
      Escalas: horas de sono, qualidade 0-10.
    
    Args:
        checkin_data: Dados do check-in
        prediction_type: Tipo de predição
        
    Returns:
        Probabilidade normalizada entre 0 e 1
    """
    try:
        if prediction_type == "relapse_risk":
            # Baseado em sono, humor, energia e ansiedade
            sleep = checkin_data.get("hoursSlept", 7)
            mood = checkin_data.get("depressedMood", 3)
            energy = checkin_data.get("energyLevel", 5)
            anxiety = checkin_data.get("anxietyStress", 3)
            
            # Normalizar valores (assumindo escalas 0-10)
            sleep_risk = max(0, 1 - (sleep / 8)) if sleep > 0 else 1.0  # Prevent division by zero
            mood_risk = mood / 10
            energy_risk = abs(energy - 5) / 5  # Muito alta ou baixa = risco
            anxiety_risk = anxiety / 10
            
            # Média ponderada
            risk = (sleep_risk * 0.3 + mood_risk * 0.3 + energy_risk * 0.2 + anxiety_risk * 0.2)
            return float(np.clip(risk, 0, 1))
            
        elif prediction_type == "suicidality_risk":
            # Baseado em humor depressivo, desesperança e impulsividade
            mood = checkin_data.get("depressedMood", 3)
            anxiety = checkin_data.get("anxietyStress", 3)
            impulsivity = checkin_data.get("compulsionIntensity", 0)
            
            # Fórmula conservadora (maior peso para depressão)
            risk = (mood * 0.5 + anxiety * 0.3 + impulsivity * 0.2) / 10
            return float(np.clip(risk, 0, 1))
            
        elif prediction_type == "medication_adherence_risk":
            # Baseado em adesão recente
            adherence = checkin_data.get("medicationAdherence", 1)
            timing = checkin_data.get("medicationTiming", 1)
            
            # Risco é inverso da adesão
            risk = 1 - ((adherence + timing) / 2)
            return float(np.clip(risk, 0, 1))
            
        elif prediction_type == "sleep_disturbance_risk":
            # Baseado em horas de sono e qualidade
            sleep = checkin_data.get("hoursSlept", 7)
            sleep_quality = checkin_data.get("sleepQuality", 5)
            
            # Risco alto se sono < 6h ou > 10h
            sleep_duration_risk = 1.0 if (sleep < 6 or sleep > 10) else 0.0
            quality_risk = (10 - sleep_quality) / 10
            
            risk = (sleep_duration_risk * 0.6 + quality_risk * 0.4)
            return float(np.clip(risk, 0, 1))
            
        else:
            return 0.5  # Default neutro
            
    except Exception as e:
        logger.warning(f"Error calculating heuristic for {prediction_type}: {e}")
        return 0.5


def run_prediction(
    checkin_data: Dict[str, Any],
    prediction_type: str,
    window_days: int = 3
) -> Dict[str, Any]:
    """
    Executa uma predição específica para um check-in.
    
    Args:
        checkin_data: Dados do check-in
        prediction_type: Tipo de predição a executar
        window_days: Janela temporal em dias
        
    Returns:
        Dicionário com resultado da predição
    """
    logger.info(f"Running prediction: {prediction_type} for window_days={window_days}")
    
    result = {
        "type": prediction_type,
        "label": None,
        "probability": None,
        "details": {},
        "model_version": None,
        "explanation": "Explanation unavailable",
        "source": "aggregated_last_checkin"
    }
    
    try:
        if prediction_type == "mood_state":
            # Usar modelo multiclasse existente
            model = MODELS.get('lgbm_multiclass_v1')
            if model:
                input_df = create_features_for_prediction(checkin_data)
                prediction_proba = model.predict_proba(input_df)[0]
                predicted_class = int(prediction_proba.argmax())
                
                result["label"] = MOOD_STATE_MAP.get(predicted_class, "Desconhecido")
                result["probability"] = float(prediction_proba[predicted_class])
                result["details"] = {
                    "class_probs": {
                        MOOD_STATE_MAP[i]: float(prob) 
                        for i, prob in enumerate(prediction_proba)
                    }
                }
                result["model_version"] = "lgbm_multiclass_v1"
                
                # Adicionar explicação SHAP se disponível
                explainer = MODELS.get('shap_explainer_v1')
                if explainer:
                    try:
                        shap_values = explainer.shap_values(input_df)
                        class_shap_values = shap_values[predicted_class][0]
                        feature_names = input_df.columns
                        
                        # Top 3 features
                        contrib = sorted(
                            zip(feature_names, class_shap_values),
                            key=lambda x: abs(x[1]),
                            reverse=True
                        )[:3]
                        
                        explanation_parts = []
                        for feature, impact in contrib:
                            explanation_parts.append(
                                f"{feature}={checkin_data.get(feature, 'N/A')} (impact: {impact:.3f})"
                            )
                        result["explanation"] = f"SHAP top features: {', '.join(explanation_parts)}"
                    except Exception as e:
                        logger.warning(f"SHAP explanation failed: {e}")
            else:
                # Fallback: usar heurística baseada em humor reportado
                mood = checkin_data.get("depressedMood", 5)
                energy = checkin_data.get("energyLevel", 5)
                
                if mood < 4 and energy < 4:
                    label = "Depressão"
                    prob = 0.6
                elif energy > 7 and mood > 6:
                    label = "Mania"
                    prob = 0.55
                elif mood < 5 and energy > 7:
                    label = "Estado Misto"
                    prob = 0.5
                else:
                    label = "Eutimia"
                    prob = 0.65
                    
                result["label"] = label
                result["probability"] = prob
                result["model_version"] = "heuristic_v1"
                result["explanation"] = f"Based on mood={mood}, energy={energy}"
                
        elif prediction_type == "medication_adherence_risk":
            # Usar modelo de adesão se disponível
            model = MODELS.get('lgbm_adherence_v1')
            if model:
                input_df = create_features_for_prediction(checkin_data)
                probability = float(model.predict_proba(input_df)[0][1])
                result["label"] = "Alto risco" if probability > 0.5 else "Baixo risco"
                result["probability"] = probability
                result["model_version"] = "lgbm_adherence_v1"
                result["explanation"] = f"Probability of non-adherence: {probability:.2%}"
            else:
                # Fallback heurístico
                probability = calculate_heuristic_probability(checkin_data, prediction_type)
                result["label"] = "Alto risco" if probability > 0.5 else "Baixo risco"
                result["probability"] = probability
                result["model_version"] = "heuristic_v1"
                result["explanation"] = "Heuristic based on reported adherence"
                
        elif prediction_type == "relapse_risk":
            # Usar heurística baseada em múltiplos fatores
            probability = calculate_heuristic_probability(checkin_data, prediction_type)
            result["label"] = "Alto risco" if probability > 0.6 else "Baixo risco"
            result["probability"] = probability
            result["model_version"] = "heuristic_v1"
            result["explanation"] = f"Risk based on sleep, mood, energy and anxiety patterns"
            
        elif prediction_type == "suicidality_risk":
            # IMPORTANTE: Tipo sensível com disclaimer
            probability = calculate_heuristic_probability(checkin_data, prediction_type)
            result["label"] = "Risco detectado" if probability > 0.5 else "Risco baixo"
            result["probability"] = probability
            result["model_version"] = "heuristic_v1"
            result["sensitive"] = True
            result["disclaimer"] = (
                "Esta predição NÃO substitui avaliação clínica profissional. "
                "Se você está pensando em suicídio, procure ajuda imediatamente."
            )
            result["resources"] = {
                "CVV": "188 (24h, gratuito)",
                "CAPS": "Centros de Atenção Psicossocial",
                "emergency": "SAMU 192 ou UPA/Emergência hospitalar"
            }
            result["explanation"] = "Based on mood and distress indicators. SEEK PROFESSIONAL HELP."
            
        elif prediction_type == "sleep_disturbance_risk":
            probability = calculate_heuristic_probability(checkin_data, prediction_type)
            result["label"] = "Distúrbio detectado" if probability > 0.5 else "Sono adequado"
            result["probability"] = probability
            result["model_version"] = "heuristic_v1"
            result["explanation"] = f"Based on sleep duration and quality metrics"
            
    except Exception as e:
        logger.exception(f"Error running prediction {prediction_type}: {e}")
        result["probability"] = None
        result["explanation"] = f"Prediction failed: {str(e)}"
        
    return result


@router.get("/predictions/{user_id}")
async def get_predictions(
    user_id: str,
    types: Optional[str] = Query(None, description="Comma-separated list of prediction types"),
    window_days: int = Query(3, ge=1, le=30, description="Temporal window in days"),
    limit_checkins: int = Query(0, ge=0, le=10, description="Number of recent check-ins to include"),
    supabase: AsyncClient = Depends(get_supabase_client)
):
    """
    Endpoint para obter predições multi-tipo para um usuário.
    
    Retorna predições para até 5 tipos de análise relevantes para transtorno bipolar:
    1. mood_state - Estado de humor previsto (eutimia/depressão/mania/misto)
    2. relapse_risk - Risco de recorrência de episódio
    3. suicidality_risk - Risco suicida (com disclaimer e recursos)
    4. medication_adherence_risk - Risco de baixa adesão medicamentosa
    5. sleep_disturbance_risk - Risco de perturbação do sono
    
    Args:
        user_id: UUID do usuário
        types: Lista de tipos separados por vírgula (default: todos)
        window_days: Janela temporal em dias (default: 3)
        limit_checkins: Número de check-ins recentes para análise individual (default: 0)
        
    Returns:
        JSON com predições agregadas e opcionalmente por check-in
    """
    # Validate UUID format
    validate_uuid_or_400(user_id, "user_id")
    
    logger.info(f"GET /data/predictions/{user_id} - types={types}, window_days={window_days}, limit_checkins={limit_checkins}")
    print(f"[PREDICTIONS] Request for user_id={user_id}", flush=True)
    
    # Validar variáveis de ambiente do Supabase
    if not os.environ.get("SUPABASE_URL") or not os.environ.get("SUPABASE_SERVICE_KEY"):
        logger.error("Supabase environment variables not configured")
        raise HTTPException(
            status_code=500,
            detail="Supabase environment variables (SUPABASE_URL, SUPABASE_SERVICE_KEY) not configured"
        )
    
    # Parse tipos solicitados
    if types:
        requested_types = [t.strip() for t in types.split(",")]
        # Validar tipos
        invalid_types = [t for t in requested_types if t not in SUPPORTED_TYPES]
        if invalid_types:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid prediction types: {invalid_types}. Supported: {SUPPORTED_TYPES}"
            )
    else:
        requested_types = SUPPORTED_TYPES.copy()
    
    logger.info(f"Requested types: {requested_types}")
    
    try:
        # Buscar check-ins do usuário
        logger.info(f"Fetching check-ins for user_id={user_id}")
        print(f"[PREDICTIONS] Querying Supabase for check-ins...", flush=True)
        
        response = await supabase.table('check_ins')\
            .select('*')\
            .eq('user_id', user_id)\
            .order('checkin_date', desc=True)\
            .limit(max(1, limit_checkins))\
            .execute()
        
        checkins = response.data if response.data else []
        logger.info(f"Found {len(checkins)} check-ins for user_id={user_id}")
        print(f"[PREDICTIONS] Found {len(checkins)} check-ins", flush=True)
        
        # Preparar resposta
        response_data = {
            "user_id": user_id,
            "window_days": window_days,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "predictions": []
        }
        
        # Se houver check-ins, processar predições
        if checkins:
            # Usar o check-in mais recente para predição agregada
            latest_checkin = checkins[0]
            logger.info(f"Processing predictions for latest check-in: {latest_checkin.get('id')}")
            
            # Executar predições para cada tipo solicitado
            for pred_type in requested_types:
                logger.info(f"Running prediction type: {pred_type}")
                prediction = run_prediction(latest_checkin, pred_type, window_days)
                response_data["predictions"].append(prediction)
            
            # Se limit_checkins > 0, incluir predições por check-in
            if limit_checkins > 0 and len(checkins) > 0:
                response_data["per_checkin"] = []
                
                for checkin in checkins[:limit_checkins]:
                    checkin_predictions = {
                        "checkin_id": checkin.get("id"),
                        "checkin_date": checkin.get("checkin_date"),
                        "predictions": []
                    }
                    
                    for pred_type in requested_types:
                        prediction = run_prediction(checkin, pred_type, window_days)
                        prediction["source"] = "per_checkin"
                        checkin_predictions["predictions"].append(prediction)
                    
                    response_data["per_checkin"].append(checkin_predictions)
                    
                logger.info(f"Included {len(response_data['per_checkin'])} check-ins with predictions")
        else:
            # Sem check-ins: retornar predições com probability null/0
            logger.info("No check-ins found, returning stub predictions")
            for pred_type in requested_types:
                response_data["predictions"].append({
                    "type": pred_type,
                    "label": "Dados insuficientes",
                    "probability": 0.0,
                    "details": {},
                    "model_version": None,
                    "explanation": "No check-in data available for this user",
                    "source": "aggregated_last_checkin"
                })
        
        logger.info(f"Successfully generated {len(response_data['predictions'])} predictions")
        print(f"[PREDICTIONS] Response ready with {len(response_data['predictions'])} predictions", flush=True)
        
        return response_data
        
    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    except APIError as e:
        # Handle PostgREST syntax errors (invalid UUID in database query)
        if hasattr(e, 'code') and e.code == '22P02':
            raise HTTPException(
                status_code=400,
                detail=f"Invalid UUID format in database query: {user_id}"
            )
        # Re-raise other APIErrors
        logger.exception(f"PostgREST APIError for user_id={user_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Database error: {str(e)}"
        )
    except Exception as e:
        logger.exception(f"Error processing predictions for user_id={user_id}: {e}")
        print(f"[PREDICTIONS ERROR] {type(e).__name__}: {str(e)}", flush=True)
        raise HTTPException(
            status_code=500,
            detail=f"Error processing predictions: {str(e)}"
        )
