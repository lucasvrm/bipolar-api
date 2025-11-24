# models/registry.py
"""
Thread-safe model registry with lazy loading for ML models.
Models are loaded on-demand when first accessed, not at application startup.
This significantly reduces startup time and initial memory footprint.
"""
import joblib
import logging
import threading
from pathlib import Path
from typing import Dict, Any, Optional

logger = logging.getLogger("bipolar-api.models")

class ModelRegistry:
    """
    Singleton registry for ML models with thread-safe lazy loading.
    Models are loaded on-demand when first accessed and cached for reuse.
    This improves startup time by deferring model loading until needed.
    """
    # Class variables are intentional for singleton pattern - shared across all instances
    _instance = None
    _lock = threading.Lock()
    _models: Dict[str, Any] = {}
    _models_dir: Optional[Path] = None
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
        Initialize the model registry with lazy loading.
        Models are NOT loaded at startup - they are loaded on-demand.
        
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
            
            # Store the models directory path for lazy loading
            self._models_dir = models_dir
            
            logger.info(f"Model registry initialized with lazy loading from: {models_dir}")
            
            # Discover available model files without loading them
            model_files = list(models_dir.glob("*.pkl"))
            if not model_files:
                logger.warning("No .pkl model files found in models directory")
            else:
                logger.info(f"Discovered {len(model_files)} model files (will load on-demand)")
                for file_path in sorted(model_files):
                    logger.info(f"  - {file_path.stem}.pkl")
            
            self._initialized = True
    
    def get_model(self, name: str) -> Optional[Any]:
        """
        Get a model by name, loading it lazily if not already cached.
        Thread-safe lazy loading with caching.
        
        Args:
            name: Model identifier (e.g., 'lgbm_multiclass_v1')
            
        Returns:
            Model object if found, None otherwise
        """
        if not self._initialized:
            logger.warning("ModelRegistry.get_model() called before initialization")
            return None
        
        # Fast path: model already loaded
        if name in self._models:
            return self._models[name]
        
        # Slow path: load model on-demand (thread-safe)
        with self._lock:
            # Double-check: another thread might have loaded it while we waited
            if name in self._models:
                return self._models[name]
            
            # Try to load the model
            if self._models_dir is None:
                logger.warning(f"Cannot load model '{name}': models directory not set")
                return None
            
            model_path = self._models_dir / f"{name}.pkl"
            if not model_path.exists():
                logger.warning(f"Model file not found: {model_path}")
                return None
            
            try:
                logger.info(f"Lazy loading model: {name}")
                self._models[name] = joblib.load(model_path)
                model_type = type(self._models[name]).__name__
                logger.info(f"✓ Loaded model: {name} ({model_type})")
                return self._models[name]
            except Exception as e:
                logger.error(f"✗ Failed to load model '{name}': {e}")
                return None
    
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
    Initialize the global model registry with lazy loading.
    Should be called once at application startup.
    Models are NOT loaded during initialization - they load on first access.
    
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
