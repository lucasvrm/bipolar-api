# tests/test_model_registry.py
"""
Unit tests for the thread-safe model registry.
"""
import pytest
import tempfile
import joblib
from pathlib import Path
from unittest.mock import patch, MagicMock
from models.registry import ModelRegistry, init_models, get_model, get_registry


class DummyModel:
    """Dummy model for testing."""
    def __init__(self, name):
        self.name = name
    
    def predict(self, X):
        return [1, 2, 3]


@pytest.fixture
def temp_models_dir():
    """Create a temporary directory with mock models."""
    with tempfile.TemporaryDirectory() as tmpdir:
        models_dir = Path(tmpdir)
        
        # Create some dummy models
        model1 = DummyModel("model1")
        model2 = DummyModel("model2")
        
        joblib.dump(model1, models_dir / "test_model_v1.pkl")
        joblib.dump(model2, models_dir / "test_model_v2.pkl")
        
        yield models_dir


def test_singleton_pattern():
    """Test that ModelRegistry follows singleton pattern."""
    registry1 = ModelRegistry()
    registry2 = ModelRegistry()
    
    assert registry1 is registry2
    assert id(registry1) == id(registry2)


def test_init_models_does_not_eagerly_load(temp_models_dir):
    """Test that init_models does NOT eagerly load models (lazy loading)."""
    # Reset registry for test
    registry = ModelRegistry()
    registry._initialized = False
    registry._models.clear()
    
    # Initialize with temp directory
    registry.init_models(temp_models_dir)
    
    assert registry.is_initialized()
    # With lazy loading, no models should be loaded yet
    assert registry.model_count() == 0
    assert len(registry.list_models()) == 0


def test_get_model_lazy_loads_on_demand(temp_models_dir):
    """Test that get_model lazy loads models on first access."""
    # Reset and initialize registry
    registry = ModelRegistry()
    registry._initialized = False
    registry._models.clear()
    registry.init_models(temp_models_dir)
    
    # Initially no models loaded
    assert registry.model_count() == 0
    
    # First access should trigger lazy loading
    model = registry.get_model("test_model_v1")
    
    assert model is not None
    assert isinstance(model, DummyModel)
    assert model.name == "model1"
    
    # Now one model should be cached
    assert registry.model_count() == 1
    assert "test_model_v1" in registry.list_models()


def test_get_model_caches_after_first_load(temp_models_dir):
    """Test that models are cached after first load."""
    # Reset and initialize registry
    registry = ModelRegistry()
    registry._initialized = False
    registry._models.clear()
    registry.init_models(temp_models_dir)
    
    # First access
    model1 = registry.get_model("test_model_v1")
    assert model1 is not None
    assert registry.model_count() == 1
    
    # Second access should return cached model (same object)
    model2 = registry.get_model("test_model_v1")
    assert model2 is model1  # Same object reference


def test_get_model_returns_none_for_missing_model(temp_models_dir):
    """Test that get_model returns None for non-existent models."""
    # Reset and initialize registry
    registry = ModelRegistry()
    registry._initialized = False
    registry._models.clear()
    registry.init_models(temp_models_dir)
    
    model = registry.get_model("nonexistent_model")
    
    assert model is None


def test_init_models_only_runs_once(temp_models_dir):
    """Test that init_models only initializes once."""
    # Reset registry
    registry = ModelRegistry()
    registry._initialized = False
    registry._models.clear()
    
    # First initialization
    registry.init_models(temp_models_dir)
    assert registry.is_initialized()
    
    # Load a model to verify it works
    model = registry.get_model("test_model_v1")
    assert model is not None
    assert registry.model_count() == 1
    
    # Second initialization should be skipped
    registry.init_models(temp_models_dir)
    
    # Model should still be cached
    assert registry.model_count() == 1


def test_init_models_handles_missing_directory():
    """Test that init_models handles missing directory gracefully."""
    # Reset registry
    registry = ModelRegistry()
    registry._initialized = False
    registry._models.clear()
    
    # Initialize with non-existent directory
    registry.init_models(Path("/nonexistent/path"))
    
    assert registry.is_initialized()
    assert registry.model_count() == 0


def test_init_models_handles_corrupt_model_file(temp_models_dir):
    """Test that get_model handles corrupt .pkl files gracefully during lazy loading."""
    # Reset registry
    registry = ModelRegistry()
    registry._initialized = False
    registry._models.clear()
    
    # Create a corrupt .pkl file
    corrupt_file = temp_models_dir / "corrupt_model.pkl"
    corrupt_file.write_text("This is not a valid pickle file")
    
    # Initialize (should discover 3 files but not load them yet)
    registry.init_models(temp_models_dir)
    
    assert registry.is_initialized()
    # No models loaded yet
    assert registry.model_count() == 0
    
    # Try to load the corrupt model - should return None
    corrupt_model = registry.get_model("corrupt_model")
    assert corrupt_model is None
    
    # Valid models should still load fine
    valid_model = registry.get_model("test_model_v1")
    assert valid_model is not None
    assert registry.model_count() == 1


def test_list_models_returns_only_loaded_models(temp_models_dir):
    """Test that list_models returns only models that have been loaded."""
    # Reset and initialize registry
    registry = ModelRegistry()
    registry._initialized = False
    registry._models.clear()
    registry.init_models(temp_models_dir)
    
    # Initially empty
    models = registry.list_models()
    assert len(models) == 0
    
    # Load one model
    registry.get_model("test_model_v1")
    models = registry.list_models()
    assert len(models) == 1
    assert models["test_model_v1"] == "DummyModel"
    
    # Load another model
    registry.get_model("test_model_v2")
    models = registry.list_models()
    assert len(models) == 2
    assert models["test_model_v2"] == "DummyModel"


def test_global_functions(temp_models_dir):
    """Test the global module-level functions with lazy loading."""
    # Reset global registry
    from models import registry as reg_module
    reg_module._registry._initialized = False
    reg_module._registry._models.clear()
    
    # Test init_models
    init_models(temp_models_dir)
    
    # Test get_model (should lazy load)
    model = get_model("test_model_v1")
    assert model is not None
    assert isinstance(model, DummyModel)
    
    # Test get_registry
    registry = get_registry()
    assert isinstance(registry, ModelRegistry)
    assert registry.is_initialized()
    assert registry.model_count() == 1  # Only one model loaded so far


def test_lazy_loading_thread_safety(temp_models_dir):
    """Test that lazy loading is thread-safe when multiple threads request same model."""
    import threading
    
    # Reset registry
    registry = ModelRegistry()
    registry._initialized = False
    registry._models.clear()
    registry.init_models(temp_models_dir)
    
    results = []
    errors = []
    
    def load_model():
        try:
            model = registry.get_model("test_model_v1")
            results.append(model)
        except Exception as e:
            errors.append(e)
    
    # Create multiple threads that all try to load the same model
    threads = [threading.Thread(target=load_model) for _ in range(10)]
    
    for thread in threads:
        thread.start()
    
    for thread in threads:
        thread.join()
    
    # Should have no errors
    assert len(errors) == 0
    
    # All threads should get the same model object (cached)
    assert len(results) == 10
    assert all(model is results[0] for model in results)
    
    # Model should only be loaded once
    assert registry.model_count() == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
