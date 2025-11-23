"""
Account management endpoints for deletion and data export.

These endpoints handle account deletion requests, cancellations, and data export
with proper role-based access control and therapist-patient relationship validation.
"""
import os
import io
import csv
import json
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Header, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from supabase import Client
from postgrest.exceptions import APIError

from api.dependencies import get_supabase_client
from api.utils import validate_uuid_or_400, handle_postgrest_error, hash_user_id_for_logging
from api.rate_limiter import limiter

logger = logging.getLogger("bipolar-api.account")

router = APIRouter(prefix="/account", tags=["Account Management"])


class DeleteRequestResponse(BaseModel):
    """Response for deletion request"""
    status: str
    message: str
    deletion_scheduled_at: str
    deletion_date: str


class UndoDeleteRequest(BaseModel):
    """Request body for undo deletion"""
    token: str = Field(..., description="Deletion token received via email")


def get_user_from_token(authorization: Optional[str], supabase: Client) -> Dict[str, Any]:
    """
    Extract and validate user from JWT token.
    
    Args:
        authorization: Authorization header with Bearer token
        supabase: Supabase client
        
    Returns:
        User data dictionary
        
    Raises:
        HTTPException: 401 if unauthorized
    """
    if not authorization or not authorization.startswith("Bearer "):
        logger.warning("No valid authorization header provided")
        raise HTTPException(
            status_code=401,
            detail="Authorization required. Provide a valid JWT token."
        )
    
    token = authorization[7:]  # Remove "Bearer " prefix
    
    try:
        # Sync client's auth.get_user() is synchronous
        user_response = supabase.auth.get_user(token)
        
        if not user_response or not user_response.user:
            logger.error("Invalid JWT token - user not found")
            raise HTTPException(
                status_code=401,
                detail="Invalid authorization token"
            )
        
        return user_response.user
        
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error validating authorization: {e}")
        raise HTTPException(
            status_code=401,
            detail="Error validating authorization token"
        )


async def log_audit_event(
    supabase: Client,
    user_id: str,
    action: str,
    details: Dict[str, Any],
    performed_by: Optional[str] = None
) -> None:
    """
    Log an audit event.
    
    Args:
        supabase: Supabase client
        user_id: User ID
        action: Action type (delete_requested, delete_cancelled, hard_deleted, export_requested)
        details: Additional details
        performed_by: User ID who performed the action (None if self-service)
    """
    try:
        await supabase.table('audit_log').insert({
            'user_id': user_id,
            'action': action,
            'details': details,
            'performed_by': performed_by,
            'created_at': datetime.now(timezone.utc).isoformat()
        }).execute()
        logger.info(f"Audit log created for user {hash_user_id_for_logging(user_id)} action: {action}")
    except Exception as e:
        logger.error(f"Failed to create audit log: {e}")


@router.post("/export")
@limiter.limit("5/hour")
async def export_account_data(
    request: Request,
    anonymize: bool = False,
    supabase: Client = Depends(get_supabase_client),
    authorization: Optional[str] = Header(None)
):
    """
    Export all user data in ZIP format with JSON and CSV files.
    
    - **Patient**: Exports only their own data
    - **Therapist**: Exports own data + all linked patients' data (optional anonymization)
    
    The export includes:
    - Profile information
    - Check-ins
    - Crisis plans
    - Clinical notes
    - Therapist-patient relationships
    - Medications and context data
    
    Args:
        anonymize: For therapists, anonymize patient data (default: false)
        authorization: JWT token in Authorization header
        
    Returns:
        ZIP file with JSON and CSV exports
        
    Raises:
        HTTPException: 401 if unauthorized, 500 for errors
    """
    user = get_user_from_token(authorization, supabase)
    user_id = user.id
    
    logger.info(f"Data export requested for user {hash_user_id_for_logging(user_id)}")
    
    try:
        # Get user profile to check role
        profile_response = await supabase.table('profiles')\
            .select('id, email, role, is_admin, created_at')\
            .eq('id', user_id)\
            .execute()
        
        if not profile_response.data:
            raise HTTPException(status_code=404, detail="User profile not found")
        
        profile = profile_response.data[0]
        role = profile.get('role', 'patient')
        
        export_data = {
            'export_date': datetime.now(timezone.utc).isoformat(),
            'user_id': user_id if not anonymize else 'ANONYMIZED',
            'role': role,
            'profile': profile if not anonymize else {'role': role},
            'data': {}
        }
        
        # Export user's own data
        # Check-ins
        checkins_response = await supabase.table('check_ins')\
            .select('*')\
            .eq('user_id', user_id)\
            .execute()
        export_data['data']['check_ins'] = checkins_response.data if checkins_response.data else []
        
        # Crisis plan
        crisis_response = await supabase.table('crisis_plan')\
            .select('*')\
            .eq('user_id', user_id)\
            .execute()
        export_data['data']['crisis_plan'] = crisis_response.data if crisis_response.data else []
        
        # User consent
        consent_response = await supabase.table('user_consent')\
            .select('*')\
            .eq('user_id', user_id)\
            .execute()
        export_data['data']['user_consent'] = consent_response.data[0] if consent_response.data else None
        
        # If therapist, include patient data
        if role == 'therapist':
            # Get all patients linked to this therapist
            patients_response = await supabase.table('therapist_patients')\
                .select('patient_id, created_at, status')\
                .eq('therapist_id', user_id)\
                .eq('status', 'active')\
                .execute()
            
            patient_ids = [p['patient_id'] for p in (patients_response.data or [])]
            export_data['data']['my_patients'] = []
            
            for patient_id in patient_ids:
                # Get patient profile
                patient_profile_response = await supabase.table('profiles')\
                    .select('id, email, created_at')\
                    .eq('id', patient_id)\
                    .execute()
                
                patient_data = {
                    'patient_id': patient_id if not anonymize else f'PATIENT_{patient_ids.index(patient_id) + 1}',
                    'profile': patient_profile_response.data[0] if patient_profile_response.data and not anonymize else {},
                    'check_ins': [],
                    'crisis_plan': [],
                    'clinical_notes': []
                }
                
                # Get patient check-ins
                patient_checkins = await supabase.table('check_ins')\
                    .select('*')\
                    .eq('user_id', patient_id)\
                    .execute()
                patient_data['check_ins'] = patient_checkins.data if patient_checkins.data else []
                
                # Get patient crisis plan
                patient_crisis = await supabase.table('crisis_plan')\
                    .select('*')\
                    .eq('user_id', patient_id)\
                    .execute()
                patient_data['crisis_plan'] = patient_crisis.data if patient_crisis.data else []
                
                # Get clinical notes for this patient
                notes_response = await supabase.table('clinical_notes')\
                    .select('*')\
                    .eq('patient_id', patient_id)\
                    .eq('therapist_id', user_id)\
                    .execute()
                patient_data['clinical_notes'] = notes_response.data if notes_response.data else []
                
                export_data['data']['my_patients'].append(patient_data)
        
        # Get clinical notes where user is patient
        notes_as_patient = await supabase.table('clinical_notes')\
            .select('*')\
            .eq('patient_id', user_id)\
            .execute()
        export_data['data']['clinical_notes_as_patient'] = notes_as_patient.data if notes_as_patient.data else []
        
        # Create ZIP file with JSON and CSV
        import zipfile
        from io import BytesIO
        
        zip_buffer = BytesIO()
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            # Add full JSON export
            zip_file.writestr('export.json', json.dumps(export_data, indent=2, default=str))
            
            # Add CSV files for each data type
            # Check-ins CSV
            if export_data['data']['check_ins']:
                csv_buffer = io.StringIO()
                writer = csv.DictWriter(csv_buffer, fieldnames=export_data['data']['check_ins'][0].keys())
                writer.writeheader()
                writer.writerows(export_data['data']['check_ins'])
                zip_file.writestr('check_ins.csv', csv_buffer.getvalue())
            
            # Crisis plan CSV
            if export_data['data']['crisis_plan']:
                csv_buffer = io.StringIO()
                writer = csv.DictWriter(csv_buffer, fieldnames=export_data['data']['crisis_plan'][0].keys())
                writer.writeheader()
                writer.writerows(export_data['data']['crisis_plan'])
                zip_file.writestr('crisis_plan.csv', csv_buffer.getvalue())
        
        # Log audit event
        await log_audit_event(
            supabase,
            user_id,
            'export_requested',
            {
                'role': role,
                'anonymize': anonymize,
                'total_check_ins': len(export_data['data']['check_ins']),
                'num_patients': len(export_data['data'].get('my_patients', []))
            }
        )
        
        zip_buffer.seek(0)
        
        logger.info(f"Data export completed for user {hash_user_id_for_logging(user_id)}")
        
        return StreamingResponse(
            zip_buffer,
            media_type='application/zip',
            headers={
                'Content-Disposition': f'attachment; filename=account_export_{user_id[:8]}.zip'
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error exporting data for user {user_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error exporting account data: {str(e)}"
        )


@router.post("/delete-request", response_model=DeleteRequestResponse)
@limiter.limit("3/hour")
async def request_account_deletion(
    request: Request,
    supabase: Client = Depends(get_supabase_client),
    authorization: Optional[str] = Header(None)
):
    """
    Request account deletion with 14-day grace period.
    
    **For therapists**: Cannot delete if they have active patients. Must transfer or delink all patients first.
    
    **For patients**: If linked to a therapist, the therapist is notified immediately.
    
    Process:
    1. Validates user has no active patients (if therapist)
    2. Sets deletion_scheduled_at to now() + 14 days
    3. Generates new deletion_token
    4. Sends email with cancellation link
    5. Notifies therapist if user is a patient
    6. Logs audit event
    
    Args:
        authorization: JWT token in Authorization header
        
    Returns:
        Confirmation with deletion date and instructions
        
    Raises:
        HTTPException: 401 if unauthorized, 403 if therapist has active patients, 500 for errors
    """
    user = get_user_from_token(authorization, supabase)
    user_id = user.id
    
    logger.info(f"Deletion request for user {hash_user_id_for_logging(user_id)}")
    
    try:
        # Get user profile
        profile_response = await supabase.table('profiles')\
            .select('id, email, role')\
            .eq('id', user_id)\
            .execute()
        
        if not profile_response.data:
            raise HTTPException(status_code=404, detail="User profile not found")
        
        profile = profile_response.data[0]
        role = profile.get('role', 'patient')
        email = profile.get('email', '')
        
        # If therapist, check for active patients
        if role == 'therapist':
            patients_response = await supabase.table('therapist_patients')\
                .select('patient_id', count='exact')\
                .eq('therapist_id', user_id)\
                .eq('status', 'active')\
                .execute()
            
            active_patients_count = patients_response.count if hasattr(patients_response, 'count') else len(patients_response.data or [])
            
            if active_patients_count > 0:
                logger.warning(f"Therapist {hash_user_id_for_logging(user_id)} has {active_patients_count} active patients")
                raise HTTPException(
                    status_code=403,
                    detail=f"Você tem {active_patients_count} paciente(s) ativo(s). Transfira ou desvincule todos antes de excluir sua conta."
                )
        
        # Calculate deletion date (14 days from now)
        deletion_scheduled_at = datetime.now(timezone.utc) + timedelta(days=14)
        
        # Update profile with deletion schedule
        update_response = await supabase.table('profiles')\
            .update({
                'deletion_scheduled_at': deletion_scheduled_at.isoformat(),
                'deletion_token': None  # Will be regenerated by database default
            })\
            .eq('id', user_id)\
            .execute()
        
        # Get the updated token
        updated_profile = await supabase.table('profiles')\
            .select('deletion_token')\
            .eq('id', user_id)\
            .execute()
        
        deletion_token = updated_profile.data[0]['deletion_token'] if updated_profile.data else None
        
        # TODO: Send email with undo link
        # Email template should include:
        # Subject: Solicitação de Exclusão de Conta - Previso
        # Body: Link to https://previso-fe.vercel.app/undo-delete?token={deletion_token}
        # Expiration: {deletion_scheduled_at}
        logger.info(f"TODO: Send deletion email to {email} with token {deletion_token}")
        
        # If patient with therapist, notify therapist
        if role == 'patient':
            therapist_response = await supabase.table('therapist_patients')\
                .select('therapist_id')\
                .eq('patient_id', user_id)\
                .eq('status', 'active')\
                .execute()
            
            if therapist_response.data:
                for relationship in therapist_response.data:
                    therapist_id = relationship['therapist_id']
                    # TODO: Send notification to therapist
                    # Push notification + email: "O paciente [nome] solicitou exclusão da conta. 
                    # A conta será apagada permanentemente em [deletion_scheduled_at]."
                    logger.info(f"TODO: Notify therapist {therapist_id} about patient deletion request")
        
        # Log audit event
        await log_audit_event(
            supabase,
            user_id,
            'delete_requested',
            {
                'email': email,
                'role': role,
                'deletion_scheduled_at': deletion_scheduled_at.isoformat()
            }
        )
        
        logger.info(f"Deletion scheduled for user {hash_user_id_for_logging(user_id)} on {deletion_scheduled_at.isoformat()}")
        
        return DeleteRequestResponse(
            status="success",
            message="Sua conta foi agendada para exclusão. Você receberá um e-mail com instruções para cancelar se mudar de ideia.",
            deletion_scheduled_at=deletion_scheduled_at.isoformat(),
            deletion_date=deletion_scheduled_at.strftime("%d/%m/%Y às %H:%M")
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error requesting deletion for user {user_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error requesting account deletion: {str(e)}"
        )


@router.post("/undo-delete")
async def undo_account_deletion(
    undo_request: UndoDeleteRequest,
    supabase: Client = Depends(get_supabase_client)
):
    """
    Cancel a pending account deletion using the token received via email.
    
    This is a public endpoint that doesn't require authentication - only the unique token.
    
    Process:
    1. Finds profile by deletion_token
    2. Validates deletion_scheduled_at > now() (still in grace period)
    3. Clears deletion_scheduled_at and deletion_token
    4. Logs audit event
    
    Args:
        undo_request: Request with deletion token
        
    Returns:
        Confirmation of cancellation
        
    Raises:
        HTTPException: 404 if token invalid/expired, 500 for errors
    """
    token = undo_request.token
    validate_uuid_or_400(token, "token")
    
    logger.info(f"Undo deletion request with token {token[:8]}...")
    
    try:
        # Find profile by token
        profile_response = await supabase.table('profiles')\
            .select('id, email, deletion_scheduled_at')\
            .eq('deletion_token', token)\
            .execute()
        
        if not profile_response.data:
            logger.warning(f"Invalid or expired deletion token: {token}")
            raise HTTPException(
                status_code=404,
                detail="Token de cancelamento inválido ou expirado."
            )
        
        profile = profile_response.data[0]
        user_id = profile['id']
        deletion_scheduled_at = profile.get('deletion_scheduled_at')
        
        # Validate token is still valid (deletion not yet executed)
        if not deletion_scheduled_at:
            raise HTTPException(
                status_code=400,
                detail="Esta conta não está agendada para exclusão."
            )
        
        deletion_date = datetime.fromisoformat(deletion_scheduled_at.replace('Z', '+00:00'))
        if deletion_date <= datetime.now(timezone.utc):
            raise HTTPException(
                status_code=400,
                detail="O período de cancelamento expirou. A conta já foi ou está sendo excluída."
            )
        
        # Cancel deletion
        await supabase.table('profiles')\
            .update({
                'deletion_scheduled_at': None,
                'deletion_token': None
            })\
            .eq('id', user_id)\
            .execute()
        
        # Log audit event
        await log_audit_event(
            supabase,
            user_id,
            'delete_cancelled',
            {
                'email': profile.get('email'),
                'cancelled_at': datetime.now(timezone.utc).isoformat(),
                'was_scheduled_for': deletion_scheduled_at
            }
        )
        
        logger.info(f"Deletion cancelled for user {hash_user_id_for_logging(user_id)}")
        
        return {
            'status': 'success',
            'message': 'Exclusão cancelada com sucesso. Sua conta permanecerá ativa.',
            'user_id': user_id
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error undoing deletion: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error canceling account deletion: {str(e)}"
        )
