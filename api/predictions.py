# api/predictions.py
import asyncio
import logging
import os
import time
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from supabase import Client
from postgrest.exceptions import APIError
from pydantic import ValidationError
import pandas as pd
import numpy as np

from api.dependencies import get_supabase_client
from api.models import MODELS
from api.utils import validate_uuid_or_400, handle_postgrest_error
from api.schemas.predictions import (
    PredictionsResponse,
    PredictionsMetric,
    MoodPredictionResponse
)
from feature_engineering import create_features_for_prediction
from services.prediction_cache import get_cache
from api.rate_limiter import limiter, PREDICTIONS_RATE_LIMIT

# Logger específico para este módulo
logger = logging.getLogger("bipolar-api.predictions")

router = APIRouter(prefix="/data", tags=["Predictions"])

# Configuration constants
INFERENCE_TIMEOUT_SECONDS = int(os.getenv("INFERENCE_TIMEOUT_SECONDS", "30"))
CACHE_TTL_SECONDS = int(os.getenv("CACHE_TTL_SECONDS", "300"))  # 5 minutes default

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


def calculate_heuristic_probability(checkin_data: Dict[str, Any], prediction_type: str, user_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Calcula probabilidade baseada em heurísticas quando modelo específico não está disponível.
    
    Returns:
        Dict with 'probability' and 'methodology' keys
    """
    # Log warning about using unvalidated heuristic
    logger.warning("Using unvalidated heuristic for prediction user_id=%s, type=%s", user_id or "unknown", prediction_type)
    
    try:
        if prediction_type == "relapse_risk":
            # Check for critical fields
            if "hoursSlept" not in checkin_data or "depressedMood" not in checkin_data:
                return {"probability": None, "methodology": "HEURISTIC_V1_UNVALIDATED", "error": "Insufficient data"}
            
            sleep = checkin_data.get("hoursSlept")
            mood = checkin_data.get("depressedMood")
            energy = checkin_data.get("energyLevel", 5)
            anxiety = checkin_data.get("anxietyStress", 3)
            sleep_risk = max(0, 1 - (sleep / 8)) if sleep > 0 else 1.0
            mood_risk = mood / 10
            energy_risk = abs(energy - 5) / 5
            anxiety_risk = anxiety / 10
            risk = (sleep_risk * 0.3 + mood_risk * 0.3 + energy_risk * 0.2 + anxiety_risk * 0.2)
            return {"probability": float(np.clip(risk, 0, 1)), "methodology": "HEURISTIC_V1_UNVALIDATED"}
            
        elif prediction_type == "suicidality_risk":
            # Check for critical fields
            if "depressedMood" not in checkin_data:
                return {"probability": None, "methodology": "HEURISTIC_V1_UNVALIDATED", "error": "Insufficient data"}
            
            mood = checkin_data.get("depressedMood")
            anxiety = checkin_data.get("anxietyStress", 3)
            impulsivity = checkin_data.get("compulsionIntensity", 0)
            risk = (mood * 0.5 + anxiety * 0.3 + impulsivity * 0.2) / 10
            return {"probability": float(np.clip(risk, 0, 1)), "methodology": "HEURISTIC_V1_UNVALIDATED"}
            
        elif prediction_type == "medication_adherence_risk":
            adherence = checkin_data.get("medicationAdherence", 1)
            timing = checkin_data.get("medicationTiming", 1)
            risk = 1 - ((adherence + timing) / 2)
            return {"probability": float(np.clip(risk, 0, 1)), "methodology": "HEURISTIC_V1_UNVALIDATED"}
            
        elif prediction_type == "sleep_disturbance_risk":
            # Check for critical fields
            if "hoursSlept" not in checkin_data:
                return {"probability": None, "methodology": "HEURISTIC_V1_UNVALIDATED", "error": "Insufficient data"}
            
            sleep = checkin_data.get("hoursSlept")
            sleep_quality = checkin_data.get("sleepQuality", 5)
            sleep_duration_risk = 1.0 if (sleep < 6 or sleep > 10) else 0.0
            quality_risk = (10 - sleep_quality) / 10
            risk = (sleep_duration_risk * 0.6 + quality_risk * 0.4)
            return {"probability": float(np.clip(risk, 0, 1)), "methodology": "HEURISTIC_V1_UNVALIDATED"}
            
        else:
            return {"probability": 0.5, "methodology": "HEURISTIC_V1_UNVALIDATED"}
            
    except Exception as e:
        logger.warning(f"Error calculating heuristic for {prediction_type}: {e}")
        return {"probability": 0.5, "methodology": "HEURISTIC_V1_UNVALIDATED", "error": str(e)}


def normalize_probability(prob: float) -> float:
    normalized = float(np.clip(prob, 0.0, 1.0))
    if normalized < 1e-6:
        normalized = 0.0
    if normalized > (1.0 - 1e-6):
        normalized = 1.0
    return normalized


def get_risk_level(prob: float, pred_type: str = "") -> str:
    if pred_type == "suicidality_risk":
        if prob > 0.7: return "critical"
        if prob > 0.4: return "high"
        if prob > 0.2: return "medium"
        return "low"

    if prob > 0.8: return "critical"
    if prob > 0.6: return "high"
    if prob > 0.3: return "medium"
    return "low"


async def run_prediction_with_timeout(
    checkin_data: Dict[str, Any],
    prediction_type: str,
    window_days: int = 3,
    timeout_seconds: int = INFERENCE_TIMEOUT_SECONDS,
    user_id: Optional[str] = None
) -> PredictionsMetric:
    """
    Wrapper around run_prediction with timeout protection.
    Returns a PredictionsMetric object.
    """
    try:
        loop = asyncio.get_event_loop()
        result = await asyncio.wait_for(
            loop.run_in_executor(
                None,
                run_prediction,
                checkin_data,
                prediction_type,
                window_days,
                user_id
            ),
            timeout=timeout_seconds
        )
        return result
    except asyncio.TimeoutError:
        logger.error(f"Prediction timeout after {timeout_seconds}s for type={prediction_type}")
        return PredictionsMetric(
            name=prediction_type,
            value=0.0,
            label="Timeout",
            riskLevel="unknown",
            confidence=0.0,
            explanation="Timeout during prediction"
        )


def run_prediction(
    checkin_data: Dict[str, Any],
    prediction_type: str,
    window_days: int = 3,
    user_id: Optional[str] = None
) -> PredictionsMetric:
    """
    Executa uma predição específica para um check-in.
    Returns: PredictionsMetric
    """
    start_time = time.time()
    logger.info(f"Running prediction: {prediction_type} for window_days={window_days}")
    
    metric = PredictionsMetric(
        name=prediction_type,
        value=0.0,
        label="Unknown",
        riskLevel="low",
        confidence=0.0,
        explanation="Explanation unavailable"
    )
    
    try:
        if prediction_type == "mood_state":
            model = MODELS.get('lgbm_multiclass_v1')
            if model:
                input_df = create_features_for_prediction(checkin_data)
                prediction_proba = model.predict_proba(input_df)[0]
                predicted_class = int(prediction_proba.argmax())
                prob = normalize_probability(prediction_proba[predicted_class])
                
                label = MOOD_STATE_MAP.get(predicted_class, "Desconhecido")
                metric.value = prob
                metric.label = label
                metric.riskLevel = "high" if label in ["Mania", "Depressão", "Estado Misto"] else "low"
                metric.confidence = prob
                metric.explanation = f"Predicted state: {label}"
                
                # Explanation details could be expanded here
            else:
                # Heuristic fallback - check for critical fields
                logger.warning("Using unvalidated heuristic for prediction user_id=%s, type=mood_state", user_id or "unknown")
                
                if "depressedMood" not in checkin_data or "energyLevel" not in checkin_data:
                    metric.value = 0.0
                    metric.label = "Dados insuficientes"
                    metric.riskLevel = "unknown"
                    metric.confidence = 0.0
                    metric.explanation = "Missing critical fields (mood or energy) for prediction"
                    metric.methodology = "HEURISTIC_V1_UNVALIDATED"
                else:
                    mood = checkin_data.get("depressedMood")
                    energy = checkin_data.get("energyLevel")
                    if mood < 4 and energy < 4:
                        label = "Depressão"
                        prob = 0.7
                    elif energy > 7 and mood > 6:
                        label = "Mania"
                        prob = 0.6
                    elif mood < 5 and energy > 7:
                        label = "Estado Misto"
                        prob = 0.5
                    else:
                        label = "Eutimia"
                        prob = 0.8
                    
                    metric.value = prob
                    metric.label = label
                    metric.riskLevel = "high" if label != "Eutimia" else "low"
                    metric.confidence = 0.5  # lower confidence for heuristic
                    metric.explanation = f"Heuristic: {label}"
                    metric.methodology = "HEURISTIC_V1_UNVALIDATED"
                
        elif prediction_type in ["medication_adherence_risk", "relapse_risk", "suicidality_risk", "sleep_disturbance_risk"]:
             heuristic_result = calculate_heuristic_probability(checkin_data, prediction_type, user_id)
             
             if heuristic_result.get("probability") is None:
                 # Insufficient data
                 metric.value = 0.0
                 metric.label = "Dados insuficientes"
                 metric.riskLevel = "unknown"
                 metric.confidence = 0.0
                 metric.explanation = heuristic_result.get("error", "Missing critical fields for prediction")
                 metric.methodology = heuristic_result.get("methodology", "HEURISTIC_V1_UNVALIDATED")
             else:
                 prob = normalize_probability(heuristic_result["probability"])
                 metric.value = prob
                 metric.riskLevel = get_risk_level(prob, prediction_type)
                 # Label logic for risks
                 if metric.riskLevel == "critical": metric.label = "Risco Crítico"
                 elif metric.riskLevel == "high": metric.label = "Alto Risco"
                 elif metric.riskLevel == "medium": metric.label = "Risco Médio"
                 else: metric.label = "Baixo Risco"

                 metric.confidence = 0.6 # heuristic confidence
                 metric.explanation = f"Heuristic based on symptoms patterns"
                 metric.methodology = heuristic_result.get("methodology", "HEURISTIC_V1_UNVALIDATED")

    except Exception as e:
        logger.exception(f"Error running prediction {prediction_type}: {e}")
        metric.explanation = f"Error: {str(e)}"
        metric.label = "Error"
    
    return metric


@router.get("/predictions/{user_id}", response_model=PredictionsResponse)
@limiter.limit(PREDICTIONS_RATE_LIMIT)
async def get_predictions(
    request: Request,
    user_id: str,
    types: Optional[str] = Query(None, description="Comma-separated list of prediction types"),
    window_days: int = Query(3, ge=1, le=30, description="Temporal window in days"),
    supabase: Client = Depends(get_supabase_client)
):
    """
    Endpoint para obter predições para um usuário.
    Retorna estrutura padronizada: status, userId, windowDays, metrics.
    
    Sempre retorna uma resposta válida, mesmo que seja com dados padrão quando
    não há check-ins disponíveis.
    """
    request_start_time = time.time()
    
    validate_uuid_or_400(user_id, "user_id")
    
    logger.info(f"GET /data/predictions/{user_id} - types={types}, window_days={window_days}")
    
    if types:
        requested_types = [t.strip() for t in types.split(",")]
        invalid_types = [t for t in requested_types if t not in SUPPORTED_TYPES]
        if invalid_types:
            raise HTTPException(
                status_code=400, 
                detail=f"Tipos de predição inválidos: {invalid_types}. Use: {', '.join(SUPPORTED_TYPES)}"
            )
    else:
        requested_types = SUPPORTED_TYPES.copy()
    
    # Cache check
    try:
        cache = get_cache()
        cached_result = await cache.get(user_id, window_days, requested_types)
        if cached_result:
            logger.info(f"Cache HIT for user {user_id}")
            return cached_result
    except Exception as e:
        logger.warning(f"Cache error (continuing without cache): {e}")
    
    try:
        response = supabase.table('check_ins')\
            .select('*')\
            .eq('user_id', user_id)\
            .order('checkin_date', desc=True)\
            .limit(1)\
            .execute()
        
        checkins = response.data if response.data else []
        
        metrics = []
        
        if checkins:
            latest_checkin = checkins[0]
            logger.info(f"Found latest check-in for user {user_id}, generating predictions")
            
            for pred_type in requested_types:
                try:
                    metric = await run_prediction_with_timeout(latest_checkin, pred_type, window_days, user_id=user_id)
                    metrics.append(metric)
                except Exception as e:
                    logger.error(f"Error generating prediction {pred_type}: {e}")
                    # Add default metric for this prediction type
                    metrics.append(PredictionsMetric(
                        name=pred_type,
                        value=0.0,
                        label="Erro",
                        riskLevel="unknown",
                        confidence=0.0,
                        explanation=f"Erro ao gerar predição: {str(e)[:100]}"
                    ))
        else:
            # Return empty/default metrics if no data
            logger.info(f"No check-ins found for user {user_id}, returning default metrics")
            for pred_type in requested_types:
                metrics.append(PredictionsMetric(
                    name=pred_type,
                    value=0.0,
                    label="Sem dados",
                    riskLevel="unknown",
                    confidence=0.0,
                    explanation="Nenhum check-in disponível para gerar predições"
                ))

        result = PredictionsResponse(
            status="ok",
            userId=user_id,
            windowDays=window_days,
            metrics=metrics,
            generatedAt=datetime.now(timezone.utc).isoformat()
        )
        
        # Cache the result model
        try:
            cache = get_cache()
            await cache.set(user_id, window_days, requested_types, result.model_dump(), CACHE_TTL_SECONDS)
        except Exception as e:
            logger.warning(f"Failed to cache result: {e}")
        
        duration_ms = (time.time() - request_start_time) * 1000
        logger.info(f"Predictions generated for user {user_id} in {duration_ms:.2f}ms")
        
        return result
        
    except HTTPException:
        raise
    except (APIError, ValidationError) as e:
        logger.exception(f"Database/validation error for user {user_id}: {e}")
        # Return a valid response with error indication
        metrics = [
            PredictionsMetric(
                name=pred_type,
                value=0.0,
                label="Erro no banco de dados",
                riskLevel="unknown",
                confidence=0.0,
                explanation="Erro ao acessar dados do usuário"
            )
            for pred_type in requested_types
        ]
        return PredictionsResponse(
            status="ok",
            userId=user_id,
            windowDays=window_days,
            metrics=metrics,
            generatedAt=datetime.now(timezone.utc).isoformat()
        )
    except Exception as e:
        logger.exception(f"Unexpected error processing predictions for user_id={user_id}: {e}")
        # Return a valid response with error indication
        metrics = [
            PredictionsMetric(
                name=pred_type,
                value=0.0,
                label="Erro inesperado",
                riskLevel="unknown",
                confidence=0.0,
                explanation="Erro inesperado ao gerar predições"
            )
            for pred_type in requested_types
        ]
        return PredictionsResponse(
            status="ok",
            userId=user_id,
            windowDays=window_days,
            metrics=metrics,
            generatedAt=datetime.now(timezone.utc).isoformat()
        )



@router.get("/prediction_of_day/{user_id}", response_model=MoodPredictionResponse)
@limiter.limit(PREDICTIONS_RATE_LIMIT)
async def get_prediction_of_day(
    request: Request,
    user_id: str,
    supabase: Client = Depends(get_supabase_client)
):
    """
    Endpoint otimizado para dashboard (mood_state apenas).
    
    Sempre retorna uma resposta válida, mesmo quando não há dados disponíveis.
    Isso previne o dashboard de alternar entre estados de erro.
    """
    validate_uuid_or_400(user_id, "user_id")
    
    logger.info(f"GET /data/prediction_of_day/{user_id}")
    
    try:
        response = supabase.table('check_ins')\
            .select('*')\
            .eq('user_id', user_id)\
            .order('checkin_date', desc=True)\
            .limit(1)\
            .execute()
        
        checkins = response.data if response.data else []
        
        if checkins:
            logger.info(f"Generating mood prediction for user {user_id}")
            metric = await run_prediction_with_timeout(checkins[0], "mood_state", window_days=3, user_id=user_id)
            
            # Extrair label da explanation ou usar lógica do valor
            label = "Desconhecido"
            if metric.label and metric.label not in ["Unknown", "Error"]:
                label = metric.label
            elif "Predicted state:" in metric.explanation:
                label = metric.explanation.split("Predicted state:")[1].strip()
            elif "Heuristic:" in metric.explanation:
                label = metric.explanation.split("Heuristic:")[1].strip()

            return {
                "type": "mood_state",
                "label": label,
                "probability": metric.value
            }
        else:
            logger.info(f"No check-ins found for user {user_id}")
            return {
                "type": "mood_state",
                "label": "Sem dados suficientes",
                "probability": 0.0
            }
            
    except HTTPException:
        raise
    except (APIError, ValidationError) as e:
        logger.error(f"Database error in prediction_of_day for user {user_id}: {e}")
        # Return valid default response instead of raising error
        return {
            "type": "mood_state",
            "label": "Erro ao carregar dados",
            "probability": 0.0
        }
    except Exception as e:
        logger.exception(f"Unexpected error in prediction_of_day for user {user_id}: {e}")
        # Return valid default response instead of raising error
        return {
            "type": "mood_state",
            "label": "Erro inesperado",
            "probability": 0.0
        }

