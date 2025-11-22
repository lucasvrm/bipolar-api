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
        label: Human readable label (e.g. 'Mania', 'High Risk') - Critical for UI
        riskLevel: Categorical risk level (low, medium, high, critical)
        confidence: Confidence score of the prediction (0-1)
        trend: Optional trend indicator (improving, worsening, stable)
        explanation: Optional human-readable explanation
    """
    name: str = Field(..., description="Name of the prediction metric")
    value: float = Field(..., description="Numerical value of the metric")
    label: str = Field(..., description="Human-readable label")
    riskLevel: str = Field(..., description="Risk level: low, medium, high, critical")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence score")
    trend: Optional[str] = Field(None, description="Trend direction")
    explanation: Optional[str] = Field(None, description="Explanation of the result")

    # Legacy alias support if needed for inner items (e.g. 'type' instead of 'name')
    type: Optional[str] = Field(None, description="Legacy alias for name")
    probability: Optional[float] = Field(None, description="Legacy alias for value")

    def model_post_init(self, __context):
        if self.type is None:
            self.type = self.name
        if self.probability is None:
            self.probability = self.value


class PredictionsResponse(BaseModel):
    """
    Standardized response schema for the /data/predictions/{user_id} endpoint.
    Matches the diagnosis requirement: status, userId, windowDays, metrics, generatedAt.
    """
    model_config = {
        "populate_by_name": True # Allow using field names or aliases
    }

    status: str = Field(default="ok", description="Response status")
    userId: UUID = Field(..., description="User UUID")
    windowDays: int = Field(..., ge=1, description="Analysis window in days")
    metrics: List[PredictionsMetric] = Field(..., description="List of prediction metrics")
    generatedAt: str = Field(..., description="ISO 8601 timestamp")

    # Aliases for backward compatibility
    user_id: Optional[UUID] = Field(None, description="Legacy alias for userId")
    window_days: Optional[int] = Field(None, description="Legacy alias for windowDays")
    predictions: Optional[List[PredictionsMetric]] = Field(None, description="Legacy alias for metrics")

    def model_post_init(self, __context):
        # Auto-populate legacy fields from new fields if not set
        if self.user_id is None:
            self.user_id = self.userId
        if self.window_days is None:
            self.window_days = self.windowDays
        if self.predictions is None:
            self.predictions = self.metrics


class MoodPredictionResponse(BaseModel):
    """
    Simplified response schema for the /data/prediction_of_day/{user_id} endpoint.
    Used for the dashboard 'Prediction of the Day' card.
    """
    type: str = Field(default="mood_state", description="Type of prediction")
    label: str = Field(..., description="Predicted mood label")
    probability: float = Field(..., ge=0.0, le=1.0, description="Confidence probability")
