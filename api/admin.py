"""
Admin endpoints for privileged operations.

These endpoints require admin authentication via JWT token with admin role.
"""
import logging
from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Header, Request
from pydantic import BaseModel, Field
from supabase import AsyncClient
from postgrest.exceptions import APIError
from postgrest.types import CountMethod

from api.dependencies import get_supabase_client, verify_admin_authorization
from api.rate_limiter import limiter
from data_generator import generate_and_populate_data

logger = logging.getLogger("bipolar-api.admin")

router = APIRouter(prefix="/api/admin", tags=["Admin"])


class GenerateDataRequest(BaseModel):
    """Request body for data generation endpoint."""
    model_config = {"json_schema_extra": {
        "example": {
            "patients_count": 5,
            "therapists_count": 2,
            "checkins_per_user": 30,
            "mood_pattern": "stable",
            "clear_db": False
        }
    }}

    # New parametrized approach
    patients_count: Optional[int] = Field(
        default=2, 
        ge=0, 
        le=100, 
        description="Number of patient profiles to generate (0-100). Patients will have check-ins generated."
    )
    therapists_count: Optional[int] = Field(
        default=1, 
        ge=0, 
        le=50, 
        description="Number of therapist profiles to generate (0-50). Therapists won't have check-ins."
    )
    checkins_per_user: int = Field(
        default=30, 
        ge=1, 
        le=365, 
        description="Check-ins per patient (1-365). Only applies to patients."
    )
    mood_pattern: str = Field(
        default="stable",
        description="Mood pattern: 'stable' (mostly euthymic), 'cycling' (regular cycles), or 'random'"
    )
    clear_db: bool = Field(
        default=False,
        description="If true, clears all synthetic data before generating new data"
    )
    
    # Legacy parameter for backward compatibility
    num_users: Optional[int] = Field(
        default=None,
        ge=1,
        le=100,
        description="DEPRECATED: Use patients_count and therapists_count instead. If provided, creates all users as patients."
    )


@router.post("/generate-data")
@limiter.limit("5/hour")  # Rate limit to prevent abuse
async def generate_synthetic_data(
    request: Request,
    data_request: GenerateDataRequest,
    supabase: AsyncClient = Depends(get_supabase_client),
    is_admin: bool = Depends(verify_admin_authorization)
):
    """
    Generate and insert synthetic patient and therapist data into the database.

    This admin-only endpoint creates realistic synthetic check-in data for testing
    and development purposes. It allows controlled generation of specific numbers of
    patients and therapists, with realistic check-in histories for patients.

    **Authentication**: Requires JWT token with admin role in Authorization header

    **Rate Limit**: 5 requests per hour per IP

    Args:
        data_request: Configuration for data generation with role-specific counts
        supabase: Supabase client (injected)
        is_admin: Admin authorization check (injected)

    Returns:
        JSON with generation statistics including:
        - Number of patients created
        - Number of therapists created
        - User IDs
        - Total check-ins inserted
        - Generation timestamp

    Raises:
        HTTPException: 401 if unauthorized, 403 if not admin, 400 for invalid parameters, 500 for errors

    Example:
        ```bash
        curl -X POST https://api.example.com/api/admin/generate-data \\
          -H "Authorization: Bearer <your-jwt-token>" \\
          -H "Content-Type: application/json" \\
          -d '{"patients_count": 5, "therapists_count": 2, "checkins_per_user": 30, "mood_pattern": "stable", "clear_db": false}'
        ```
    """
    # Admin check is done by dependency - no need to verify again

    # Validate mood_pattern
    valid_patterns = ['stable', 'cycling', 'random']
    if data_request.mood_pattern not in valid_patterns:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid mood_pattern. Must be one of: {', '.join(valid_patterns)}"
        )
    
    # Handle legacy num_users parameter
    patients_count = data_request.patients_count
    therapists_count = data_request.therapists_count
    
    if data_request.num_users is not None:
        # Legacy mode: num_users creates all patients
        logger.info(f"Using legacy num_users parameter ({data_request.num_users}), creating all as patients")
        patients_count = data_request.num_users
        therapists_count = 0
    
    # Validate at least one user type is requested
    if patients_count == 0 and therapists_count == 0:
        raise HTTPException(
            status_code=400,
            detail="Must specify at least one patient or therapist to generate"
        )

    logger.info(
        f"Admin data generation request: {patients_count} patients, "
        f"{therapists_count} therapists, {data_request.checkins_per_user} check-ins per patient, "
        f"pattern={data_request.mood_pattern}, clear_db={data_request.clear_db}"
    )

    try:
        # Clear database if requested
        if data_request.clear_db:
            logger.info("Clearing synthetic data before generation...")
            
            # Synthetic domains used by Faker with pt_BR locale
            SYNTHETIC_DOMAINS = ['@example.com', '@example.org', '@example.net']
            
            # Get all synthetic user profiles (identified by example domains)
            profiles_response = await supabase.table('profiles').select('id, email').execute()
            
            if profiles_response.data:
                synthetic_user_ids = [
                    profile['id'] for profile in profiles_response.data
                    if profile.get('email') and any(domain in profile['email'] for domain in SYNTHETIC_DOMAINS)
                ]
                
                if synthetic_user_ids:
                    logger.info(f"Found {len(synthetic_user_ids)} synthetic users to clear")
                    
                    # Bulk delete check-ins (child records) using in_ clause
                    await supabase.table('check_ins').delete().in_('user_id', synthetic_user_ids).execute()
                    
                    # Bulk delete profiles (parent records) using in_ clause
                    await supabase.table('profiles').delete().in_('id', synthetic_user_ids).execute()
                    
                    logger.info(f"Cleared {len(synthetic_user_ids)} synthetic users and their check-ins")
        
        # Generate and populate data with new parameters
        result = await generate_and_populate_data(
            supabase=supabase,
            checkins_per_user=data_request.checkins_per_user,
            mood_pattern=data_request.mood_pattern,
            patients_count=patients_count,
            therapists_count=therapists_count
        )

        logger.info(
            f"Data generation completed: {result['statistics']['patients_created']} patients, "
            f"{result['statistics']['therapists_created']} therapists, "
            f"{result['statistics']['total_checkins']} check-ins inserted"
        )

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


@router.get("/stats")
async def get_admin_stats(
    supabase: AsyncClient = Depends(get_supabase_client),
    is_admin: bool = Depends(verify_admin_authorization)
):
    """
    Get statistics about users and check-ins in the database.

    This admin-only endpoint provides counts of total users and check-ins
    using the Supabase service role to bypass RLS policies.

    **Authentication**: Requires JWT token with admin role in Authorization header

    Returns:
        JSON with statistics:
        - total_users: Total number of user profiles
        - total_checkins: Total number of check-ins

    Raises:
        HTTPException: 401 if unauthorized, 403 if not admin, 500 for errors

    Example:
        ```bash
        curl -X GET https://api.example.com/api/admin/stats \\
          -H "Authorization: Bearer <your-jwt-token>"
        ```
    """
    # Admin check is done by dependency

    logger.info("Admin stats request received")

    try:
        # Count total users using exact count with head=True (only returns count, no data)
        profiles_response = await supabase.table('profiles').select('*', count=CountMethod.exact, head=True).execute()
        total_users = profiles_response.count if profiles_response.count is not None else 0

        # Count total check-ins using exact count with head=True
        checkins_response = await supabase.table('check_ins').select('*', count=CountMethod.exact, head=True).execute()
        total_checkins = checkins_response.count if checkins_response.count is not None else 0

        logger.info(f"Stats retrieved: {total_users} users, {total_checkins} check-ins")

        return {
            "total_users": total_users,
            "total_checkins": total_checkins
        }

    except APIError as e:
        logger.exception(f"Database error during stats retrieval: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Database error: {str(e)}"
        )
    except Exception as e:
        logger.exception(f"Error retrieving stats: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error retrieving statistics: {str(e)}"
        )


@router.get("/users")
async def get_admin_users(
    supabase: AsyncClient = Depends(get_supabase_client),
    is_admin: bool = Depends(verify_admin_authorization)
):
    """
    List the most recently created users in the database.

    This admin-only endpoint provides a list of the last 50 users with their
    basic information, using the Supabase service role to bypass RLS policies.

    **Authentication**: Requires JWT token with admin role in Authorization header

    Returns:
        List of user objects with:
        - id: User UUID
        - email: User email

    Raises:
        HTTPException: 401 if unauthorized, 403 if not admin, 500 for errors

    Example:
        ```bash
        curl -X GET https://api.example.com/api/admin/users \\
          -H "Authorization: Bearer <your-jwt-token>"
        ```
    """
    # Admin check is done by dependency

    logger.info("Admin users list request received")

    try:
        # Get last 50 users ordered by created_at descending
        response = await supabase.table('profiles').select('id, email').order('created_at', desc=True).limit(50).execute()

        users = response.data if response.data else []

        logger.info(f"Retrieved {len(users)} users")

        return users

    except APIError as e:
        logger.exception(f"Database error during users retrieval: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Database error: {str(e)}"
        )
    except Exception as e:
        logger.exception(f"Error retrieving users: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error retrieving users: {str(e)}"
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
    is_admin: bool = Depends(verify_admin_authorization)
):
    """
    Clean up synthetic patient data from the database.

    This admin-only endpoint removes synthetic users and their associated check-ins.
    Synthetic users are identified by their email domain (@example.com).

    **Authentication**: Requires JWT token with admin role in Authorization header

    **Rate Limit**: 3 requests per hour per IP

    Args:
        cleanup_request: Cleanup confirmation
        supabase: Supabase client (injected)
        is_admin: Admin authorization check (injected)

    Returns:
        JSON with cleanup statistics including:
        - Number of profiles deleted
        - Number of check-ins deleted
        - Cleanup timestamp

    Raises:
        HTTPException: 401 if unauthorized, 403 if not admin, 400 if not confirmed, 500 for errors

    Example:
        ```bash
        curl -X POST https://api.example.com/api/admin/cleanup-data \\
          -H "Authorization: Bearer <your-jwt-token>" \\
          -H "Content-Type: application/json" \\
          -d '{"confirm": true}'
        ```
    """
    # Admin check is done by dependency

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
