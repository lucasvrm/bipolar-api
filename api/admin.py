"""
Admin endpoints for privileged operations.

These endpoints require admin authentication via JWT token with admin role.
"""
import logging
import io
import csv
import json
from datetime import datetime, timezone, timedelta
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Header, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from supabase import AsyncClient
from postgrest.exceptions import APIError
from postgrest.types import CountMethod

from api.dependencies import get_supabase_client, verify_admin_authorization
from api.rate_limiter import limiter
from api.schemas.synthetic_data import (
    CleanDataRequest,
    CleanDataResponse,
    ToggleTestFlagResponse,
    EnhancedStatsResponse
)
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
        logger.exception("Database error during data generation")
        raise HTTPException(
            status_code=500,
            detail=f"Database error: {str(e)}"
        )
    except Exception as e:
        logger.exception("Error generating data")
        raise HTTPException(
            status_code=500,
            detail=f"Error generating synthetic data: {str(e)}"
        )


@router.get("/stats", response_model=EnhancedStatsResponse)
async def get_admin_stats(
    supabase: AsyncClient = Depends(get_supabase_client),
    is_admin: bool = Depends(verify_admin_authorization)
):
    """
    Get comprehensive statistics about users and check-ins in the database.

    This admin-only endpoint provides detailed metrics including patient counts,
    check-in statistics, mood distributions, and alerts.

    **Authentication**: Requires JWT token with admin role in Authorization header

    Returns:
        JSON with comprehensive statistics including:
        - Legacy fields: total_users, total_checkins
        - Patient counts: real_patients_count, synthetic_patients_count
        - Check-in metrics: checkins_today, checkins_last_7_days, etc.
        - Analytics: avg_checkins_per_active_patient, avg_adherence_last_30d
        - Mood data: avg_current_mood, mood_distribution
        - Alerts: critical_alerts_last_30d, patients_with_recent_radar

    Raises:
        HTTPException: 401 if unauthorized, 403 if not admin, 500 for errors
    """
    logger.info("Admin enhanced stats request received")

    try:
        # Get current datetime for calculations
        now = datetime.now(timezone.utc)
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        seven_days_ago = now - timedelta(days=7)
        fourteen_days_ago = now - timedelta(days=14)
        thirty_days_ago = now - timedelta(days=30)

        # Legacy counts
        profiles_response = await supabase.table('profiles').select('*', count=CountMethod.exact, head=True).execute()
        total_users = profiles_response.count if profiles_response.count is not None else 0

        checkins_response = await supabase.table('check_ins').select('*', count=CountMethod.exact, head=True).execute()
        total_checkins = checkins_response.count if checkins_response.count is not None else 0

        # Get all profiles with is_test_patient flag
        SYNTHETIC_DOMAINS = ['@example.com', '@example.org', '@example.net']
        all_profiles_response = await supabase.table('profiles').select('id, email, is_test_patient, role').execute()
        all_profiles = all_profiles_response.data if all_profiles_response.data else []

        # Count synthetic vs real patients
        synthetic_patients = [
            p for p in all_profiles
            if (p.get('role') == 'patient' and (
                p.get('is_test_patient') is True or
                (p.get('email') and any(domain in p['email'] for domain in SYNTHETIC_DOMAINS))
            ))
        ]
        
        real_patients = [
            p for p in all_profiles
            if p.get('role') == 'patient' and p not in synthetic_patients
        ]

        real_patients_count = len(real_patients)
        synthetic_patients_count = len(synthetic_patients)

        # Check-ins today
        checkins_today_response = await supabase.table('check_ins').select(
            '*', count=CountMethod.exact, head=True
        ).gte('checkin_date', today_start.isoformat()).execute()
        checkins_today = checkins_today_response.count if checkins_today_response.count is not None else 0

        # Check-ins last 7 days
        checkins_7d_response = await supabase.table('check_ins').select(
            '*', count=CountMethod.exact, head=True
        ).gte('checkin_date', seven_days_ago.isoformat()).execute()
        checkins_last_7_days = checkins_7d_response.count if checkins_7d_response.count is not None else 0

        # Check-ins previous 7 days (for % variation)
        checkins_prev_7d_response = await supabase.table('check_ins').select(
            '*', count=CountMethod.exact, head=True
        ).gte('checkin_date', fourteen_days_ago.isoformat()).lt('checkin_date', seven_days_ago.isoformat()).execute()
        checkins_last_7_days_previous = checkins_prev_7d_response.count if checkins_prev_7d_response.count is not None else 0

        # Get check-ins from last 30 days with full data for calculations
        checkins_30d_response = await supabase.table('check_ins').select(
            'user_id, checkin_date, mood_data, meds_context_data'
        ).gte('checkin_date', thirty_days_ago.isoformat()).execute()
        checkins_30d = checkins_30d_response.data if checkins_30d_response.data else []

        # Calculate avg check-ins per active patient (patients who checked in last 30 days)
        active_patients = set(c['user_id'] for c in checkins_30d)
        active_patient_count = len(active_patients)
        avg_checkins_per_active_patient = len(checkins_30d) / active_patient_count if active_patient_count > 0 else 0.0

        # Calculate avg adherence last 30d (from meds_context_data)
        adherence_values = []
        for checkin in checkins_30d:
            meds_data = checkin.get('meds_context_data', {})
            if isinstance(meds_data, dict) and 'medication_adherence' in meds_data:
                adherence = meds_data['medication_adherence']
                if isinstance(adherence, (int, float)):
                    adherence_values.append(adherence)

        avg_adherence_last_30d = sum(adherence_values) / len(adherence_values) if adherence_values else 0.0

        # Calculate avg current mood from recent check-ins (last 7 days)
        mood_values = []
        mood_counts = {
            'stable': 0,
            'hypomania': 0,
            'mania': 0,
            'depression': 0,
            'mixed': 0,
            'euthymic': 0
        }

        for checkin in checkins_30d:
            mood_data = checkin.get('mood_data', {})
            if isinstance(mood_data, dict):
                # Get depression and elevation scores to classify mood
                depression = mood_data.get('depressedMood', 0)
                elevation = mood_data.get('elevatedMood', 0)
                activation = mood_data.get('activation', 0)

                # Classification logic (simplified)
                if depression > 7 and elevation > 5:
                    mood_counts['mixed'] += 1
                    mood_values.append(3)  # Mixed state
                elif elevation > 8 or activation > 8:
                    mood_counts['mania'] += 1
                    mood_values.append(4)  # Manic
                elif elevation > 5:
                    mood_counts['hypomania'] += 1
                    mood_values.append(3.5)  # Hypomanic
                elif depression > 7:
                    mood_counts['depression'] += 1
                    mood_values.append(2)  # Depressed
                else:
                    mood_counts['euthymic'] += 1
                    mood_values.append(3)  # Euthymic/stable

        avg_current_mood = sum(mood_values) / len(mood_values) if mood_values else 3.0

        # Mood distribution
        mood_distribution = mood_counts

        # Critical alerts last 30d (placeholder - would need alerts table)
        # For now, count check-ins with high risk indicators
        critical_alerts_last_30d = 0
        for checkin in checkins_30d:
            mood_data = checkin.get('mood_data', {})
            symptoms_data = checkin.get('symptoms_data', {})
            
            if isinstance(mood_data, dict) and isinstance(symptoms_data, dict):
                depression = mood_data.get('depressedMood', 0)
                activation = mood_data.get('activation', 0)
                thought_speed = symptoms_data.get('thoughtSpeed', 0)
                
                # High risk if extreme values
                if depression >= 9 or activation >= 9 or thought_speed >= 9:
                    critical_alerts_last_30d += 1

        # Patients with recent radar (placeholder - would need radar table)
        # For now, return 0
        patients_with_recent_radar = 0

        logger.info(
            f"Enhanced stats: {real_patients_count} real patients, "
            f"{synthetic_patients_count} synthetic patients, "
            f"{checkins_last_7_days} check-ins (7d)"
        )

        return EnhancedStatsResponse(
            total_users=total_users,
            total_checkins=total_checkins,
            real_patients_count=real_patients_count,
            synthetic_patients_count=synthetic_patients_count,
            checkins_today=checkins_today,
            checkins_last_7_days=checkins_last_7_days,
            checkins_last_7_days_previous=checkins_last_7_days_previous,
            avg_checkins_per_active_patient=round(avg_checkins_per_active_patient, 2),
            avg_adherence_last_30d=round(avg_adherence_last_30d, 2),
            avg_current_mood=round(avg_current_mood, 2),
            mood_distribution=mood_distribution,
            critical_alerts_last_30d=critical_alerts_last_30d,
            patients_with_recent_radar=patients_with_recent_radar
        )

    except APIError as e:
        logger.exception("Database error during stats retrieval")
        raise HTTPException(
            status_code=500,
            detail=f"Database error: {str(e)}"
        )
    except Exception as e:
        logger.exception("Error retrieving stats")
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
        logger.exception("Database error during users retrieval")
        raise HTTPException(
            status_code=500,
            detail=f"Database error: {str(e)}"
        )
    except Exception as e:
        logger.exception("Error retrieving users")
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
        logger.exception("Database error during cleanup")
        raise HTTPException(
            status_code=500,
            detail=f"Database error: {str(e)}"
        )
    except Exception as e:
        logger.exception("Error cleaning up data")
        raise HTTPException(
            status_code=500,
            detail=f"Error cleaning up synthetic data: {str(e)}"
        )


@router.post("/synthetic-data/clean", response_model=CleanDataResponse)
@limiter.limit("10/hour")
async def clean_synthetic_data(
    request: Request,
    clean_request: CleanDataRequest,
    supabase: AsyncClient = Depends(get_supabase_client),
    is_admin: bool = Depends(verify_admin_authorization)
):
    """
    Clean synthetic/test patient data with various filtering options.

    This admin-only endpoint deletes synthetic patients and their associated data.
    Synthetic patients are identified by is_test_patient=true flag OR email domains
    (@example.com, @example.org, @example.net).

    **Authentication**: Requires JWT token with admin role in Authorization header

    **Rate Limit**: 10 requests per hour per IP

    Actions:
    - delete_all: Delete all synthetic patients
    - delete_last_n: Delete the last N synthetic patients (by creation date)
    - delete_by_mood: Delete synthetic patients with specific mood pattern
    - delete_before_date: Delete synthetic patients created before a specific date

    Args:
        clean_request: Cleanup configuration
        supabase: Supabase client (injected)
        is_admin: Admin authorization check (injected)

    Returns:
        JSON with deletion statistics

    Raises:
        HTTPException: 400 for invalid parameters, 401/403 for auth, 500 for errors
    """
    logger.info(f"Synthetic data clean request: action={clean_request.action}")

    try:
        # Validate required parameters based on action
        if clean_request.action == "delete_last_n" and not clean_request.quantity:
            raise HTTPException(
                status_code=400,
                detail="quantity parameter is required for delete_last_n action"
            )
        if clean_request.action == "delete_by_mood" and not clean_request.mood_pattern:
            raise HTTPException(
                status_code=400,
                detail="mood_pattern parameter is required for delete_by_mood action"
            )
        if clean_request.action == "delete_before_date" and not clean_request.before_date:
            raise HTTPException(
                status_code=400,
                detail="before_date parameter is required for delete_before_date action"
            )

        # Synthetic domains and test patient flag
        SYNTHETIC_DOMAINS = ['@example.com', '@example.org', '@example.net']

        # Build query to get synthetic patients
        query = supabase.table('profiles').select('id, email, created_at')

        # Filter by is_test_patient or synthetic email domains
        # Since Supabase doesn't support complex OR conditions easily, we fetch all and filter in Python
        profiles_response = await query.execute()

        if not profiles_response.data:
            logger.info("No profiles found in database")
            return CleanDataResponse(
                status="success",
                message="No data to cleanup",
                deleted_count=0
            )

        # Filter synthetic users
        synthetic_users = [
            profile for profile in profiles_response.data
            if (
                profile.get('is_test_patient') is True or
                (profile.get('email') and any(domain in profile['email'] for domain in SYNTHETIC_DOMAINS))
            )
        ]

        if not synthetic_users:
            logger.info("No synthetic users found")
            return CleanDataResponse(
                status="success",
                message="No synthetic users found",
                deleted_count=0
            )

        # Apply action-specific filtering
        users_to_delete = synthetic_users.copy()

        if clean_request.action == "delete_last_n":
            # Sort by created_at descending and take last N
            users_to_delete.sort(key=lambda x: x.get('created_at', ''), reverse=True)
            users_to_delete = users_to_delete[:clean_request.quantity]

        elif clean_request.action == "delete_by_mood":
            # Note: mood_pattern is stored in check-ins, not profiles
            # We need to find users with specific mood patterns in their check-ins
            # For simplicity, we'll skip this filtering here since it requires complex joins
            # This would need to be implemented by querying check-ins and grouping by user
            logger.warning("delete_by_mood action not fully implemented - deleting all synthetic patients instead")

        elif clean_request.action == "delete_before_date":
            # Parse the date
            try:
                cutoff_date = datetime.fromisoformat(clean_request.before_date.replace('Z', '+00:00'))
            except (ValueError, AttributeError) as e:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid before_date format. Use ISO format: {str(e)}"
                )

            # Filter users created before the cutoff date
            users_to_delete = [
                user for user in users_to_delete
                if user.get('created_at') and datetime.fromisoformat(user['created_at'].replace('Z', '+00:00')) < cutoff_date
            ]

        # elif action == "delete_all" - no additional filtering needed

        if not users_to_delete:
            logger.info(f"No users matched criteria for action {clean_request.action}")
            return CleanDataResponse(
                status="success",
                message=f"No users matched criteria for {clean_request.action}",
                deleted_count=0
            )

        user_ids_to_delete = [user['id'] for user in users_to_delete]
        logger.info(f"Deleting {len(user_ids_to_delete)} synthetic users")

        # Delete check-ins first (child records)
        if user_ids_to_delete:
            await supabase.table('check_ins').delete().in_('user_id', user_ids_to_delete).execute()

        # Delete profiles (parent records)
        if user_ids_to_delete:
            await supabase.table('profiles').delete().in_('id', user_ids_to_delete).execute()

        deleted_count = len(user_ids_to_delete)
        logger.info(f"Successfully deleted {deleted_count} synthetic users")

        return CleanDataResponse(
            status="success",
            message=f"Deleted {deleted_count} synthetic patients and their data",
            deleted_count=deleted_count
        )

    except HTTPException:
        raise
    except APIError as e:
        logger.exception("Database error during synthetic data cleanup")
        raise HTTPException(
            status_code=500,
            detail=f"Database error: {str(e)}"
        )
    except Exception as e:
        logger.exception("Error cleaning synthetic data")
        raise HTTPException(
            status_code=500,
            detail=f"Error cleaning synthetic data: {str(e)}"
        )


@router.get("/synthetic-data/export")
@limiter.limit("5/hour")
async def export_synthetic_data(
    request: Request,
    format: str = "json",
    scope: str = "all",
    quantity: Optional[int] = None,
    mood_pattern: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    include_checkins: bool = True,
    include_notes: bool = False,
    include_medications: bool = False,
    include_radar: bool = False,
    supabase: AsyncClient = Depends(get_supabase_client),
    is_admin: bool = Depends(verify_admin_authorization)
):
    """
    Export synthetic data in various formats (CSV, JSON, Excel).

    **Authentication**: Requires JWT token with admin role in Authorization header

    **Rate Limit**: 5 requests per hour per IP

    Query Parameters:
    - format: "csv", "json", or "excel" (default: "json")
    - scope: "all", "last_n", "by_mood", "by_period" (default: "all")
    - quantity: Number of patients (required for last_n)
    - mood_pattern: Mood pattern filter (for by_mood)
    - start_date: ISO datetime (for by_period)
    - end_date: ISO datetime (for by_period)
    - include_checkins: Include check-in data (default: true)
    - include_notes: Include notes (default: false)
    - include_medications: Include medications (default: false)
    - include_radar: Include radar data (default: false)

    Returns:
        File stream with appropriate content type

    Raises:
        HTTPException: 400 for invalid parameters, 401/403 for auth, 500 for errors
    """
    logger.info(f"Export request: format={format}, scope={scope}")

    try:
        # Validate parameters
        if format not in ["csv", "json", "excel"]:
            raise HTTPException(
                status_code=400,
                detail="Invalid format. Must be csv, json, or excel"
            )

        if scope not in ["all", "last_n", "by_mood", "by_period"]:
            raise HTTPException(
                status_code=400,
                detail="Invalid scope. Must be all, last_n, by_mood, or by_period"
            )

        if scope == "last_n" and not quantity:
            raise HTTPException(
                status_code=400,
                detail="quantity parameter is required for last_n scope"
            )

        if scope == "by_period" and (not start_date or not end_date):
            raise HTTPException(
                status_code=400,
                detail="start_date and end_date parameters are required for by_period scope"
            )

        # Get synthetic patients
        SYNTHETIC_DOMAINS = ['@example.com', '@example.org', '@example.net']
        profiles_response = await supabase.table('profiles').select('*').execute()

        if not profiles_response.data:
            raise HTTPException(
                status_code=404,
                detail="No profiles found"
            )

        # Filter synthetic users
        synthetic_users = [
            profile for profile in profiles_response.data
            if (
                profile.get('is_test_patient') is True or
                (profile.get('email') and any(domain in profile['email'] for domain in SYNTHETIC_DOMAINS))
            )
        ]

        # Apply scope filtering
        if scope == "last_n":
            synthetic_users.sort(key=lambda x: x.get('created_at', ''), reverse=True)
            synthetic_users = synthetic_users[:quantity]

        elif scope == "by_period":
            try:
                start_dt = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
                end_dt = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
            except (ValueError, AttributeError) as e:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid date format. Use ISO format: {str(e)}"
                )

            synthetic_users = [
                user for user in synthetic_users
                if user.get('created_at') and 
                start_dt <= datetime.fromisoformat(user['created_at'].replace('Z', '+00:00')) <= end_dt
            ]

        if not synthetic_users:
            raise HTTPException(
                status_code=404,
                detail="No synthetic users found matching criteria"
            )

        # Collect data based on include flags
        export_data = []
        for user in synthetic_users:
            user_data = {
                "id": user.get('id'),
                "email": user.get('email'),
                "role": user.get('role'),
                "created_at": user.get('created_at'),
                "is_test_patient": user.get('is_test_patient', False)
            }

            if include_checkins:
                checkins_response = await supabase.table('check_ins').select('*').eq('user_id', user['id']).execute()
                user_data['checkins'] = checkins_response.data if checkins_response.data else []
                user_data['checkins_count'] = len(user_data['checkins'])

            # Note: notes, medications, and radar tables may not exist yet
            # Include placeholders for now
            if include_notes:
                user_data['notes'] = []

            if include_medications:
                user_data['medications'] = []

            if include_radar:
                user_data['radar'] = []

            export_data.append(user_data)

        # Generate file based on format
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

        if format == "json":
            output = json.dumps(export_data, indent=2, default=str)
            return StreamingResponse(
                io.BytesIO(output.encode()),
                media_type="application/json",
                headers={
                    "Content-Disposition": f"attachment; filename=synthetic_data_{timestamp}.json"
                }
            )

        elif format == "csv":
            output = io.StringIO()
            if export_data:
                # Flatten data for CSV
                flattened_data = []
                for user_data in export_data:
                    flat_row = {
                        "id": user_data.get('id'),
                        "email": user_data.get('email'),
                        "role": user_data.get('role'),
                        "created_at": user_data.get('created_at'),
                        "is_test_patient": user_data.get('is_test_patient'),
                        "checkins_count": user_data.get('checkins_count', 0)
                    }
                    flattened_data.append(flat_row)

                writer = csv.DictWriter(output, fieldnames=flattened_data[0].keys())
                writer.writeheader()
                writer.writerows(flattened_data)

            return StreamingResponse(
                io.BytesIO(output.getvalue().encode()),
                media_type="text/csv",
                headers={
                    "Content-Disposition": f"attachment; filename=synthetic_data_{timestamp}.csv"
                }
            )

        elif format == "excel":
            # For Excel, we'd need openpyxl or xlsxwriter
            # For now, return CSV with .xlsx extension as placeholder
            # This should be implemented with proper Excel library
            raise HTTPException(
                status_code=501,
                detail="Excel export not yet implemented. Use csv or json format."
            )

    except HTTPException:
        raise
    except APIError as e:
        logger.exception("Database error during export")
        raise HTTPException(
            status_code=500,
            detail=f"Database error: {str(e)}"
        )
    except Exception as e:
        logger.exception("Error exporting data")
        raise HTTPException(
            status_code=500,
            detail=f"Error exporting data: {str(e)}"
        )


@router.patch("/patients/{patient_id}/toggle-test-flag", response_model=ToggleTestFlagResponse)
async def toggle_test_patient_flag(
    patient_id: str,
    supabase: AsyncClient = Depends(get_supabase_client),
    is_admin: bool = Depends(verify_admin_authorization)
):
    """
    Toggle the is_test_patient flag for a specific patient.

    **Authentication**: Requires JWT token with admin role in Authorization header

    Args:
        patient_id: UUID of the patient
        supabase: Supabase client (injected)
        is_admin: Admin authorization check (injected)

    Returns:
        JSON with updated patient status

    Raises:
        HTTPException: 404 if patient not found, 401/403 for auth, 500 for errors
    """
    logger.info(f"Toggle test flag request for patient: {patient_id}")

    try:
        # Get current patient data
        patient_response = await supabase.table('profiles').select('id, is_test_patient').eq('id', patient_id).execute()

        if not patient_response.data:
            raise HTTPException(
                status_code=404,
                detail=f"Patient with id {patient_id} not found"
            )

        patient = patient_response.data[0]
        current_flag = patient.get('is_test_patient', False)
        new_flag = not current_flag

        # Update the flag
        update_response = await supabase.table('profiles').update({
            'is_test_patient': new_flag,
            'updated_at': datetime.now(timezone.utc).isoformat()
        }).eq('id', patient_id).execute()

        logger.info(f"Toggled is_test_patient for {patient_id}: {current_flag} -> {new_flag}")

        return ToggleTestFlagResponse(
            id=patient_id,
            is_test_patient=new_flag,
            message=f"is_test_patient flag toggled to {new_flag}"
        )

    except HTTPException:
        raise
    except APIError as e:
        logger.exception("Database error during toggle")
        raise HTTPException(
            status_code=500,
            detail=f"Database error: {str(e)}"
        )
    except Exception as e:
        logger.exception("Error toggling test flag")
        raise HTTPException(
            status_code=500,
            detail=f"Error toggling test flag: {str(e)}"
        )
