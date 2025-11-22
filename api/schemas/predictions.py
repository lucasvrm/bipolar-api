"""
Pydantic schemas for predictions API responses.
"""
from datetime import datetime
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field
from uuid import UUID


class PredictionResponse(BaseModel):
    """
    Schema for a single prediction result.
    
    Attributes:
        type: Type of prediction (e.g., 'mood_state', 'relapse_risk')
        label: Human-readable label for the prediction
        probability: Probability score between 0 and 1 (null if unavailable)
        details: Additional details specific to the prediction type
        model_version: Version of the model used (null if heuristic/unavailable)
        explanation: Human-readable explanation of the prediction
        source: Source of the prediction data
        sensitive: Whether this is sensitive information requiring special handling
        disclaimer: Disclaimer text for sensitive predictions
        resources: Crisis resources for sensitive predictions
    """
    type: str = Field(..., description="Type of prediction")
    label: str = Field(..., description="Human-readable prediction label")
    probability: Optional[float] = Field(
        None, 
        ge=0.0, 
        le=1.0,
        description="Probability score between 0 and 1"
    )
    details: Dict[str, Any] = Field(
        default_factory=dict,
        description="Additional prediction-specific details"
    )
    model_version: Optional[str] = Field(
        None,
        description="Version of the model used"
    )
    explanation: str = Field(
        ...,
        description="Human-readable explanation"
    )
    source: str = Field(
        default="aggregated_last_checkin",
        description="Source of prediction data"
    )
    sensitive: Optional[bool] = Field(
        None,
        description="Whether this prediction is sensitive"
    )
    disclaimer: Optional[str] = Field(
        None,
        description="Disclaimer for sensitive predictions"
    )
    resources: Optional[Dict[str, str]] = Field(
        None,
        description="Crisis resources for sensitive predictions"
    )


class PerCheckinPredictions(BaseModel):
    """
    Schema for predictions associated with a specific check-in.
    
    Attributes:
        checkin_id: UUID of the check-in
        checkin_date: Date of the check-in
        predictions: List of predictions for this check-in
    """
    checkin_id: UUID = Field(..., description="Check-in UUID")
    checkin_date: str = Field(..., description="Check-in date (ISO 8601)")
    predictions: List[PredictionResponse] = Field(
        ...,
        description="Predictions for this check-in"
    )


class PredictionsResponse(BaseModel):
    """
    Standardized response schema for the /data/predictions/{user_id} endpoint.
    
    This model ensures consistent API responses and proper OpenAPI documentation.
    
    Attributes:
        user_id: UUID of the user
        window_days: Temporal window in days used for predictions
        generated_at: ISO 8601 timestamp when predictions were generated
        predictions: List of prediction results
        per_checkin: Optional list of per-checkin predictions
    """
    user_id: UUID = Field(..., description="User UUID")
    window_days: int = Field(
        ..., 
        ge=1, 
        le=30,
        description="Temporal window in days"
    )
    generated_at: str = Field(
        ...,
        description="ISO 8601 timestamp when predictions were generated"
    )
    predictions: List[PredictionResponse] = Field(
        ...,
        description="List of predictions for the user"
    )
    per_checkin: Optional[List[PerCheckinPredictions]] = Field(
        None,
        description="Per-checkin predictions (only when limit_checkins > 0)"
    )


class MoodPredictionResponse(BaseModel):
    """
    Simplified response schema for the /data/prediction_of_day/{user_id} endpoint.
    
    Returns only the essential mood state prediction for dashboard display.
    
    Attributes:
        type: Always 'mood_state'
        label: Predicted mood state label
        probability: Probability score between 0 and 1
    """
    type: str = Field(
        default="mood_state",
        description="Type of prediction (always mood_state)"
    )
    label: str = Field(
        ...,
        description="Predicted mood state (e.g., 'Eutimia', 'Mania', 'Depressão')"
    )
    probability: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Confidence probability between 0 and 1"
    )
