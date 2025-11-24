# api/models.py
"""
Lazy model loading interface - delegates to models.registry.
Models are loaded on-demand when first accessed, not at startup.
Maintained for backward compatibility with existing code.
"""
import logging
from pathlib import Path
from models.registry import init_models as registry_init_models, get_model

logger = logging.getLogger("bipolar-api.models")

# Constrói o caminho para a pasta 'models' a partir da localização deste arquivo
BASE_DIR = Path(__file__).resolve(strict=True).parent.parent
MODELS_DIR = BASE_DIR / "models"


class _ModelsDict(dict):
    """
    Dictionary wrapper that delegates to the model registry.
    Provides backward compatibility with existing code using MODELS dict.
    """
    def __getitem__(self, key):
        model = get_model(key)
        if model is None:
            raise KeyError(key)
        return model
    
    def get(self, key, default=None):
        model = get_model(key)
        return model if model is not None else default
    
    def __contains__(self, key):
        return get_model(key) is not None


# Global MODELS dict for backward compatibility
MODELS = _ModelsDict()


def load_models():
    """
    Initialize the model registry with lazy loading.
    Called during application startup.
    
    Models are NOT loaded at this point - they are loaded on-demand
    when first accessed via get_model() or MODELS dict.
    This significantly reduces startup time from ~15s to <2s.
    
    This function delegates to models.registry.init_models() for
    thread-safe lazy loading with singleton pattern.
    """
    logger.info("Initializing model registry with lazy loading...")
    registry_init_models(MODELS_DIR)
    logger.info("Model registry initialized (models will load on-demand)")


# Exemplo de como acessar um modelo (usaremos isso nos outros arquivos):
# from .models import MODELS
# multiclass_model = MODELS.get('lgbm_multiclass_v1')
