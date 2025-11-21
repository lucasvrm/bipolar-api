# models/registry.py
"""
Thread-safe model registry for managing ML models at application startup.
Ensures models are loaded once and reused across requests.
"""
import joblib
import logging
import threading
from pathlib import Path
from typing import Dict, Any, Optional

logger = logging.getLogger("bipolar-api.models")

class ModelRegistry:
    """
    Singleton registry for ML models with thread-safe initialization.
    Models are loaded once at startup and cached for the application lifetime.
    """
    _instance = None
    _lock = threading.Lock()
    _models: Dict[str, Any] = {}
    _initialized = False
    
    def __new__(cls):
        """Singleton pattern: ensure only one instance exists."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance
    
    def init_models(self, models_dir: Optional[Path] = None) -> None:
        """
        Load all .pkl models from the models directory.
        Thread-safe initialization that runs only once.
        
        Args:
            models_dir: Path to models directory. If None, uses default location.
        """
        with self._lock:
            if self._initialized:
                logger.info("Models already initialized, skipping...")
                return
            
            if models_dir is None:
                # Default: models/ directory relative to this file
                models_dir = Path(__file__).resolve().parent
            
            if not models_dir.exists():
                logger.warning(f"Models directory not found: {models_dir}")
                self._initialized = True
                return
            
            logger.info(f"Loading models from: {models_dir}")
            model_files = list(models_dir.glob("*.pkl"))
            
            if not model_files:
                logger.warning("No .pkl model files found in models directory")
            
            for file_path in model_files:
                model_name = file_path.stem
                try:
                    self._models[model_name] = joblib.load(file_path)
                    logger.info(f"✓ Loaded model: {model_name}")
                except Exception as e:
                    logger.error(f"✗ Failed to load model '{model_name}': {e}")
            
            self._initialized = True
            logger.info(f"Model registry initialized with {len(self._models)} models")
            
            # Log model inventory
            if self._models:
                logger.info("Available models:")
                for model_name in sorted(self._models.keys()):
                    model_type = type(self._models[model_name]).__name__
                    logger.info(f"  - {model_name} ({model_type})")
    
    def get_model(self, name: str) -> Optional[Any]:
        """
        Get a model by name.
        
        Args:
            name: Model identifier (e.g., 'lgbm_multiclass_v1')
            
        Returns:
            Model object if found, None otherwise
        """
        if not self._initialized:
            logger.warning("ModelRegistry.get_model() called before initialization")
            return None
        
        return self._models.get(name)
    
    def list_models(self) -> Dict[str, str]:
        """
        List all available models with their types.
        
        Returns:
            Dictionary mapping model names to their type names
        """
        return {
            name: type(model).__name__ 
            for name, model in self._models.items()
        }
    
    def is_initialized(self) -> bool:
        """Check if the registry has been initialized."""
        return self._initialized
    
    def model_count(self) -> int:
        """Get the number of loaded models."""
        return len(self._models)


# Global singleton instance
_registry = ModelRegistry()


def init_models(models_dir: Optional[Path] = None) -> None:
    """
    Initialize the global model registry.
    Should be called once at application startup.
    
    Args:
        models_dir: Optional path to models directory
    """
    _registry.init_models(models_dir)


def get_model(name: str) -> Optional[Any]:
    """
    Retrieve a model from the global registry.
    
    Args:
        name: Model identifier
        
    Returns:
        Model object if found, None otherwise
    """
    return _registry.get_model(name)


def get_registry() -> ModelRegistry:
    """
    Get the global model registry instance.
    
    Returns:
        The singleton ModelRegistry instance
    """
    return _registry
