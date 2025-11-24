# services/prediction_cache.py
"""
Redis-based caching layer for prediction results.
Gracefully degrades when Redis is unavailable.
"""
import json
import logging
import hashlib
import os
from typing import Optional, Dict, Any, List
from datetime import timedelta

logger = logging.getLogger("bipolar-api.cache")

# Try to import Redis, but don't fail if it's not available
try:
    import redis.asyncio as redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False
    logger.warning("Redis library not available - caching will be disabled")


class PredictionCache:
    """
    Async Redis cache for prediction results with graceful degradation.
    """
    
    def __init__(self):
        """Initialize cache connection (lazy - connects on first use)."""
        self._redis_client: Optional[redis.Redis] = None
        self._enabled = False
        self._redis_url = os.getenv("REDIS_URL")
        
        if not REDIS_AVAILABLE:
            logger.info("Redis caching disabled (library not installed)")
            return
        
        if not self._redis_url:
            logger.info("Redis caching disabled (REDIS_URL not configured)")
            return
        
        self._enabled = True
        logger.info(f"Redis caching enabled with URL: {self._redis_url[:20]}...")
    
    async def _get_client(self) -> Optional[redis.Redis]:
        """
        Get or create Redis client connection.
        Returns None if connection fails.
        """
        if not self._enabled:
            return None
        
        if self._redis_client is None:
            try:
                self._redis_client = redis.from_url(
                    self._redis_url,
                    encoding="utf-8",
                    decode_responses=True,
                    socket_connect_timeout=2,
                    socket_timeout=2
                )
                # Test connection
                await self._redis_client.ping()
                logger.info("Redis connection established successfully")
            except Exception as e:
                logger.warning(f"Failed to connect to Redis: {e}")
                self._enabled = False
                return None
        
        return self._redis_client
    
    def _generate_cache_key(
        self,
        user_id: str,
        window_days: int,
        prediction_types: List[str]
    ) -> str:
        """
        Generate a cache key for prediction results.
        
        Args:
            user_id: User identifier
            window_days: Temporal window in days
            prediction_types: Sorted list of prediction types
            
        Returns:
            Cache key string
        """
        # Sort types to ensure consistent key generation
        types_str = ",".join(sorted(prediction_types))
        
        # Create a deterministic key
        key_data = f"{user_id}:{window_days}:{types_str}"
        
        # Use SHA-256 for better hash quality (not security-critical, but better than MD5)
        import hashlib
        key_hash = hashlib.sha256(key_data.encode()).hexdigest()[:16]
        
        return f"prediction:{user_id}:{window_days}:{key_hash}"
    
    async def get(
        self,
        user_id: str,
        window_days: int,
        prediction_types: List[str]
    ) -> Optional[Dict[str, Any]]:
        """
        Retrieve cached prediction results.
        
        Args:
            user_id: User identifier
            window_days: Temporal window in days
            prediction_types: List of prediction types
            
        Returns:
            Cached prediction data or None if not found/error
        """
        client = await self._get_client()
        if client is None:
            return None
        
        cache_key = self._generate_cache_key(user_id, window_days, prediction_types)
        
        try:
            cached_data = await client.get(cache_key)
            if cached_data:
                logger.debug(f"Cache HIT for key: {cache_key}")
                return json.loads(cached_data)
            else:
                logger.debug(f"Cache MISS for key: {cache_key}")
                return None
        except Exception as e:
            logger.warning(f"Cache GET error: {e}")
            return None
    
    async def set(
        self,
        user_id: str,
        window_days: int,
        prediction_types: List[str],
        data: Dict[str, Any],
        ttl_seconds: int = 300
    ) -> bool:
        """
        Store prediction results in cache.
        
        Args:
            user_id: User identifier
            window_days: Temporal window in days
            prediction_types: List of prediction types
            data: Prediction data to cache
            ttl_seconds: Time-to-live in seconds (default: 5 minutes)
            
        Returns:
            True if cached successfully, False otherwise
        """
        client = await self._get_client()
        if client is None:
            return False
        
        cache_key = self._generate_cache_key(user_id, window_days, prediction_types)
        
        try:
            serialized_data = json.dumps(data)
            await client.setex(
                cache_key,
                timedelta(seconds=ttl_seconds),
                serialized_data
            )
            logger.debug(f"Cache SET for key: {cache_key} (TTL: {ttl_seconds}s)")
            return True
        except Exception as e:
            logger.warning(f"Cache SET error: {e}")
            return False
    
    async def invalidate(self, user_id: str) -> int:
        """
        Invalidate all cached predictions for a user.
        
        Args:
            user_id: User identifier
            
        Returns:
            Number of keys deleted
        """
        client = await self._get_client()
        if client is None:
            return 0
        
        try:
            # Find all keys for this user
            pattern = f"prediction:{user_id}:*"
            keys = []
            # scan_iter returns a sync generator, not async
            cursor = client.scan_iter(match=pattern, count=100)
            for key in cursor:
                keys.append(key)
            
            if keys:
                deleted = await client.delete(*keys)
                logger.info(f"Invalidated {deleted} cache entries for user {user_id}")
                return deleted
            return 0
        except Exception as e:
            logger.warning(f"Cache INVALIDATE error: {e}")
            return 0
    
    async def close(self):
        """Close Redis connection."""
        if self._redis_client:
            await self._redis_client.close()
            logger.info("Redis connection closed")


# Global cache instance
_cache_instance: Optional[PredictionCache] = None


def get_cache() -> PredictionCache:
    """
    Get the global prediction cache instance.
    
    Returns:
        PredictionCache singleton
    """
    global _cache_instance
    if _cache_instance is None:
        _cache_instance = PredictionCache()
    return _cache_instance
