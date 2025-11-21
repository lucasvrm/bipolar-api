# tests/test_prediction_cache.py
"""
Unit tests for the Redis-based prediction cache.
"""
import pytest
import json
from unittest.mock import AsyncMock, MagicMock, patch
from services.prediction_cache import PredictionCache, get_cache


@pytest.fixture
def mock_redis_client():
    """Create a mock Redis client."""
    mock_client = AsyncMock()
    mock_client.ping = AsyncMock(return_value=True)
    mock_client.get = AsyncMock(return_value=None)
    mock_client.setex = AsyncMock(return_value=True)
    mock_client.delete = AsyncMock(return_value=0)
    mock_client.scan_iter = AsyncMock(return_value=iter([]))
    mock_client.close = AsyncMock()
    return mock_client


@pytest.mark.asyncio
async def test_cache_disabled_without_redis_url():
    """Test that cache is disabled when REDIS_URL is not set."""
    with patch.dict('os.environ', {}, clear=True):
        cache = PredictionCache()
        
        assert not cache._enabled
        
        result = await cache.get("user123", 3, ["mood_state"])
        assert result is None
        
        success = await cache.set("user123", 3, ["mood_state"], {"data": "test"})
        assert not success


@pytest.mark.asyncio
async def test_cache_generates_consistent_keys():
    """Test that cache keys are deterministic and consistent."""
    with patch.dict('os.environ', {'REDIS_URL': 'redis://localhost:6379'}):
        cache = PredictionCache()
        
        key1 = cache._generate_cache_key("user123", 3, ["mood_state", "relapse_risk"])
        key2 = cache._generate_cache_key("user123", 3, ["relapse_risk", "mood_state"])
        
        # Should be the same regardless of order
        assert key1 == key2
        
        # Different parameters should produce different keys
        key3 = cache._generate_cache_key("user123", 7, ["mood_state", "relapse_risk"])
        assert key1 != key3


@pytest.mark.asyncio
async def test_cache_get_returns_none_on_miss(mock_redis_client):
    """Test that cache.get returns None on cache miss."""
    with patch.dict('os.environ', {'REDIS_URL': 'redis://localhost:6379'}):
        with patch('services.prediction_cache.redis') as mock_redis:
            mock_redis.from_url = MagicMock(return_value=mock_redis_client)
            mock_redis_client.get.return_value = None
            
            cache = PredictionCache()
            result = await cache.get("user123", 3, ["mood_state"])
            
            assert result is None
            mock_redis_client.get.assert_called_once()


@pytest.mark.asyncio
async def test_cache_get_returns_data_on_hit(mock_redis_client):
    """Test that cache.get returns cached data on cache hit."""
    cached_data = {"predictions": [{"type": "mood_state", "label": "Euthymia"}]}
    
    with patch.dict('os.environ', {'REDIS_URL': 'redis://localhost:6379'}):
        with patch('services.prediction_cache.redis') as mock_redis:
            mock_redis.from_url = MagicMock(return_value=mock_redis_client)
            mock_redis_client.get.return_value = json.dumps(cached_data)
            
            cache = PredictionCache()
            result = await cache.get("user123", 3, ["mood_state"])
            
            assert result == cached_data
            mock_redis_client.get.assert_called_once()


@pytest.mark.asyncio
async def test_cache_set_stores_data(mock_redis_client):
    """Test that cache.set stores data with correct TTL."""
    data_to_cache = {"predictions": [{"type": "mood_state"}]}
    
    with patch.dict('os.environ', {'REDIS_URL': 'redis://localhost:6379'}):
        with patch('services.prediction_cache.redis') as mock_redis:
            mock_redis.from_url = MagicMock(return_value=mock_redis_client)
            
            cache = PredictionCache()
            success = await cache.set("user123", 3, ["mood_state"], data_to_cache, ttl_seconds=600)
            
            assert success
            mock_redis_client.setex.assert_called_once()
            
            # Verify the data was serialized
            call_args = mock_redis_client.setex.call_args
            assert json.loads(call_args[0][2]) == data_to_cache


@pytest.mark.asyncio
async def test_cache_invalidate_deletes_user_keys(mock_redis_client):
    """Test that cache.invalidate removes all keys for a user."""
    # Create an async generator that returns keys
    async def mock_scan(*args, **kwargs):
        for key in ["prediction:user123:3:abc", "prediction:user123:7:def"]:
            yield key
    
    with patch.dict('os.environ', {'REDIS_URL': 'redis://localhost:6379'}):
        with patch('services.prediction_cache.redis') as mock_redis:
            mock_redis.from_url = MagicMock(return_value=mock_redis_client)
            # Return the async generator, not calling it
            mock_redis_client.scan_iter = mock_scan
            mock_redis_client.delete.return_value = 2
            
            cache = PredictionCache()
            deleted = await cache.invalidate("user123")
            
            assert deleted == 2
            mock_redis_client.delete.assert_called_once()


@pytest.mark.asyncio
async def test_cache_handles_redis_connection_failure():
    """Test that cache handles Redis connection failures gracefully."""
    with patch.dict('os.environ', {'REDIS_URL': 'redis://localhost:6379'}):
        with patch('services.prediction_cache.redis') as mock_redis:
            # Simulate connection failure
            mock_client = AsyncMock()
            mock_client.ping = AsyncMock(side_effect=Exception("Connection failed"))
            mock_redis.from_url = MagicMock(return_value=mock_client)
            
            cache = PredictionCache()
            
            # Should handle gracefully
            result = await cache.get("user123", 3, ["mood_state"])
            assert result is None
            
            success = await cache.set("user123", 3, ["mood_state"], {"data": "test"})
            assert not success


@pytest.mark.asyncio
async def test_cache_handles_get_errors_gracefully(mock_redis_client):
    """Test that cache.get handles errors gracefully."""
    with patch.dict('os.environ', {'REDIS_URL': 'redis://localhost:6379'}):
        with patch('services.prediction_cache.redis') as mock_redis:
            mock_redis.from_url = MagicMock(return_value=mock_redis_client)
            mock_redis_client.get.side_effect = Exception("Redis error")
            
            cache = PredictionCache()
            result = await cache.get("user123", 3, ["mood_state"])
            
            assert result is None  # Should return None instead of crashing


@pytest.mark.asyncio
async def test_cache_handles_set_errors_gracefully(mock_redis_client):
    """Test that cache.set handles errors gracefully."""
    with patch.dict('os.environ', {'REDIS_URL': 'redis://localhost:6379'}):
        with patch('services.prediction_cache.redis') as mock_redis:
            mock_redis.from_url = MagicMock(return_value=mock_redis_client)
            mock_redis_client.setex.side_effect = Exception("Redis error")
            
            cache = PredictionCache()
            success = await cache.set("user123", 3, ["mood_state"], {"data": "test"})
            
            assert not success  # Should return False instead of crashing


@pytest.mark.asyncio
async def test_get_cache_returns_singleton():
    """Test that get_cache returns the same instance."""
    cache1 = get_cache()
    cache2 = get_cache()
    
    assert cache1 is cache2


@pytest.mark.asyncio
async def test_cache_close(mock_redis_client):
    """Test that cache.close closes the Redis connection."""
    with patch.dict('os.environ', {'REDIS_URL': 'redis://localhost:6379'}):
        with patch('services.prediction_cache.redis') as mock_redis:
            mock_redis.from_url = MagicMock(return_value=mock_redis_client)
            
            cache = PredictionCache()
            await cache._get_client()  # Force connection
            await cache.close()
            
            mock_redis_client.close.assert_called_once()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
