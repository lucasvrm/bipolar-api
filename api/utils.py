# api/utils.py
"""
Utility functions for the API.
"""
import uuid
from fastapi import HTTPException


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
    except (ValueError, AttributeError):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid UUID format for {param_name}: {value}"
        )
