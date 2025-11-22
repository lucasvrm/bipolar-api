"""
Pydantic schemas for predictions API responses.
"""
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field
from uuid import UUID


class PredictionsMetric(BaseModel):
    """
    Schema for a single prediction metric.
    
    Attributes:
        name: Name of the metric (e.g., 'suicide_risk', 'mood_state')
        value: Numerical value (normalized 0-1 or specific scale)
        riskLevel: Categorical risk level (low, medium, high, critical)
        confidence: Confidence score of the prediction (0-1)
        trend: Optional trend indicator (improving, worsening, stable)
        explanation: Optional human-readable explanation
    """
    name: str = Field(..., description="Name of the prediction metric")
    value: float = Field(..., description="Numerical value of the metric")
    riskLevel: str = Field(..., description="Risk level: low, medium, high, critical")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence score")
    trend: Optional[str] = Field(None, description="Trend direction")
    explanation: Optional[str] = Field(None, description="Explanation of the result")


class PredictionsResponse(BaseModel):
    """
    Standardized response schema for the /data/predictions/{user_id} endpoint.
    Matches the diagnosis requirement: status, userId, windowDays, metrics, generatedAt.
    
    Attributes:
        status: API response status (e.g., 'ok')
        userId: UUID of the user
        windowDays: Temporal window in days
        metrics: List of prediction metrics
        generatedAt: ISO 8601 timestamp
    """
    status: str = Field(default="ok", description="Response status")
    userId: UUID = Field(..., description="User UUID")
    windowDays: int = Field(..., ge=1, description="Analysis window in days")
    metrics: List[PredictionsMetric] = Field(..., description="List of prediction metrics")
    generatedAt: str = Field(..., description="ISO 8601 timestamp")


class MoodPredictionResponse(BaseModel):
    """
    Simplified response schema for the /data/prediction_of_day/{user_id} endpoint.
    Used for the dashboard 'Prediction of the Day' card.
    """
    type: str = Field(default="mood_state", description="Type of prediction")
    label: str = Field(..., description="Predicted mood label")
    probability: float = Field(..., ge=0.0, le=1.0, description="Confidence probability")
