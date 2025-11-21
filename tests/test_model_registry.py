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


def test_init_models_loads_from_directory(temp_models_dir):
    """Test that init_models loads all .pkl files from directory."""
    # Reset registry for test
    registry = ModelRegistry()
    registry._initialized = False
    registry._models.clear()
    
    # Initialize with temp directory
    registry.init_models(temp_models_dir)
    
    assert registry.is_initialized()
    assert registry.model_count() == 2
    assert "test_model_v1" in registry.list_models()
    assert "test_model_v2" in registry.list_models()


def test_get_model_returns_loaded_model(temp_models_dir):
    """Test that get_model returns the correct model."""
    # Reset and initialize registry
    registry = ModelRegistry()
    registry._initialized = False
    registry._models.clear()
    registry.init_models(temp_models_dir)
    
    model = registry.get_model("test_model_v1")
    
    assert model is not None
    assert isinstance(model, DummyModel)
    assert model.name == "model1"


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
    initial_count = registry.model_count()
    
    # Second initialization should be skipped
    registry.init_models(temp_models_dir)
    
    assert registry.model_count() == initial_count


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
    """Test that init_models handles corrupt .pkl files gracefully."""
    # Reset registry
    registry = ModelRegistry()
    registry._initialized = False
    registry._models.clear()
    
    # Create a corrupt .pkl file
    corrupt_file = temp_models_dir / "corrupt_model.pkl"
    corrupt_file.write_text("This is not a valid pickle file")
    
    # Should not crash, just skip the corrupt file
    registry.init_models(temp_models_dir)
    
    assert registry.is_initialized()
    # Should still have the 2 valid models
    assert registry.model_count() == 2


def test_list_models_returns_model_types(temp_models_dir):
    """Test that list_models returns model names and types."""
    # Reset and initialize registry
    registry = ModelRegistry()
    registry._initialized = False
    registry._models.clear()
    registry.init_models(temp_models_dir)
    
    models = registry.list_models()
    
    assert len(models) == 2
    assert models["test_model_v1"] == "DummyModel"
    assert models["test_model_v2"] == "DummyModel"


def test_global_functions(temp_models_dir):
    """Test the global module-level functions."""
    # Reset global registry
    from models import registry as reg_module
    reg_module._registry._initialized = False
    reg_module._registry._models.clear()
    
    # Test init_models
    init_models(temp_models_dir)
    
    # Test get_model
    model = get_model("test_model_v1")
    assert model is not None
    assert isinstance(model, DummyModel)
    
    # Test get_registry
    registry = get_registry()
    assert isinstance(registry, ModelRegistry)
    assert registry.is_initialized()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
