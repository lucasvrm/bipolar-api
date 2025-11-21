"""
Rate limiting configuration for the Bipolar AI Engine API.

This module provides rate limiting to prevent API abuse and ensure fair usage.
Rate limits are configurable via environment variables.
"""
import os
import logging
from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from fastapi import Request
from fastapi.responses import JSONResponse

logger = logging.getLogger("bipolar-api.rate_limiter")

# Configure rate limits from environment variables with sensible defaults
# Format: "number/period" where period can be: second, minute, hour, day
# Examples: "10/minute", "100/hour", "1000/day"
DEFAULT_RATE_LIMIT = os.getenv("RATE_LIMIT_DEFAULT", "60/minute")
PREDICTIONS_RATE_LIMIT = os.getenv("RATE_LIMIT_PREDICTIONS", "10/minute")
DATA_ACCESS_RATE_LIMIT = os.getenv("RATE_LIMIT_DATA_ACCESS", "30/minute")

logger.info(f"Rate limiting configured - Default: {DEFAULT_RATE_LIMIT}, "
            f"Predictions: {PREDICTIONS_RATE_LIMIT}, Data: {DATA_ACCESS_RATE_LIMIT}")


def get_user_id_from_request(request: Request) -> str:
    """
    Extract user identifier from request for rate limiting.
    
    Uses a combination of:
    1. User ID from path parameters (if available)
    2. Client IP address (fallback)
    
    This ensures rate limiting per user rather than globally.
    
    Args:
        request: FastAPI request object
        
    Returns:
        Identifier string for rate limiting
    """
    # Try to extract user_id from path
    path_parts = request.url.path.split('/')
    for part in path_parts:
        # Look for UUID-like patterns (36 chars with 4 hyphens)
        if len(part) == 36 and part.count('-') == 4:
            return f"user:{part}"
    
    # Fallback to IP address
    return get_remote_address(request)


# Initialize rate limiter
limiter = Limiter(
    key_func=get_user_id_from_request,
    default_limits=[DEFAULT_RATE_LIMIT],
    storage_uri=os.getenv("RATE_LIMIT_STORAGE_URI", "memory://"),
    # Use Redis if available, otherwise in-memory storage
    # Redis URI format: redis://host:port/db or rediss:// for SSL
)


def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    """
    Custom handler for rate limit exceeded responses.
    
    Returns a JSON response with clear error message and retry information.
    
    Args:
        request: FastAPI request object
        exc: RateLimitExceeded exception
        
    Returns:
        JSONResponse with 429 status code
    """
    logger.warning(
        f"Rate limit exceeded for {get_user_id_from_request(request)} "
        f"on path {request.url.path}"
    )
    
    return JSONResponse(
        status_code=429,
        content={
            "error": "rate_limit_exceeded",
            "message": "Too many requests. Please slow down and try again later.",
            "detail": str(exc.detail) if hasattr(exc, 'detail') else "Rate limit exceeded",
            "retry_after": getattr(exc, 'retry_after', 60)  # Default 60 seconds
        },
        headers={
            "Retry-After": str(getattr(exc, 'retry_after', 60))
        }
    )
