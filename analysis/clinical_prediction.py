"""
Clinical Prediction Module for Bipolar AI Engine.

Contains models for predicting crisis risk, state transitions, and impulsive behaviors.
"""

import joblib
import pandas as pd
import numpy as np
from typing import Dict, Any, List, Optional
from pathlib import Path


class ClinicalPredictor:
    """Handles clinical predictions including crisis risk and state transitions."""
    
    def __init__(self, models_dir: str = "models"):
        """
        Initialize the clinical predictor.
        
        Args:
            models_dir: Directory containing model files
        """
        self.models_dir = Path(models_dir)
        self.crisis_model_3d = None
        self.crisis_model_7d = None
        self.state_transition_model = None
        self.impulsive_behavior_model = None
        
        # Load existing models
        self._load_models()
    
    def _load_models(self):
        """Load all available models from the models directory."""
        # Load 3-day crisis model (existing)
        crisis_3d_path = Path("lightgbm_crisis_binary_v1.pkl")
        if crisis_3d_path.exists():
            try:
                self.crisis_model_3d = joblib.load(crisis_3d_path)
                print(f"✅ Loaded 3-day crisis model")
            except Exception as e:
                print(f"⚠️ Could not load 3-day crisis model: {e}")
        
        # Try to load 7-day crisis model
        crisis_7d_path = self.models_dir / "crisis_model_t7.joblib"
        if crisis_7d_path.exists():
            try:
                self.crisis_model_7d = joblib.load(crisis_7d_path)
                print(f"✅ Loaded 7-day crisis model")
            except Exception as e:
                print(f"⚠️ Could not load 7-day crisis model: {e}")
        
        # Try to load state transition model
        state_path = self.models_dir / "state_transition_model.joblib"
        if state_path.exists():
            try:
                self.state_transition_model = joblib.load(state_path)
                print(f"✅ Loaded state transition model")
            except Exception as e:
                print(f"⚠️ Could not load state transition model: {e}")
        
        # Try to load impulsive behavior model
        impulsive_path = self.models_dir / "impulsive_behavior_model.joblib"
        if impulsive_path.exists():
            try:
                self.impulsive_behavior_model = joblib.load(impulsive_path)
                print(f"✅ Loaded impulsive behavior model")
            except Exception as e:
                print(f"⚠️ Could not load impulsive behavior model: {e}")
    
    def predict_crisis_7d(self, features_df: pd.DataFrame) -> Dict[str, Any]:
        """
        Predict crisis risk for T+7 days.
        
        Args:
            features_df: DataFrame with patient features
            
        Returns:
            Dictionary with prediction results
        """
        if self.crisis_model_7d is None:
            # Fallback to 3-day model with adjusted threshold
            if self.crisis_model_3d is None:
                raise ValueError("No crisis prediction model available")
            
            prob = float(self.crisis_model_3d.predict_proba(features_df)[0][1])
            # Adjust probability for longer timeframe (slightly lower risk)
            prob_7d = prob * 0.85
        else:
            prob_7d = float(self.crisis_model_7d.predict_proba(features_df)[0][1])
        
        # Risk levels for 7-day prediction
        risk = "LOW"
        if prob_7d > 0.4:
            risk = "MODERATE"
        if prob_7d > 0.7:
            risk = "HIGH"
        
        return {
            "probability": round(prob_7d, 4),
            "risk_level": risk,
            "alert": prob_7d > 0.5,
            "timeframe_days": 7
        }
    
    def predict_state_transition(self, features_df: pd.DataFrame) -> Dict[str, Any]:
        """
        Predict state transition for T+3 days (multi-class).
        
        Args:
            features_df: DataFrame with patient features
            
        Returns:
            Dictionary with state prediction results
        """
        if self.state_transition_model is None:
            # Simplified heuristic-based prediction
            return self._heuristic_state_prediction(features_df)
        
        probs = self.state_transition_model.predict_proba(features_df)[0]
        state_labels = ["STABLE", "DEPRESSIVE", "MANIC", "MIXED"]
        predicted_state = state_labels[np.argmax(probs)]
        
        state_probs = {
            label: round(float(prob), 4)
            for label, prob in zip(state_labels, probs)
        }
        
        return {
            "predicted_state": predicted_state,
            "probabilities": state_probs,
            "confidence": round(float(max(probs)), 4),
            "timeframe_days": 3
        }
    
    def _heuristic_state_prediction(self, features_df: pd.DataFrame) -> Dict[str, Any]:
        """Heuristic-based state prediction when model is not available."""
        # Extract key features
        mood = features_df['mood'].iloc[0] if 'mood' in features_df else 5.0
        activation = features_df['activation'].iloc[0] if 'activation' in features_df else 5.0
        anxiety = features_df['anxiety'].iloc[0] if 'anxiety' in features_df else 5.0
        
        # Simple rules
        if activation > 7 and mood > 6:
            state = "MANIC"
            probs = {"STABLE": 0.1, "DEPRESSIVE": 0.1, "MANIC": 0.7, "MIXED": 0.1}
        elif mood < 4 and activation < 4:
            state = "DEPRESSIVE"
            probs = {"STABLE": 0.1, "DEPRESSIVE": 0.7, "MANIC": 0.1, "MIXED": 0.1}
        elif activation > 6 and mood < 4:
            state = "MIXED"
            probs = {"STABLE": 0.1, "DEPRESSIVE": 0.2, "MANIC": 0.2, "MIXED": 0.5}
        else:
            state = "STABLE"
            probs = {"STABLE": 0.7, "DEPRESSIVE": 0.1, "MANIC": 0.1, "MIXED": 0.1}
        
        return {
            "predicted_state": state,
            "probabilities": probs,
            "confidence": max(probs.values()),
            "timeframe_days": 3,
            "note": "Heuristic prediction (model not trained yet)"
        }
    
    def predict_impulsive_behavior(self, features_df: pd.DataFrame) -> Dict[str, Any]:
        """
        Predict impulsive behavior risk for T+2 days.
        
        Args:
            features_df: DataFrame with patient features
            
        Returns:
            Dictionary with impulsive behavior prediction
        """
        if self.impulsive_behavior_model is None:
            # Heuristic based on activation and libido
            return self._heuristic_impulsive_prediction(features_df)
        
        prob = float(self.impulsive_behavior_model.predict_proba(features_df)[0][1])
        
        risk = "LOW"
        if prob > 0.5:
            risk = "MODERATE"
        if prob > 0.75:
            risk = "HIGH"
        
        return {
            "probability": round(prob, 4),
            "risk_level": risk,
            "alert": prob > 0.6,
            "timeframe_days": 2
        }
    
    def _heuristic_impulsive_prediction(self, features_df: pd.DataFrame) -> Dict[str, Any]:
        """Heuristic-based impulsive behavior prediction."""
        activation = features_df['activation'].iloc[0] if 'activation' in features_df else 5.0
        libido = features_df['libido'].iloc[0] if 'libido' in features_df else 5.0
        irritability = features_df['irritability'].iloc[0] if 'irritability' in features_df else 5.0
        
        # Simple scoring
        score = (activation * 0.4 + libido * 0.3 + irritability * 0.3) / 10.0
        
        risk = "LOW"
        if score > 0.5:
            risk = "MODERATE"
        if score > 0.75:
            risk = "HIGH"
        
        return {
            "probability": round(score, 4),
            "risk_level": risk,
            "alert": score > 0.6,
            "timeframe_days": 2,
            "note": "Heuristic prediction (model not trained yet)"
        }
