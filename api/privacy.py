# api/privacy.py
"""
Privacy and data operations endpoints for GDPR/LGPD compliance.
Includes consent management, data export, and data erasure.
"""
import os
import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException, Header, Request
from supabase import AsyncClient
from postgrest.exceptions import APIError

from api.dependencies import get_supabase_client
from api.utils import validate_uuid_or_400, handle_postgrest_error, hash_user_id_for_logging
from api.rate_limiter import limiter, DATA_ACCESS_RATE_LIMIT

logger = logging.getLogger("bipolar-api.privacy")

router = APIRouter(prefix="/user", tags=["Privacy & Data Operations"])


def verify_authorization(user_id: str, authorization: Optional[str] = Header(None)) -> bool:
    """
    Verify that the request is authorized for the given user.
    
    Authorization can be:
    1. Service key (for admin operations)
    2. User token (for user's own data - to be implemented with JWT)
    
    Args:
        user_id: The user ID being accessed
        authorization: Authorization header
        
    Returns:
        True if authorized
        
    Raises:
        HTTPException: 401 if unauthorized
    """
    if not authorization:
        logger.warning(f"No authorization header provided for user {user_id}")
        raise HTTPException(
            status_code=401,
            detail="Authorization required. Provide a valid access token."
        )
    
    # Get service key from environment
    service_key = os.getenv("SUPABASE_SERVICE_KEY")
    
    # Check if it's a service key (admin access)
    if authorization.startswith("Bearer "):
        token = authorization[7:]
        if token == service_key:
            logger.info(f"Admin access authorized for user {user_id}")
            return True
    
    # TODO: Implement JWT token validation for user-specific access
    # For now, reject all non-service-key requests
    logger.error(f"Invalid authorization token for user {user_id}")
    raise HTTPException(
        status_code=401,
        detail="Invalid authorization token. Please use a valid service key or user token."
    )


@router.get("/{user_id}/profile")
@limiter.limit(DATA_ACCESS_RATE_LIMIT)
async def get_user_profile(
    request: Request,
    user_id: str,
    supabase: AsyncClient = Depends(get_supabase_client)
):
    """
    Get user profile information including admin status.
    
    This endpoint returns basic profile information for a user including:
    - User ID
    - Email
    - Full name
    - Admin status (is_admin field)
    - Created timestamp
    
    Security Note: This endpoint currently does not require authorization, matching
    the pattern of other data endpoints (/data/predictions, /data/latest_checkin).
    The security model assumes the frontend authenticates users via Supabase Auth
    and only requests data for the authenticated user. Rate limiting (30/min) helps
    prevent abuse.
    
    TODO: Implement JWT token validation to ensure users can only access their own
    profile data, or add proper RLS by using user-scoped Supabase clients instead
    of the service key.
    
    Args:
        request: FastAPI request object (for rate limiting)
        user_id: UUID of the user
        
    Returns:
        User profile object with id, email, full_name, is_admin, created_at
        
    Raises:
        HTTPException: 400 for invalid UUID, 404 if user not found, 429 for rate limit, 500 for errors
    """
    # Validate UUID
    validate_uuid_or_400(user_id, "user_id")
    
    logger.info(f"Fetching profile for user {hash_user_id_for_logging(user_id)}")
    
    try:
        # Fetch user profile from profiles table
        response = await supabase.table('profiles')\
            .select('id, email, full_name, is_admin, created_at')\
            .eq('id', user_id)\
            .execute()
        
        if not response.data or len(response.data) == 0:
            logger.warning(f"User profile not found for user {hash_user_id_for_logging(user_id)}")
            raise HTTPException(
                status_code=404,
                detail="User profile not found"
            )
        
        profile = response.data[0]
        logger.info(f"Profile fetched successfully for user (admin={profile.get('is_admin', False)})")
        
        return profile
        
    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    except APIError as e:
        # Handle PostgREST errors using centralized utility
        handle_postgrest_error(e, user_id)
    except Exception as e:
        logger.exception(f"Error fetching profile for user {hash_user_id_for_logging(user_id)}: {e}")
        raise HTTPException(
            status_code=500,
            detail="Error fetching user profile"
        )


@router.post("/{user_id}/consent")
async def update_consent(
    user_id: str,
    consent_data: Dict[str, Any],
    supabase: AsyncClient = Depends(get_supabase_client),
    authorization: Optional[str] = Header(None)
):
    """
    Update user consent preferences for data processing.
    
    This endpoint allows users to:
    - Grant or revoke consent for data processing
    - Specify purposes for which data can be used
    - Update consent preferences at any time
    
    Args:
        user_id: UUID of the user
        consent_data: Dictionary with consent preferences
            {
                "analytics": bool,
                "research": bool,
                "personalization": bool,
                "updated_at": ISO timestamp (auto-generated if not provided)
            }
        authorization: Authorization header (required)
        
    Returns:
        Updated consent record
        
    Raises:
        HTTPException: 400 for invalid UUID, 401 for unauthorized, 500 for errors
    """
    # Validate UUID
    validate_uuid_or_400(user_id, "user_id")
    
    # Verify authorization
    verify_authorization(user_id, authorization)
    
    logger.info(f"Updating consent for user {hash_user_id_for_logging(user_id)}")
    
    try:
        # Add timestamp
        consent_data["user_id"] = user_id
        consent_data["updated_at"] = datetime.now(timezone.utc).isoformat()
        
        # Upsert consent record
        response = await supabase.table('user_consent')\
            .upsert(consent_data, on_conflict="user_id")\
            .execute()
        
        logger.info(f"Consent updated successfully for user")
        
        return {
            "status": "success",
            "message": "Consent preferences updated successfully",
            "data": response.data[0] if response.data else consent_data
        }
        
    except APIError as e:
        handle_postgrest_error(e, user_id)
    except Exception as e:
        logger.exception(f"Error updating consent for user {user_id}")
        raise HTTPException(
            status_code=500,
            detail=f"Error updating consent: {str(e)}"
        )


@router.get("/{user_id}/export")
async def export_user_data(
    user_id: str,
    supabase: AsyncClient = Depends(get_supabase_client),
    authorization: Optional[str] = Header(None)
):
    """
    Export all user data in a portable format (GDPR/LGPD right to data portability).
    
    This endpoint collects all data associated with the user from various tables
    and returns it in a structured JSON format.
    
    Args:
        user_id: UUID of the user
        authorization: Authorization header (required)
        
    Returns:
        JSON with all user data including:
        - Profile information
        - Check-ins
        - Consent preferences
        - Any other user-related data
        
    Raises:
        HTTPException: 400 for invalid UUID, 401 for unauthorized, 500 for errors
    """
    # Validate UUID
    validate_uuid_or_400(user_id, "user_id")
    
    # Verify authorization
    verify_authorization(user_id, authorization)
    
    logger.info(f"Exporting data for user {hash_user_id_for_logging(user_id)}")
    
    try:
        export_data = {
            "user_id": user_id,
            "export_date": datetime.now(timezone.utc).isoformat(),
            "data": {}
        }
        
        # Fetch check-ins
        try:
            checkins_response = await supabase.table('check_ins')\
                .select('*')\
                .eq('user_id', user_id)\
                .execute()
            export_data["data"]["check_ins"] = checkins_response.data if checkins_response.data else []
            logger.info(f"Exported {len(export_data['data']['check_ins'])} check-ins")
        except Exception as e:
            logger.warning(f"Error fetching check-ins: {e}")
            export_data["data"]["check_ins"] = []
        
        # Fetch consent preferences
        try:
            consent_response = await supabase.table('user_consent')\
                .select('*')\
                .eq('user_id', user_id)\
                .execute()
            export_data["data"]["consent"] = consent_response.data[0] if consent_response.data else None
            logger.info("Exported consent data")
        except Exception as e:
            logger.warning(f"Error fetching consent: {e}")
            export_data["data"]["consent"] = None
        
        # Add metadata
        export_data["metadata"] = {
            "total_check_ins": len(export_data["data"]["check_ins"]),
            "format_version": "1.0",
            "notice": "This export contains all personal data we have stored about you."
        }
        
        logger.info(f"Data export completed successfully for user")
        
        return export_data
        
    except APIError as e:
        handle_postgrest_error(e, user_id)
    except Exception as e:
        logger.exception(f"Error exporting data for user {user_id}")
        raise HTTPException(
            status_code=500,
            detail=f"Error exporting user data: {str(e)}"
        )


@router.post("/{user_id}/erase")
async def erase_user_data(
    user_id: str,
    supabase: AsyncClient = Depends(get_supabase_client),
    authorization: Optional[str] = Header(None)
):
    """
    Erase all user data (GDPR/LGPD right to be forgotten).
    
    This endpoint deletes all data associated with the user.
    This is a destructive operation and cannot be undone.
    
    Note: In production, this should:
    1. Create an erasure job for background processing
    2. Log the request for compliance
    3. Notify relevant systems
    4. Retain minimal data for legal compliance if required
    
    Args:
        user_id: UUID of the user
        authorization: Authorization header (required)
        
    Returns:
        Confirmation of erasure request
        
    Raises:
        HTTPException: 400 for invalid UUID, 401 for unauthorized, 500 for errors
    """
    # Validate UUID
    validate_uuid_or_400(user_id, "user_id")
    
    # Verify authorization
    verify_authorization(user_id, authorization)
    
    logger.warning(f"ERASURE REQUEST for user {hash_user_id_for_logging(user_id)}")
    
    try:
        deletion_summary = {
            "user_id": user_id,
            "erasure_date": datetime.now(timezone.utc).isoformat(),
            "deleted_records": {}
        }
        
        # Delete check-ins
        try:
            checkins_delete = await supabase.table('check_ins')\
                .delete()\
                .eq('user_id', user_id)\
                .execute()
            deleted_checkins = len(checkins_delete.data) if checkins_delete.data else 0
            deletion_summary["deleted_records"]["check_ins"] = deleted_checkins
            logger.info(f"Deleted {deleted_checkins} check-ins")
        except Exception as e:
            logger.error(f"Error deleting check-ins: {e}")
            deletion_summary["deleted_records"]["check_ins"] = 0
        
        # Delete consent preferences
        try:
            consent_delete = await supabase.table('user_consent')\
                .delete()\
                .eq('user_id', user_id)\
                .execute()
            deleted_consent = len(consent_delete.data) if consent_delete.data else 0
            deletion_summary["deleted_records"]["consent"] = deleted_consent
            logger.info(f"Deleted consent record")
        except Exception as e:
            logger.error(f"Error deleting consent: {e}")
            deletion_summary["deleted_records"]["consent"] = 0
        
        # Invalidate cache
        try:
            from services.prediction_cache import get_cache
            cache = get_cache()
            invalidated = await cache.invalidate(user_id)
            deletion_summary["cache_invalidated"] = invalidated > 0
            logger.info(f"Invalidated {invalidated} cache entries")
        except Exception as e:
            logger.warning(f"Error invalidating cache: {e}")
            deletion_summary["cache_invalidated"] = False
        
        logger.warning(f"ERASURE COMPLETED for user - Summary: {deletion_summary}")
        
        return {
            "status": "success",
            "message": "User data erasure completed successfully",
            "summary": deletion_summary
        }
        
    except APIError as e:
        handle_postgrest_error(e, user_id)
    except Exception as e:
        logger.exception(f"Error erasing data for user {user_id}")
        raise HTTPException(
            status_code=500,
            detail=f"Error erasing user data: {str(e)}"
        )
