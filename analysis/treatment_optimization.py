"""
Treatment Optimization Module for Bipolar AI Engine.

Contains medication adherence prediction, causal analysis, and habit optimization.
"""

import pandas as pd
import numpy as np
from typing import Dict, Any, List, Optional
from scipy import stats
import joblib
from pathlib import Path


class TreatmentOptimizer:
    """Handles treatment optimization analyses."""
    
    def __init__(self, models_dir: str = "models"):
        """
        Initialize the treatment optimizer.
        
        Args:
            models_dir: Directory containing model files
        """
        self.models_dir = Path(models_dir)
        self.adherence_model = None
        self._load_models()
    
    def _load_models(self):
        """Load treatment-related models."""
        adherence_path = self.models_dir / "medication_adherence_model.joblib"
        if adherence_path.exists():
            try:
                self.adherence_model = joblib.load(adherence_path)
                print(f"✅ Loaded medication adherence model")
            except Exception as e:
                print(f"⚠️ Could not load adherence model: {e}")
    
    def predict_medication_adherence(
        self, 
        features_df: pd.DataFrame
    ) -> Dict[str, Any]:
        """
        Predict medication adherence risk.
        
        Args:
            features_df: DataFrame with patient features
            
        Returns:
            Dictionary with adherence prediction
        """
        if self.adherence_model is None:
            # Heuristic prediction
            return self._heuristic_adherence_prediction(features_df)
        
        prob = float(self.adherence_model.predict_proba(features_df)[0][1])
        
        risk = "LOW"
        if prob > 0.4:
            risk = "MODERATE"
        if prob > 0.7:
            risk = "HIGH"
        
        return {
            "non_adherence_probability": round(prob, 4),
            "risk_level": risk,
            "alert": prob > 0.5,
            "timeframe_days": 3,
            "recommendations": self._generate_adherence_recommendations(prob)
        }
    
    def _heuristic_adherence_prediction(
        self, 
        features_df: pd.DataFrame
    ) -> Dict[str, Any]:
        """Heuristic-based adherence prediction."""
        # Check if medicationAdherence feature exists
        if 'medicationAdherence' in features_df.columns:
            current_adherence = features_df['medicationAdherence'].iloc[0]
            # Convert to risk (inverse of adherence)
            prob = (10 - current_adherence) / 10.0
        else:
            # Use mood instability as proxy
            mood = features_df['mood'].iloc[0] if 'mood' in features_df else 5.0
            anxiety = features_df['anxiety'].iloc[0] if 'anxiety' in features_df else 5.0
            # Higher anxiety and extreme mood suggest higher non-adherence risk
            prob = (abs(mood - 5) + anxiety) / 15.0
        
        risk = "LOW"
        if prob > 0.4:
            risk = "MODERATE"
        if prob > 0.7:
            risk = "HIGH"
        
        return {
            "non_adherence_probability": round(prob, 4),
            "risk_level": risk,
            "alert": prob > 0.5,
            "timeframe_days": 3,
            "recommendations": self._generate_adherence_recommendations(prob),
            "note": "Heuristic prediction (model not trained yet)"
        }
    
    def _generate_adherence_recommendations(self, prob: float) -> List[str]:
        """Generate adherence recommendations based on risk."""
        recommendations = []
        
        if prob > 0.7:
            recommendations.append("Consider setting up medication reminders")
            recommendations.append("Discuss side effects with healthcare provider")
            recommendations.append("Use a pill organizer for weekly planning")
        elif prob > 0.4:
            recommendations.append("Maintain consistent medication routine")
            recommendations.append("Track medication in app daily")
        else:
            recommendations.append("Continue current medication routine")
        
        return recommendations
    
    def analyze_medication_impact(
        self,
        patient_history: List[Dict[str, Any]],
        medication_change: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Analyze causal impact of medication using propensity score matching.
        
        Args:
            patient_history: Historical patient data
            medication_change: Information about medication change
            
        Returns:
            Dictionary with causal analysis results
        """
        if not patient_history or len(patient_history) < 14:
            return {
                "average_treatment_effect": None,
                "note": "Insufficient data for causal analysis (need at least 14 days)"
            }
        
        # Simplified causal analysis (basic before/after comparison)
        medication_name = medication_change.get('medication', 'Unknown')
        change_index = medication_change.get('index', len(patient_history) // 2)
        
        # Split data into before and after
        before_data = patient_history[:change_index]
        after_data = patient_history[change_index:]
        
        if len(before_data) < 3 or len(after_data) < 3:
            return {
                "average_treatment_effect": None,
                "note": "Need at least 3 data points before and after medication change"
            }
        
        # Calculate mood stability before and after
        before_mood = [d.get('mood', 5.0) for d in before_data]
        after_mood = [d.get('mood', 5.0) for d in after_data]
        
        before_stability = np.std(before_mood)
        after_stability = np.std(after_mood)
        
        before_mean = np.mean(before_mood)
        after_mean = np.mean(after_mood)
        
        # Calculate treatment effect
        ate_stability = before_stability - after_stability  # Positive = improvement
        ate_mood = after_mean - before_mean  # Positive = mood increased
        
        # Statistical test
        t_stat, p_value = stats.ttest_ind(before_mood, after_mood)
        
        return {
            "medication": medication_name,
            "average_treatment_effect": {
                "mood_stability_change": round(ate_stability, 3),
                "mood_level_change": round(ate_mood, 3),
                "interpretation": self._interpret_ate(ate_stability, ate_mood)
            },
            "statistical_significance": {
                "p_value": round(p_value, 4),
                "significant": p_value < 0.05
            },
            "before_period": {
                "mean_mood": round(before_mean, 2),
                "mood_stability": round(before_stability, 2),
                "days": len(before_data)
            },
            "after_period": {
                "mean_mood": round(after_mean, 2),
                "mood_stability": round(after_stability, 2),
                "days": len(after_data)
            },
            "note": "Basic before/after analysis. Full propensity score matching requires more data."
        }
    
    def _interpret_ate(self, stability_change: float, mood_change: float) -> str:
        """Interpret average treatment effect."""
        if stability_change > 0.5:
            stability_desc = "significantly improved stability"
        elif stability_change > 0.2:
            stability_desc = "moderately improved stability"
        elif stability_change > -0.2:
            stability_desc = "no significant change in stability"
        else:
            stability_desc = "decreased stability"
        
        if abs(mood_change) < 0.5:
            mood_desc = "minimal mood change"
        elif mood_change > 0:
            mood_desc = "elevated mood"
        else:
            mood_desc = "lowered mood"
        
        return f"{stability_desc}, {mood_desc}"
    
    def optimize_habit(
        self,
        patient_history: List[Dict[str, Any]],
        habit: str = 'exerciseDurationMin'
    ) -> Dict[str, Any]:
        """
        Optimize a single habit by analyzing its correlation with mood stability.
        
        Args:
            patient_history: Historical patient data
            habit: Name of habit to optimize (e.g., 'exerciseDurationMin')
            
        Returns:
            Dictionary with optimization recommendations
        """
        if not patient_history or len(patient_history) < 7:
            return {
                "habit": habit,
                "optimal_value": None,
                "note": "Insufficient data for habit optimization (need at least 7 days)"
            }
        
        # Extract habit values and corresponding mood stability
        habit_values = []
        mood_values = []
        
        for entry in patient_history:
            if habit in entry:
                habit_values.append(entry[habit])
                mood_values.append(entry.get('mood', 5.0))
        
        if len(habit_values) < 7:
            return {
                "habit": habit,
                "optimal_value": None,
                "note": f"Insufficient data points with {habit} recorded"
            }
        
        # Calculate correlation
        correlation, p_value = stats.pearsonr(habit_values, mood_values)
        
        # Find optimal range based on mood stability
        df = pd.DataFrame({
            'habit': habit_values,
            'mood': mood_values
        })
        
        # Bin habit values and find which bin has most stable mood
        df['habit_bin'] = pd.qcut(df['habit'], q=min(5, len(df)//2), duplicates='drop')
        
        bin_stats = df.groupby('habit_bin').agg({
            'mood': ['mean', 'std', 'count']
        })
        
        # Find bin with best stability (low std) and good mood (close to 5-7)
        bin_stats['score'] = -bin_stats[('mood', 'std')] + abs(6 - bin_stats[('mood', 'mean')])
        best_bin_idx = bin_stats['score'].idxmax()
        best_bin = bin_stats.loc[best_bin_idx]
        
        optimal_range = str(best_bin_idx)
        
        return {
            "habit": habit,
            "correlation_with_mood": round(correlation, 3),
            "statistical_significance": {
                "p_value": round(p_value, 4),
                "significant": p_value < 0.05
            },
            "optimal_range": optimal_range,
            "current_average": round(np.mean(habit_values), 2),
            "recommendation": self._generate_habit_recommendation(
                habit, correlation, optimal_range
            ),
            "data_points": len(habit_values)
        }
    
    def _generate_habit_recommendation(
        self,
        habit: str,
        correlation: float,
        optimal_range: str
    ) -> str:
        """Generate habit recommendation."""
        if abs(correlation) < 0.2:
            return f"{habit} shows weak correlation with mood. Continue monitoring."
        
        if correlation > 0:
            direction = "higher"
            effect = "improved mood"
        else:
            direction = "lower"
            effect = "improved mood"
        
        return f"{habit} in range {optimal_range} associated with best mood stability. " \
               f"{direction.capitalize()} values correlate with {effect}."
