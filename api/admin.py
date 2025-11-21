# api/admin.py
"""
Admin endpoints for privileged operations.

These endpoints require admin authentication via service key.
"""
import os
import logging
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Header, Request
from pydantic import BaseModel, Field
from supabase import AsyncClient
from postgrest.exceptions import APIError

from api.dependencies import get_supabase_client
from api.rate_limiter import limiter
from data_generator import generate_and_populate_data

logger = logging.getLogger("bipolar-api.admin")

router = APIRouter(prefix="/api/admin", tags=["Admin"])


def verify_admin_authorization(authorization: Optional[str] = Header(None)) -> bool:
    """
    Verify that the request has admin authorization via service key.
    
    Uses the same pattern as privacy.py for admin access.
    
    Args:
        authorization: Authorization header
        
    Returns:
        True if authorized as admin
        
    Raises:
        HTTPException: 401 if unauthorized
    """
    if not authorization:
        logger.warning("No authorization header provided for admin endpoint")
        raise HTTPException(
            status_code=401,
            detail="Admin authorization required. Provide a valid service key."
        )
    
    # Get service key from environment
    service_key = os.getenv("SUPABASE_SERVICE_KEY")
    
    # Check if it's a service key (admin access)
    if authorization.startswith("Bearer "):
        token = authorization[7:]
        if token == service_key:
            logger.info("Admin access authorized")
            return True
    
    logger.error("Invalid admin authorization token")
    raise HTTPException(
        status_code=401,
        detail="Invalid authorization token. Admin access requires service key."
    )


class GenerateDataRequest(BaseModel):
    """Request body for data generation endpoint."""
    model_config = {"json_schema_extra": {
        "example": {
            "num_users": 10,
            "checkins_per_user": 30,
            "mood_pattern": "stable"
        }
    }}
    
    num_users: int = Field(default=5, ge=1, le=100, description="Number of users to generate (1-100)")
    checkins_per_user: int = Field(default=30, ge=1, le=365, description="Check-ins per user (1-365)")
    mood_pattern: str = Field(
        default="stable",
        description="Mood pattern: 'stable' (mostly euthymic), 'cycling' (regular cycles), or 'random'"
    )


@router.post("/generate-data")
@limiter.limit("5/hour")  # Rate limit to prevent abuse
async def generate_synthetic_data(
    request: Request,
    data_request: GenerateDataRequest,
    supabase: AsyncClient = Depends(get_supabase_client),
    authorization: Optional[str] = Header(None)
):
    """
    Generate and insert synthetic patient data into the database.
    
    This admin-only endpoint creates realistic synthetic check-in data for testing
    and development purposes. It generates multiple users with complete check-in
    histories that include realistic correlations between mood states and other
    clinical markers.
    
    **Authentication**: Requires service key in Authorization header
    
    **Rate Limit**: 5 requests per hour per IP
    
    Args:
        data_request: Configuration for data generation
        supabase: Supabase client (injected)
        authorization: Authorization header with service key
        
    Returns:
        JSON with generation statistics including:
        - Number of users created
        - User IDs
        - Total check-ins inserted
        - Generation timestamp
        
    Raises:
        HTTPException: 401 if unauthorized, 400 for invalid parameters, 500 for errors
        
    Example:
        ```bash
        curl -X POST https://api.example.com/api/admin/generate-data \\
          -H "Authorization: Bearer <your-service-key>" \\
          -H "Content-Type: application/json" \\
          -d '{"num_users": 10, "checkins_per_user": 30, "mood_pattern": "stable"}'
        ```
    """
    # Verify admin authorization
    verify_admin_authorization(authorization)
    
    # Validate mood_pattern
    valid_patterns = ['stable', 'cycling', 'random']
    if data_request.mood_pattern not in valid_patterns:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid mood_pattern. Must be one of: {', '.join(valid_patterns)}"
        )
    
    logger.info(
        f"Admin data generation request: {data_request.num_users} users, "
        f"{data_request.checkins_per_user} check-ins per user, "
        f"pattern={data_request.mood_pattern}"
    )
    
    try:
        # Generate and populate data
        result = await generate_and_populate_data(
            supabase=supabase,
            num_users=data_request.num_users,
            checkins_per_user=data_request.checkins_per_user,
            mood_pattern=data_request.mood_pattern
        )
        
        logger.info(f"Data generation completed: {result['statistics']['total_checkins']} check-ins inserted")
        
        return result
        
    except APIError as e:
        logger.exception(f"Database error during data generation: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Database error: {str(e)}"
        )
    except Exception as e:
        logger.exception(f"Error generating data: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error generating synthetic data: {str(e)}"
        )
