import joblib
import pandas as pd
import numpy as np
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Dict, Any, List

# --- CONFIGURAÇÕES ---
MODEL_FILE = 'lightgbm_crisis_binary_v1.pkl'

app = FastAPI(title="Bipolar AI Engine", version="2.0")

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

@app.on_event("startup")
def load_model_and_features():
    global model, expected_features
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
        
    except Exception as e:
        print(f"❌ ERRO CRÍTICO: Não foi possível carregar o modelo.")
        print(e)

# Modelo de entrada flexível (Aceita qualquer JSON)
class FlexibleInput(BaseModel):
    features: Dict[str, Any]

@app.get("/")
def health():
    return {
        "status": "online", 
        "model_loaded": model is not None,
        "features_count": len(expected_features)
    }

@app.post("/predict")
def predict(payload: FlexibleInput):
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
        
        return {
            "probability": round(prob, 4),
            "risk_level": risk,
            "features_processed": len(df.columns),
            "alert": prob > 0.6
        }

    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=400, detail=f"Erro no processamento: {str(e)}")