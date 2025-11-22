# api/utils.py
"""
Utility functions for the API.
"""
import uuid
import hashlib
import logging
from typing import Union
from fastapi import HTTPException
from postgrest.exceptions import APIError
from pydantic import ValidationError

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


def handle_postgrest_error(e: Union[APIError, Exception], user_id: str) -> None:
    """
    Handles PostgREST API errors and raises appropriate HTTPExceptions.
    
    Specifically maps PostgREST syntax errors (code 22P02, invalid UUID in DB query)
    to 400 Bad Request.
    Maps 401/403 errors to appropriate HTTP exceptions.
    Converts other errors to 500.

    Args:
        e: The exception (APIError or other)
        user_id: The user_id that caused the error (for error message)
        
    Raises:
        HTTPException: 400, 401, 403, or 500 depending on the error
    """
    error_msg = str(e)
    error_code = None

    # Try to extract code from APIError
    if isinstance(e, APIError):
        if hasattr(e, 'code'):
            error_code = e.code
        elif hasattr(e, 'message'):
            # Some versions might put code in message dict? Unlikely but possible
            pass

    # Handle PostgREST syntax errors (invalid UUID in database query)
    if error_code == POSTGREST_UUID_SYNTAX_ERROR:
        logger.warning(f"PostgREST UUID syntax error for user_id={user_id}: {e}")
        raise HTTPException(
            status_code=400,
            detail=f"Invalid UUID format in database query: {user_id}"
        )

    # Handle Authentication/Authorization errors
    # Note: PostgREST usually returns 401/403 as HTTP status, but library wraps it.
    # We check if the error code matches HTTP status codes which sometimes happens
    # when the library parses the error response.
    if error_code == '401' or '401' in error_msg:
        logger.error(f"PostgREST Auth Error (401) for user_id={user_id}: {e}")
        raise HTTPException(
            status_code=401,
            detail="Unauthorized: Database access denied. Check API configuration."
        )

    if error_code == '403' or '403' in error_msg:
        logger.error(f"PostgREST Permission Error (403) for user_id={user_id}: {e}")
        raise HTTPException(
            status_code=403,
            detail="Forbidden: Insufficient permissions for this operation."
        )

    # Check for Pydantic Validation Errors (often wrapping APIError parsing failures)
    if isinstance(e, ValidationError) or "validation error" in error_msg.lower():
         logger.error(f"Validation Error processing DB response for user_id={user_id}: {e}")
         raise HTTPException(
            status_code=500,
            detail="Internal Server Error: Failed to process database response."
        )

    # Log and raise generic 500 for other errors
    logger.exception(f"PostgREST APIError for user_id={user_id}: {e}")

    # Extract details if possible for the 500 message, but keep it safe
    detail = "Database error"
    if hasattr(e, 'details') and e.details:
        detail = f"Database error: {str(e.details)}"
    elif hasattr(e, 'message') and e.message:
        detail = f"Database error: {e.message}"

    raise HTTPException(status_code=500, detail=detail)
