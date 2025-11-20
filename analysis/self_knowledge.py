"""
Self-Knowledge Analysis Module for Bipolar AI Engine.

Contains SHAP analysis, environmental triggers, and mood clustering.
"""

import shap
import pandas as pd
import numpy as np
from typing import Dict, Any, List, Optional
from sklearn.cluster import KMeans, DBSCAN
from collections import Counter
import re


class SelfKnowledgeAnalyzer:
    """Handles self-knowledge analyses including SHAP, triggers, and clustering."""
    
    def __init__(self):
        """Initialize the self-knowledge analyzer."""
        self.shap_explainer = None
        self.cluster_models = {}
    
    def explain_prediction_shap(
        self,
        model,
        features_df: pd.DataFrame,
        top_n: int = 3
    ) -> Dict[str, Any]:
        """
        Use SHAP to explain model predictions.
        
        Args:
            model: Trained model to explain
            features_df: Features used for prediction
            top_n: Number of top contributing features to return
            
        Returns:
            Dictionary with SHAP values and explanations
        """
        try:
            # Create SHAP explainer (tree explainer for LightGBM)
            if self.shap_explainer is None:
                self.shap_explainer = shap.TreeExplainer(model)
            
            # Calculate SHAP values
            shap_values = self.shap_explainer.shap_values(features_df)
            
            # For binary classification, take the positive class
            if isinstance(shap_values, list):
                shap_values = shap_values[1]
            
            # Get feature names and their SHAP values
            feature_names = features_df.columns.tolist()
            shap_vals = shap_values[0] if len(shap_values.shape) > 1 else shap_values
            
            # Create feature importance list
            feature_importance = [
                {
                    "feature": name,
                    "shap_value": float(val),
                    "feature_value": float(features_df[name].iloc[0]),
                    "impact": "increases_risk" if val > 0 else "decreases_risk"
                }
                for name, val in zip(feature_names, shap_vals)
            ]
            
            # Sort by absolute SHAP value
            feature_importance.sort(key=lambda x: abs(x["shap_value"]), reverse=True)
            
            # Get top N features
            top_features = feature_importance[:top_n]
            
            return {
                "top_contributors": top_features,
                "all_features": feature_importance,
                "base_value": float(self.shap_explainer.expected_value[1] 
                                   if isinstance(self.shap_explainer.expected_value, list)
                                   else self.shap_explainer.expected_value)
            }
            
        except Exception as e:
            # Fallback to simple feature importance
            return {
                "top_contributors": [],
                "error": f"SHAP analysis failed: {str(e)}",
                "note": "Using model without SHAP explanation"
            }
    
    def analyze_environmental_triggers(
        self,
        patient_history: List[Dict[str, Any]],
        crisis_events: List[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Analyze environmental triggers from patient history.
        
        Args:
            patient_history: Historical patient data including notes and stressors
            crisis_events: List of crisis event timestamps
            
        Returns:
            Dictionary with identified triggers and patterns
        """
        if not patient_history:
            return {
                "triggers": [],
                "patterns": {},
                "note": "Insufficient data for trigger analysis"
            }
        
        triggers = []
        stressor_patterns = Counter()
        
        # Analyze contextual stressors
        for entry in patient_history:
            if 'contextualStressors' in entry and entry['contextualStressors']:
                stressors = entry['contextualStressors']
                if isinstance(stressors, list):
                    for stressor in stressors:
                        stressor_patterns[stressor] += 1
        
        # Analyze notes for sentiment and keywords
        note_patterns = self._analyze_notes(patient_history)
        
        # Identify triggers associated with high-risk periods
        high_risk_stressors = []
        if crisis_events:
            # Find stressors that appeared before crises
            for crisis in crisis_events:
                crisis_time = crisis.get('timestamp')
                # Look for stressors in the week before
                # (simplified - in real implementation, use timestamps)
                high_risk_stressors.extend(
                    entry.get('contextualStressors', [])
                    for entry in patient_history[-7:]
                )
        
        # Build triggers list
        for stressor, count in stressor_patterns.most_common(10):
            triggers.append({
                "trigger": stressor,
                "frequency": count,
                "risk_level": "HIGH" if count > 5 else "MODERATE" if count > 2 else "LOW"
            })
        
        return {
            "triggers": triggers,
            "patterns": {
                "most_common_stressor": stressor_patterns.most_common(1)[0][0] 
                                       if stressor_patterns else "None",
                "note_sentiments": note_patterns
            },
            "recommendations": self._generate_trigger_recommendations(triggers)
        }
    
    def _analyze_notes(self, patient_history: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Analyze patient notes for sentiment and patterns."""
        negative_keywords = ['stressed', 'anxious', 'worried', 'sad', 'angry', 'fear']
        positive_keywords = ['happy', 'calm', 'peaceful', 'good', 'better', 'improving']
        
        negative_count = 0
        positive_count = 0
        
        for entry in patient_history:
            if 'notes' in entry and entry['notes']:
                note = str(entry['notes']).lower()
                negative_count += sum(1 for kw in negative_keywords if kw in note)
                positive_count += sum(1 for kw in positive_keywords if kw in note)
        
        return {
            "negative_sentiment_indicators": negative_count,
            "positive_sentiment_indicators": positive_count,
            "overall_tone": "NEGATIVE" if negative_count > positive_count else "POSITIVE"
        }
    
    def _generate_trigger_recommendations(self, triggers: List[Dict]) -> List[str]:
        """Generate recommendations based on identified triggers."""
        recommendations = []
        
        for trigger in triggers[:3]:  # Top 3 triggers
            trigger_name = trigger['trigger']
            if 'sleep' in trigger_name.lower():
                recommendations.append(
                    "Consider maintaining a consistent sleep schedule"
                )
            elif 'work' in trigger_name.lower() or 'stress' in trigger_name.lower():
                recommendations.append(
                    "Practice stress management techniques for work-related stress"
                )
            elif 'social' in trigger_name.lower():
                recommendations.append(
                    "Monitor social interactions and set healthy boundaries"
                )
        
        return recommendations
    
    def cluster_mood_states(
        self,
        patient_history: List[Dict[str, Any]],
        n_clusters: int = 4
    ) -> Dict[str, Any]:
        """
        Cluster mood states to identify patterns.
        
        Args:
            patient_history: Historical patient data
            n_clusters: Number of clusters to identify
            
        Returns:
            Dictionary with cluster analysis results
        """
        if not patient_history or len(patient_history) < n_clusters:
            return {
                "clusters": [],
                "note": "Insufficient data for clustering"
            }
        
        # Extract mood-related features
        features = []
        for entry in patient_history:
            features.append([
                entry.get('mood', 5.0),
                entry.get('energyLevel', 5.0),
                entry.get('activation', 5.0),
                entry.get('anxiety', 5.0),
                entry.get('irritability', 5.0)
            ])
        
        features_array = np.array(features)
        
        # Perform K-Means clustering
        kmeans = KMeans(n_clusters=n_clusters, random_state=42, n_init=10)
        labels = kmeans.fit_predict(features_array)
        
        # Analyze each cluster
        clusters = []
        for i in range(n_clusters):
            cluster_mask = labels == i
            cluster_data = features_array[cluster_mask]
            
            if len(cluster_data) > 0:
                centroid = kmeans.cluster_centers_[i]
                
                # Label the cluster based on centroid characteristics
                cluster_label = self._label_cluster(centroid)
                
                clusters.append({
                    "cluster_id": i,
                    "label": cluster_label,
                    "count": int(np.sum(cluster_mask)),
                    "percentage": round(float(np.sum(cluster_mask) / len(labels) * 100), 2),
                    "characteristics": {
                        "mood": round(float(centroid[0]), 2),
                        "energy": round(float(centroid[1]), 2),
                        "activation": round(float(centroid[2]), 2),
                        "anxiety": round(float(centroid[3]), 2),
                        "irritability": round(float(centroid[4]), 2)
                    }
                })
        
        # Sort by frequency
        clusters.sort(key=lambda x: x['count'], reverse=True)
        
        return {
            "clusters": clusters,
            "total_data_points": len(patient_history),
            "dominant_state": clusters[0]['label'] if clusters else "Unknown"
        }
    
    def _label_cluster(self, centroid: np.ndarray) -> str:
        """Label a cluster based on its centroid characteristics."""
        mood, energy, activation, anxiety, irritability = centroid
        
        # Simple rule-based labeling
        if activation > 6 and mood > 6:
            return "Manic/Hypomanic State"
        elif activation > 6 and mood < 4:
            return "Mixed/Agitated State"
        elif mood < 4 and energy < 4:
            return "Depressive State"
        elif anxiety > 6:
            return "Anxious State"
        elif mood > 5 and mood < 7 and energy > 4 and energy < 7:
            return "Stable/Euthymic State"
        else:
            return "Transitional State"
