# api/utils.py
"""
Utility functions for the API.
"""
import uuid
import hashlib
import logging
from fastapi import HTTPException
from postgrest.exceptions import APIError

logger = logging.getLogger("bipolar-api.utils")

# PostgREST error codes
POSTGREST_UUID_SYNTAX_ERROR = '22P02'  # invalid_text_representation


def hash_user_id_for_logging(user_id: str) -> str:
    """
    Hash a user ID for privacy-preserving logging.
    
    Creates a short hash of the user ID that can be used in logs to track
    requests without exposing the actual user ID.
    
    Args:
        user_id: The user ID to hash
        
    Returns:
        First 8 characters of SHA-256 hash
    """
    return hashlib.sha256(user_id.encode()).hexdigest()[:8]


def validate_uuid_or_400(value: str, param_name: str = "id") -> str:
    """
    Validates that a string is a valid UUID format.
    
    Args:
        value: The string value to validate
        param_name: Name of the parameter for error message (default: "id")
        
    Returns:
        The original value if valid
        
    Raises:
        HTTPException: 400 Bad Request if the value is not a valid UUID
    """
    try:
        uuid.UUID(value)
        return value
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid UUID format for {param_name}: {value}"
        )


def handle_postgrest_error(e: APIError, user_id: str) -> None:
    """
    Handles PostgREST API errors and raises appropriate HTTPExceptions.
    
    Specifically maps PostgREST syntax errors (code 22P02, invalid UUID in DB query)
    to 400 Bad Request. Re-raises other APIErrors to be handled by caller.
    
    Args:
        e: The APIError from PostgREST
        user_id: The user_id that caused the error (for error message)
        
    Raises:
        HTTPException: 400 Bad Request if the error is a UUID syntax error (22P02)
        APIError: Re-raises the original error for other cases
    """
    # Handle PostgREST syntax errors (invalid UUID in database query)
    if hasattr(e, 'code') and e.code == POSTGREST_UUID_SYNTAX_ERROR:
        logger.warning(f"PostgREST UUID syntax error for user_id={user_id}: {e}")
        raise HTTPException(
            status_code=400,
            detail=f"Invalid UUID format in database query: {user_id}"
        )
    # Re-raise other APIErrors to be handled by caller
    logger.exception(f"PostgREST APIError for user_id={user_id}: {e}")
    raise
