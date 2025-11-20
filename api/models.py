# api/models.py
import joblib
import os
from pathlib import Path

# Constrói o caminho para a pasta 'models' a partir da localização deste arquivo
BASE_DIR = Path(__file__).resolve(strict=True).parent.parent
MODELS_DIR = BASE_DIR / "models"

MODELS = {}

def load_models():
    """
    Carrega todos os modelos .pkl da pasta /models e os armazena
    no dicionário global MODELS. É chamado na inicialização da API.
    """
    if not MODELS_DIR.exists():
        print(f"Diretório de modelos não encontrado em: {MODELS_DIR}")
        return

    print("Carregando modelos de IA...")
    for file_path in MODELS_DIR.glob("*.pkl"):
        model_name = file_path.stem  # ex: 'lgbm_multiclass_v1'
        try:
            MODELS[model_name] = joblib.load(file_path)
            print(f"- Modelo '{model_name}' carregado com sucesso.")
        except Exception as e:
            print(f"Erro ao carregar o modelo '{model_name}': {e}")
    
    if not MODELS:
        print("Nenhum modelo foi carregado.")
    else:
        print("Todos os modelos foram carregados.")

# Exemplo de como acessar um modelo (usaremos isso nos outros arquivos):
# from .models import MODELS
# multiclass_model = MODELS.get('lgbm_multiclass_v1')
