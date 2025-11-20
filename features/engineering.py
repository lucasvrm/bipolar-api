"""
Feature Engineering Module for Bipolar AI Engine.

This module contains functions for computing features from raw patient data.
Features include sleep metrics, mood volatility, behavior patterns, etc.
"""

import pandas as pd
import numpy as np
from typing import Dict, Any, List


def compute_basic_features(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Compute basic features from raw patient data.
    
    Args:
        data: Dictionary containing raw patient data
        
    Returns:
        Dictionary with computed features
    """
    features = {}
    
    # Copy direct features
    direct_features = [
        'sex', 'diagnosis_state_ground_truth', 'hoursSlept', 'sleepQuality',
        'sleepHygiene', 'perceivedSleepNeed', 'hasNapped', 'nappingDurationMin',
        'caffeineDoses', 'energyLevel', 'mood', 'anxiety', 'irritability',
        'activation', 'libido', 'focusQuality', 'medicationAdherence',
        'exerciseDurationMin', 'socialInteractionQuality', 'socialWithdrawal'
    ]
    
    for feature in direct_features:
        if feature in data:
            features[feature] = data[feature]
        else:
            # Default values
            if feature in ['diagnosis_state_ground_truth', 'sex']:
                features[feature] = 'UNKNOWN'
            elif feature in ['hasNapped']:
                features[feature] = False
            else:
                features[feature] = 0.0
    
    return features


def compute_time_series_features(
    patient_history: List[Dict[str, Any]], 
    window_days: int = 30
) -> Dict[str, float]:
    """
    Compute time-series features from patient history.
    
    Args:
        patient_history: List of patient data points over time
        window_days: Number of days to compute rolling statistics
        
    Returns:
        Dictionary with time-series features
    """
    features = {}
    
    if not patient_history or len(patient_history) == 0:
        # Return default values
        return {
            f'sleep_zscore_{window_days}d': 0.0,
            f'mood_volatility_{window_days}d': 0.0,
            f'anxiety_trend_{window_days}d': 0.0,
            f'activation_mean_{window_days}d': 0.0,
            f'impulse_count_{window_days}d': 0.0,
        }
    
    # Convert to DataFrame for easier processing
    df = pd.DataFrame(patient_history)
    
    # Compute sleep z-score
    if 'hoursSlept' in df.columns:
        sleep_mean = df['hoursSlept'].mean()
        sleep_std = df['hoursSlept'].std() if df['hoursSlept'].std() > 0 else 1.0
        features[f'sleep_zscore_{window_days}d'] = (
            (df['hoursSlept'].iloc[-1] - sleep_mean) / sleep_std
            if len(df) > 0 else 0.0
        )
    
    # Compute mood volatility
    if 'mood' in df.columns:
        features[f'mood_volatility_{window_days}d'] = df['mood'].std() if len(df) > 1 else 0.0
    
    # Compute anxiety trend
    if 'anxiety' in df.columns:
        features[f'anxiety_trend_{window_days}d'] = (
            df['anxiety'].diff().mean() if len(df) > 1 else 0.0
        )
    
    # Compute activation mean
    if 'activation' in df.columns:
        features[f'activation_mean_{window_days}d'] = df['activation'].mean()
    
    # Count impulsive behaviors
    if 'impulsiveBehaviors' in df.columns:
        features[f'impulse_count_{window_days}d'] = df['impulsiveBehaviors'].apply(
            lambda x: len(x) if isinstance(x, list) else 0
        ).sum()
    
    return features


def prepare_model_input(
    raw_data: Dict[str, Any],
    patient_history: List[Dict[str, Any]] = None,
    expected_features: List[str] = None
) -> pd.DataFrame:
    """
    Prepare a complete feature set for model input.
    
    Args:
        raw_data: Current patient data point
        patient_history: Historical data for time-series features
        expected_features: List of features expected by the model
        
    Returns:
        DataFrame ready for model prediction
    """
    # Compute basic features
    features = compute_basic_features(raw_data)
    
    # Compute time-series features if history is provided
    if patient_history:
        ts_features = compute_time_series_features(patient_history)
        features.update(ts_features)
    
    # Fill in any missing expected features
    if expected_features:
        for feature in expected_features:
            if feature not in features:
                # Smart defaults
                if 'diagnosis' in feature or 'medication' in feature:
                    features[feature] = 'EUTHYMIC'
                else:
                    features[feature] = 0.0
    
    # Create DataFrame
    df = pd.DataFrame([features])
    
    # Convert types appropriately
    for col in df.columns:
        if df[col].dtype == 'object':
            df[col] = df[col].astype('category')
        else:
            df[col] = df[col].astype(np.float32)
    
    return df
