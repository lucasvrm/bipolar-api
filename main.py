import joblib
import pandas as pd
import numpy as np
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Dict, Any, List, Optional

# Import analysis modules
from analysis.clinical_prediction import ClinicalPredictor
from analysis.self_knowledge import SelfKnowledgeAnalyzer
from analysis.treatment_optimization import TreatmentOptimizer
from analysis.engagement import EngagementAnalyzer
from features.engineering import prepare_model_input

# --- CONFIGURAÇÕES ---
MODEL_FILE = 'lightgbm_crisis_binary_v1.pkl'

app = FastAPI(
    title="Bipolar AI Engine - Expanded", 
    version="3.0",
    description="Comprehensive bipolar disorder analysis platform with predictive analytics"
)

# --- BLOCO DE CONFIGURAÇÃO CORS ---
# Você precisa de uma lista de ORIGENS (os domínios que podem ligar para sua API)
origins = [
    "https://previso-fe.vercel.app",
    "http://localhost:3000",        
    "http://localhost:5173",        
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,          # Permite as origens listadas
    allow_credentials=True,         
    allow_methods=["*"],            # Permite todos os métodos (POST, GET)
    allow_headers=["*"],            # Permite todos os cabeçalhos
)
# --- FIM DO BLOCO CORS ---

# Variáveis Globais (armazenam o modelo na memória)
model = None
expected_features: List[str] = []

# Initialize analysis modules
clinical_predictor = None
self_knowledge_analyzer = None
treatment_optimizer = None
engagement_analyzer = None

@app.on_event("startup")
def load_model_and_features():
    global model, expected_features
    global clinical_predictor, self_knowledge_analyzer, treatment_optimizer, engagement_analyzer
    
    try:
        print(f"🔄 Carregando modelo {MODEL_FILE}...")
        model = joblib.load(MODEL_FILE)
        
        # Tenta extrair os nomes das colunas que o modelo aprendeu
        # LightGBM armazena isso internamente
        if hasattr(model, "feature_name_"):
            expected_features = model.feature_name_
        elif hasattr(model, "booster_"):
            expected_features = model.booster_.feature_name()
        else:
            # Fallback: Se não conseguir ler, imprime aviso (mas a API sobe)
            print("⚠️ Aviso: Não foi possível ler os nomes das features automaticamente.")
            expected_features = []
            
        print(f"✅ Modelo carregado! Esperando {len(expected_features)} features.")
        print(f"   Exemplo de features: {expected_features[:5]}...")
        
        # Initialize analysis modules
        clinical_predictor = ClinicalPredictor()
        self_knowledge_analyzer = SelfKnowledgeAnalyzer()
        treatment_optimizer = TreatmentOptimizer()
        engagement_analyzer = EngagementAnalyzer()
        print("✅ Módulos de análise inicializados!")
        
    except Exception as e:
        print(f"❌ ERRO CRÍTICO: Não foi possível carregar o modelo.")
        print(e)

# Modelo de entrada flexível (Aceita qualquer JSON)
class FlexibleInput(BaseModel):
    features: Dict[str, Any]

class PatientHistoryInput(BaseModel):
    """Input model for endpoints requiring patient history."""
    current_data: Dict[str, Any]
    history: Optional[List[Dict[str, Any]]] = None

class MedicationAnalysisInput(BaseModel):
    """Input model for medication impact analysis."""
    patient_history: List[Dict[str, Any]]
    medication_change: Dict[str, Any]

@app.get("/")
def health():
    return {
        "status": "online", 
        "model_loaded": model is not None,
        "features_count": len(expected_features),
        "version": "3.0",
        "modules": {
            "clinical_prediction": clinical_predictor is not None,
            "self_knowledge": self_knowledge_analyzer is not None,
            "treatment_optimization": treatment_optimizer is not None,
            "engagement": engagement_analyzer is not None
        }
    }

@app.post("/predict")
def predict(payload: FlexibleInput, include_shap: bool = Query(False, description="Include SHAP analysis")):
    """
    Original crisis prediction endpoint (T+3 days) with optional SHAP analysis.
    
    Args:
        payload: Patient features
        include_shap: Whether to include SHAP values in response
        
    Returns:
        Crisis prediction with optional SHAP explanation
    """
    if not model:
        raise HTTPException(status_code=500, detail="Modelo não carregado no servidor.")
    
    try:
        # 1. Pegar dados brutos enviados pelo usuário
        input_data = payload.features
        
        # 2. Construir o dicionário completo (Auto-complete)
        # Se o usuário não mandou 'sleep_debt_3d', assumimos 0.0
        full_data = {}
        
        if len(expected_features) > 0:
            for feature in expected_features:
                if feature in input_data:
                    full_data[feature] = input_data[feature]
                else:
                    # Preenchimento inteligente de valores padrão
                    if "diagnosis" in feature or "medication" in feature:
                        full_data[feature] = "EUTHYMIC" # Valor seguro para categorias
                    else:
                        full_data[feature] = 0.0 # Valor seguro para números
        else:
            # Se não conseguimos ler as features do modelo, usamos o que veio
            full_data = input_data
        
        # 3. Criar DataFrame
        df = pd.DataFrame([full_data])
        
        # 4. Correção de Tipos (Essencial para LightGBM)
        # Converte colunas de texto para 'category' e números para 'float'
        for col in df.columns:
            if df[col].dtype == 'object':
                df[col] = df[col].astype('category')
            else:
                df[col] = df[col].astype(np.float32)

        # 5. Predição
        # predict_proba retorna [[prob_classe_0, prob_classe_1]]
        prob = float(model.predict_proba(df)[0][1])
        
        # 6. Lógica de Negócio (Semáforo)
        risk = "LOW"
        if prob > 0.5: risk = "MODERATE"
        if prob > 0.8: risk = "HIGH"
        
        result = {
            "probability": round(prob, 4),
            "risk_level": risk,
            "features_processed": len(df.columns),
            "alert": prob > 0.6,
            "timeframe_days": 3
        }
        
        # 7. Add SHAP analysis if requested
        if include_shap and self_knowledge_analyzer:
            try:
                shap_analysis = self_knowledge_analyzer.explain_prediction_shap(
                    model, df, top_n=3
                )
                result["shap_analysis"] = shap_analysis
            except Exception as e:
                result["shap_error"] = str(e)
        
        return result

    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=400, detail=f"Erro no processamento: {str(e)}")

# ========================================
# GROUP I: CLINICAL PREDICTION ENDPOINTS
# ========================================

@app.post("/predict/crisis/7d")
def predict_crisis_7d(payload: FlexibleInput):
    """
    Predict crisis risk for T+7 days.
    
    Args:
        payload: Patient features
        
    Returns:
        7-day crisis risk prediction
    """
    if not clinical_predictor:
        raise HTTPException(status_code=500, detail="Clinical predictor not initialized")
    
    try:
        input_data = payload.features
        df = prepare_model_input(input_data, expected_features=expected_features)
        result = clinical_predictor.predict_crisis_7d(df)
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error in 7-day prediction: {str(e)}")


@app.post("/predict/state/3d")
def predict_state_transition(payload: FlexibleInput):
    """
    Predict state transition for T+3 days (multi-class: Stable, Depressive, Manic, Mixed).
    
    Args:
        payload: Patient features
        
    Returns:
        State transition prediction with probabilities
    """
    if not clinical_predictor:
        raise HTTPException(status_code=500, detail="Clinical predictor not initialized")
    
    try:
        input_data = payload.features
        df = prepare_model_input(input_data, expected_features=expected_features)
        result = clinical_predictor.predict_state_transition(df)
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error in state prediction: {str(e)}")


@app.post("/predict/impulsive_behavior/2d")
def predict_impulsive_behavior(payload: FlexibleInput):
    """
    Predict impulsive behavior risk for T+2 days.
    
    Args:
        payload: Patient features
        
    Returns:
        Impulsive behavior risk prediction
    """
    if not clinical_predictor:
        raise HTTPException(status_code=500, detail="Clinical predictor not initialized")
    
    try:
        input_data = payload.features
        df = prepare_model_input(input_data, expected_features=expected_features)
        result = clinical_predictor.predict_impulsive_behavior(df)
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error in impulsive behavior prediction: {str(e)}")


# ========================================
# GROUP II: SELF-KNOWLEDGE ENDPOINTS
# ========================================

@app.get("/patient/{patient_id}/triggers")
def analyze_triggers(
    patient_id: str,
    history: Optional[str] = Query(None, description="JSON string of patient history")
):
    """
    Analyze environmental triggers from patient history.
    
    Args:
        patient_id: Patient identifier
        history: JSON string with patient history data
        
    Returns:
        Identified triggers and patterns
    """
    if not self_knowledge_analyzer:
        raise HTTPException(status_code=500, detail="Self-knowledge analyzer not initialized")
    
    try:
        import json
        patient_history = json.loads(history) if history else []
        result = self_knowledge_analyzer.analyze_environmental_triggers(patient_history)
        result["patient_id"] = patient_id
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error in trigger analysis: {str(e)}")


@app.get("/patient/{patient_id}/mood_clusters")
def cluster_mood_states(
    patient_id: str,
    history: Optional[str] = Query(None, description="JSON string of patient history"),
    n_clusters: int = Query(4, description="Number of clusters")
):
    """
    Cluster mood states to identify patterns.
    
    Args:
        patient_id: Patient identifier
        history: JSON string with patient history data
        n_clusters: Number of clusters to identify
        
    Returns:
        Mood cluster analysis
    """
    if not self_knowledge_analyzer:
        raise HTTPException(status_code=500, detail="Self-knowledge analyzer not initialized")
    
    try:
        import json
        patient_history = json.loads(history) if history else []
        result = self_knowledge_analyzer.cluster_mood_states(patient_history, n_clusters)
        result["patient_id"] = patient_id
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error in mood clustering: {str(e)}")


# ========================================
# GROUP III: TREATMENT OPTIMIZATION ENDPOINTS
# ========================================

@app.post("/predict/medication_adherence/3d")
def predict_medication_adherence(payload: FlexibleInput):
    """
    Predict medication adherence risk for T+3 days.
    
    Args:
        payload: Patient features
        
    Returns:
        Medication adherence prediction with recommendations
    """
    if not treatment_optimizer:
        raise HTTPException(status_code=500, detail="Treatment optimizer not initialized")
    
    try:
        input_data = payload.features
        df = prepare_model_input(input_data, expected_features=expected_features)
        result = treatment_optimizer.predict_medication_adherence(df)
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error in adherence prediction: {str(e)}")


@app.post("/analyze/medication_impact")
def analyze_medication_impact(payload: MedicationAnalysisInput):
    """
    Analyze causal impact of medication changes using before/after analysis.
    
    Args:
        payload: Patient history and medication change information
        
    Returns:
        Causal analysis of medication impact
    """
    if not treatment_optimizer:
        raise HTTPException(status_code=500, detail="Treatment optimizer not initialized")
    
    try:
        result = treatment_optimizer.analyze_medication_impact(
            payload.patient_history,
            payload.medication_change
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error in medication analysis: {str(e)}")


@app.get("/patient/{patient_id}/habit_optimization")
def optimize_habit(
    patient_id: str,
    habit: str = Query("exerciseDurationMin", description="Habit to optimize"),
    history: Optional[str] = Query(None, description="JSON string of patient history")
):
    """
    Optimize a single habit by analyzing its correlation with mood stability.
    
    Args:
        patient_id: Patient identifier
        habit: Name of habit to optimize (e.g., 'exerciseDurationMin')
        history: JSON string with patient history data
        
    Returns:
        Habit optimization recommendations
    """
    if not treatment_optimizer:
        raise HTTPException(status_code=500, detail="Treatment optimizer not initialized")
    
    try:
        import json
        patient_history = json.loads(history) if history else []
        result = treatment_optimizer.optimize_habit(patient_history, habit)
        result["patient_id"] = patient_id
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error in habit optimization: {str(e)}")


# ========================================
# GROUP IV: ENGAGEMENT ENDPOINTS
# ========================================

@app.get("/patient/{patient_id}/churn_risk")
def predict_churn_risk(
    patient_id: str,
    history: Optional[str] = Query(None, description="JSON string of patient history")
):
    """
    Predict user churn risk using engagement metrics.
    
    Args:
        patient_id: Patient identifier
        history: JSON string with patient history data
        
    Returns:
        Churn risk prediction with recommendations
    """
    if not engagement_analyzer:
        raise HTTPException(status_code=500, detail="Engagement analyzer not initialized")
    
    try:
        import json
        patient_history = json.loads(history) if history else []
        result = engagement_analyzer.predict_churn_risk(patient_history, patient_id)
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error in churn prediction: {str(e)}")


# ========================================
# UTILITY ENDPOINTS
# ========================================

@app.get("/api/info")
def api_info():
    """
    Get comprehensive API information and available endpoints.
    
    Returns:
        API capabilities and endpoint documentation
    """
    return {
        "title": "Bipolar AI Engine - Expanded Analytics Platform",
        "version": "3.0",
        "description": "Comprehensive bipolar disorder analysis with predictive analytics",
        "endpoints": {
            "clinical_prediction": [
                {"path": "/predict", "method": "POST", "description": "3-day crisis prediction (original)"},
                {"path": "/predict/crisis/7d", "method": "POST", "description": "7-day crisis prediction"},
                {"path": "/predict/state/3d", "method": "POST", "description": "3-day state transition (multi-class)"},
                {"path": "/predict/impulsive_behavior/2d", "method": "POST", "description": "2-day impulsive behavior risk"}
            ],
            "self_knowledge": [
                {"path": "/patient/{id}/triggers", "method": "GET", "description": "Environmental triggers analysis"},
                {"path": "/patient/{id}/mood_clusters", "method": "GET", "description": "Mood state clustering"}
            ],
            "treatment_optimization": [
                {"path": "/predict/medication_adherence/3d", "method": "POST", "description": "Medication adherence prediction"},
                {"path": "/analyze/medication_impact", "method": "POST", "description": "Causal medication impact analysis"},
                {"path": "/patient/{id}/habit_optimization", "method": "GET", "description": "Single habit optimization"}
            ],
            "engagement": [
                {"path": "/patient/{id}/churn_risk", "method": "GET", "description": "User churn risk prediction"}
            ]
        },
        "features": [
            "SHAP-based root cause analysis (add ?include_shap=true to /predict)",
            "Multi-class state prediction (Stable, Depressive, Manic, Mixed)",
            "Environmental trigger identification",
            "Mood pattern clustering",
            "Medication impact analysis",
            "Habit-mood correlation optimization",
            "Engagement and churn prediction"
        ]
    }
