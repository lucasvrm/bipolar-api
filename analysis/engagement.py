"""
Engagement Analysis Module for Bipolar AI Engine.

Contains churn risk prediction using survival analysis.
"""

import pandas as pd
import numpy as np
from typing import Dict, Any, List, Optional
from lifelines import CoxPHFitter
from datetime import datetime, timedelta


class EngagementAnalyzer:
    """Handles user engagement and churn prediction."""
    
    def __init__(self):
        """Initialize the engagement analyzer."""
        self.cox_model = None
    
    def predict_churn_risk(
        self,
        patient_history: List[Dict[str, Any]],
        patient_id: str = None
    ) -> Dict[str, Any]:
        """
        Predict churn risk using survival analysis.
        
        Args:
            patient_history: Historical patient data
            patient_id: Patient identifier
            
        Returns:
            Dictionary with churn risk prediction
        """
        if not patient_history or len(patient_history) < 3:
            return {
                "churn_risk": "UNKNOWN",
                "note": "Insufficient data for churn prediction (need at least 3 days)"
            }
        
        # Calculate engagement metrics
        engagement_metrics = self._calculate_engagement_metrics(patient_history)
        
        # Use heuristic-based prediction
        # (In production, this would use a trained Cox Proportional Hazards model)
        churn_risk = self._heuristic_churn_prediction(engagement_metrics)
        
        return {
            "patient_id": patient_id,
            "churn_risk_level": churn_risk["risk_level"],
            "churn_probability_30d": churn_risk["probability"],
            "engagement_metrics": engagement_metrics,
            "risk_factors": churn_risk["risk_factors"],
            "recommendations": churn_risk["recommendations"]
        }
    
    def _calculate_engagement_metrics(
        self,
        patient_history: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Calculate user engagement metrics from history."""
        total_days = len(patient_history)
        
        # Calculate consistency (days with data vs total days)
        # Assuming history represents consecutive days
        consistency_score = min(total_days / 30.0, 1.0)  # Normalized to 30 days
        
        # Calculate feature completeness (how many fields are filled)
        completeness_scores = []
        for entry in patient_history:
            # Count non-null, non-zero fields
            filled_fields = sum(
                1 for k, v in entry.items()
                if v is not None and v != 0 and v != '' and v != []
            )
            total_fields = len(entry)
            completeness_scores.append(filled_fields / max(total_fields, 1))
        
        avg_completeness = np.mean(completeness_scores) if completeness_scores else 0
        
        # Calculate recent activity trend
        if len(patient_history) >= 7:
            recent_completeness = np.mean(completeness_scores[-7:])
            older_completeness = np.mean(completeness_scores[:-7])
            trend = recent_completeness - older_completeness
        else:
            trend = 0
        
        # Check for notes/engagement
        notes_count = sum(
            1 for entry in patient_history
            if entry.get('notes') and len(str(entry.get('notes', ''))) > 10
        )
        notes_engagement = notes_count / max(total_days, 1)
        
        return {
            "total_days_tracked": total_days,
            "consistency_score": round(consistency_score, 3),
            "average_completeness": round(avg_completeness, 3),
            "engagement_trend": round(trend, 3),
            "notes_engagement_rate": round(notes_engagement, 3),
            "last_entry_days_ago": 0  # Assuming most recent entry is today
        }
    
    def _heuristic_churn_prediction(
        self,
        engagement_metrics: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Heuristic-based churn prediction."""
        risk_factors = []
        risk_score = 0.0
        
        # Check consistency
        consistency = engagement_metrics["consistency_score"]
        if consistency < 0.3:
            risk_score += 0.4
            risk_factors.append("Low tracking consistency")
        elif consistency < 0.6:
            risk_score += 0.2
            risk_factors.append("Moderate tracking consistency")
        
        # Check completeness
        completeness = engagement_metrics["average_completeness"]
        if completeness < 0.3:
            risk_score += 0.3
            risk_factors.append("Low data completeness")
        elif completeness < 0.6:
            risk_score += 0.15
            risk_factors.append("Moderate data completeness")
        
        # Check trend
        trend = engagement_metrics["engagement_trend"]
        if trend < -0.1:
            risk_score += 0.3
            risk_factors.append("Declining engagement trend")
        elif trend < 0:
            risk_score += 0.1
            risk_factors.append("Slight decline in engagement")
        
        # Cap risk score at 1.0
        risk_score = min(risk_score, 1.0)
        
        # Determine risk level
        if risk_score > 0.7:
            risk_level = "HIGH"
        elif risk_score > 0.4:
            risk_level = "MODERATE"
        else:
            risk_level = "LOW"
        
        # Generate recommendations
        recommendations = self._generate_engagement_recommendations(
            risk_level, risk_factors, engagement_metrics
        )
        
        return {
            "probability": round(risk_score, 4),
            "risk_level": risk_level,
            "risk_factors": risk_factors if risk_factors else ["No major risk factors identified"],
            "recommendations": recommendations
        }
    
    def _generate_engagement_recommendations(
        self,
        risk_level: str,
        risk_factors: List[str],
        engagement_metrics: Dict[str, Any]
    ) -> List[str]:
        """Generate recommendations to improve engagement."""
        recommendations = []
        
        if risk_level == "HIGH":
            recommendations.append("Consider reaching out to user with personalized encouragement")
            recommendations.append("Review app usability and identify friction points")
            
        if "Low tracking consistency" in risk_factors:
            recommendations.append("Enable push notifications for daily check-ins")
            recommendations.append("Set up daily reminders at optimal times")
        
        if "Low data completeness" in risk_factors:
            recommendations.append("Simplify data entry with smart defaults")
            recommendations.append("Highlight benefits of complete data tracking")
        
        if "Declining engagement trend" in risk_factors:
            recommendations.append("Send re-engagement campaign with new insights")
            recommendations.append("Offer personalized analysis of tracked data")
        
        if engagement_metrics["notes_engagement_rate"] < 0.2:
            recommendations.append("Encourage journaling with prompts and templates")
        
        if not recommendations:
            recommendations.append("User is well-engaged. Continue current support.")
            recommendations.append("Provide positive reinforcement on tracking streak")
        
        return recommendations
    
    def train_cox_model(
        self,
        training_data: pd.DataFrame,
        duration_col: str = 'duration',
        event_col: str = 'churned'
    ) -> Dict[str, Any]:
        """
        Train a Cox Proportional Hazards model for churn prediction.
        
        Args:
            training_data: DataFrame with patient engagement data
            duration_col: Name of column with survival duration
            event_col: Name of column indicating churn event
            
        Returns:
            Dictionary with training results
        """
        try:
            self.cox_model = CoxPHFitter()
            self.cox_model.fit(
                training_data,
                duration_col=duration_col,
                event_col=event_col
            )
            
            return {
                "status": "success",
                "model_summary": str(self.cox_model.summary),
                "concordance_index": round(self.cox_model.concordance_index_, 4)
            }
        except Exception as e:
            return {
                "status": "failed",
                "error": str(e),
                "note": "Cox model training requires proper survival data format"
            }
