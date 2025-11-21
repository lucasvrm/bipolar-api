# api/middleware.py
"""
Custom middleware for observability and request tracking.
"""
import time
import uuid
import hashlib
import logging
from typing import Callable
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

logger = logging.getLogger("bipolar-api.middleware")


class ObservabilityMiddleware(BaseHTTPMiddleware):
    """
    Middleware to add observability features:
    - Request ID generation and tracking
    - Request timing
    - User ID hashing for privacy-preserving logging
    - Request/response logging
    """
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Generate unique request ID
        request_id = str(uuid.uuid4())
        
        # Extract user_id from path if present (for privacy-preserving logging)
        user_id_hash = None
        path_parts = request.url.path.split('/')
        
        # Look for UUID-like patterns in the path
        for part in path_parts:
            if len(part) == 36 and part.count('-') == 4:
                # Likely a UUID, hash it for logging
                user_id_hash = hashlib.sha256(part.encode()).hexdigest()[:8]
                break
        
        # Start timer
        start_time = time.time()
        
        # Add request ID to request state for use in endpoints
        request.state.request_id = request_id
        request.state.user_id_hash = user_id_hash
        
        # Log request start
        log_data = {
            "request_id": request_id,
            "method": request.method,
            "path": request.url.path,
            "user_hash": user_id_hash
        }
        logger.info(f"Request started: {log_data}")
        
        # Process request
        try:
            response = await call_next(request)
            
            # Calculate duration
            duration_ms = (time.time() - start_time) * 1000
            
            # Add headers
            response.headers["X-Request-ID"] = request_id
            response.headers["X-Response-Time"] = f"{duration_ms:.2f}ms"
            
            # Log response
            logger.info(
                f"Request completed: request_id={request_id}, "
                f"status={response.status_code}, "
                f"duration={duration_ms:.2f}ms, "
                f"user_hash={user_id_hash or 'none'}"
            )
            
            # Log metrics (could be sent to monitoring system)
            if hasattr(request.state, 'metrics'):
                metrics = request.state.metrics
                logger.info(f"Request metrics: request_id={request_id}, {metrics}")
            
            return response
            
        except Exception as e:
            # Log error
            duration_ms = (time.time() - start_time) * 1000
            logger.error(
                f"Request failed: request_id={request_id}, "
                f"error={str(e)}, "
                f"duration={duration_ms:.2f}ms, "
                f"user_hash={user_id_hash or 'none'}",
                exc_info=True
            )
            raise


def add_request_metrics(request: Request, **metrics):
    """
    Helper function to add metrics to request state.
    Can be called from endpoints to track custom metrics.
    
    Example:
        add_request_metrics(request, cache_hit=True, model_version="v1")
    """
    if not hasattr(request.state, 'metrics'):
        request.state.metrics = {}
    
    request.state.metrics.update(metrics)


def get_request_id(request: Request) -> str:
    """
    Get the request ID from request state.
    
    Args:
        request: FastAPI Request object
        
    Returns:
        Request ID string, or "unknown" if not available
    """
    return getattr(request.state, 'request_id', 'unknown')


def get_user_hash(request: Request) -> str:
    """
    Get the hashed user ID from request state.
    
    Args:
        request: FastAPI Request object
        
    Returns:
        Hashed user ID string, or "none" if not available
    """
    return getattr(request.state, 'user_id_hash', 'none')
