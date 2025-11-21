"""
Admin endpoints for privileged operations.

These endpoints require admin authentication via service key.
"""
import os
import logging
from datetime import datetime, timezone
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


class CleanupDataRequest(BaseModel):
    """Request body for data cleanup endpoint."""
    model_config = {"json_schema_extra": {
        "example": {
            "confirm": True
        }
    }}
    
    confirm: bool = Field(default=False, description="Confirmation to proceed with cleanup")


@router.post("/cleanup-data")
@limiter.limit("3/hour")  # Rate limit to prevent abuse
async def cleanup_synthetic_data(
    request: Request,
    cleanup_request: CleanupDataRequest,
    supabase: AsyncClient = Depends(get_supabase_client),
    authorization: Optional[str] = Header(None)
):
    """
    Clean up synthetic patient data from the database.
    
    This admin-only endpoint removes synthetic users and their associated check-ins.
    Synthetic users are identified by their email domain (@example.com).
    
    **Authentication**: Requires service key in Authorization header
    
    **Rate Limit**: 3 requests per hour per IP
    
    Args:
        cleanup_request: Cleanup confirmation
        supabase: Supabase client (injected)
        authorization: Authorization header with service key
        
    Returns:
        JSON with cleanup statistics including:
        - Number of profiles deleted
        - Number of check-ins deleted
        - Cleanup timestamp
        
    Raises:
        HTTPException: 401 if unauthorized, 400 if not confirmed, 500 for errors
        
    Example:
        ```bash
        curl -X POST https://api.example.com/api/admin/cleanup-data \\
          -H "Authorization: Bearer <your-service-key>" \\
          -H "Content-Type: application/json" \\
          -d '{"confirm": true}'
        ```
    """
    # Verify admin authorization
    verify_admin_authorization(authorization)
    
    # Require explicit confirmation
    if not cleanup_request.confirm:
        raise HTTPException(
            status_code=400,
            detail="Cleanup requires explicit confirmation. Set 'confirm': true in the request."
        )
    
    logger.info("Admin data cleanup request received")
    
    try:
        # First, get all synthetic user profiles (identified by @example.com email)
        profiles_response = await supabase.table('profiles').select('id, email').execute()
        
        if not profiles_response.data:
            logger.info("No profiles found in database")
            return {
                "status": "success",
                "message": "No data to cleanup",
                "statistics": {
                    "profiles_deleted": 0,
                    "checkins_deleted": 0,
                    "cleaned_at": datetime.now(timezone.utc).isoformat()
                }
            }
        
        # Filter synthetic users (those with @example.com emails or typical faker domains)
        synthetic_domains = ['@example.com', '@example.org', '@example.net']
        synthetic_user_ids = [
            profile['id'] for profile in profiles_response.data
            if profile.get('email') and any(domain in profile['email'] for domain in synthetic_domains)
        ]
        
        if not synthetic_user_ids:
            logger.info("No synthetic users found to cleanup")
            return {
                "status": "success",
                "message": "No synthetic users found",
                "statistics": {
                    "profiles_deleted": 0,
                    "checkins_deleted": 0,
                    "cleaned_at": datetime.now(timezone.utc).isoformat()
                }
            }
        
        logger.info(f"Found {len(synthetic_user_ids)} synthetic users to cleanup")
        
        # Delete check-ins first (child records)
        checkins_deleted = 0
        for user_id in synthetic_user_ids:
            checkins_response = await supabase.table('check_ins').delete().eq('user_id', user_id).execute()
            if checkins_response.data:
                checkins_deleted += len(checkins_response.data)
        
        logger.info(f"Deleted {checkins_deleted} check-ins")
        
        # Then delete profiles (parent records)
        profiles_deleted = 0
        for user_id in synthetic_user_ids:
            profile_response = await supabase.table('profiles').delete().eq('id', user_id).execute()
            if profile_response.data:
                profiles_deleted += len(profile_response.data)
        
        logger.info(f"Deleted {profiles_deleted} profiles")
        
        return {
            "status": "success",
            "message": f"Cleaned up {profiles_deleted} synthetic users and {checkins_deleted} check-ins",
            "statistics": {
                "profiles_deleted": profiles_deleted,
                "checkins_deleted": checkins_deleted,
                "cleaned_at": datetime.now(timezone.utc).isoformat()
            }
        }
        
    except APIError as e:
        logger.exception(f"Database error during cleanup: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Database error: {str(e)}"
        )
    except Exception as e:
        logger.exception(f"Error cleaning up data: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error cleaning up synthetic data: {str(e)}"
        )
