"""
Daily scheduled job for processing hard deletions of accounts.

This job should be run daily (e.g., via pg_cron or Supabase Edge Function)
to process accounts that have passed their 14-day deletion grace period.
"""
import logging
import os
from datetime import datetime, timezone
from typing import List, Dict, Any
from supabase import acreate_client, AsyncClient
from supabase.lib.client_options import AsyncClientOptions

logger = logging.getLogger("bipolar-api.deletion_job")


async def get_supabase_admin_client() -> AsyncClient:
    """
    Create an admin Supabase client with service key.
    
    Returns:
        AsyncClient: Supabase client with admin privileges
    """
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_KEY")
    
    if not url or not key:
        raise ValueError("SUPABASE_URL and SUPABASE_SERVICE_KEY must be set")
    
    options = AsyncClientOptions(persist_session=False)
    client = await acreate_client(url, key, options=options)
    return client


async def log_audit_event(
    supabase: AsyncClient,
    user_id: str,
    action: str,
    details: Dict[str, Any]
) -> None:
    """
    Log an audit event.
    
    Args:
        supabase: Supabase client
        user_id: User ID
        action: Action type
        details: Additional details
    """
    try:
        await supabase.table('audit_log').insert({
            'user_id': user_id,
            'action': action,
            'details': details,
            'performed_by': None,  # System-performed action
            'created_at': datetime.now(timezone.utc).isoformat()
        }).execute()
        logger.info(f"Audit log created for user {user_id[:8]}... action: {action}")
    except Exception as e:
        logger.error(f"Failed to create audit log for user {user_id}: {e}")


async def hard_delete_user_data(supabase: AsyncClient, user_id: str, role: str) -> Dict[str, int]:
    """
    Hard delete all user data in cascading order.
    
    Args:
        supabase: Supabase client
        user_id: User ID to delete
        role: User role (patient or therapist)
    
    Returns:
        Dictionary with counts of deleted records
    """
    deleted_counts = {
        'check_ins': 0,
        'crisis_plan': 0,
        'clinical_notes': 0,
        'therapist_patients': 0,
        'user_consent': 0,
        'profile': 0
    }
    
    logger.info(f"Starting hard delete for user {user_id[:8]}... (role: {role})")
    
    try:
        # 1. Delete check-ins
        response = await supabase.table('check_ins').delete().eq('user_id', user_id).execute()
        deleted_counts['check_ins'] = len(response.data) if response.data else 0
        logger.info(f"Deleted {deleted_counts['check_ins']} check-ins")
        
        # 2. Delete crisis plan
        response = await supabase.table('crisis_plan').delete().eq('user_id', user_id).execute()
        deleted_counts['crisis_plan'] = len(response.data) if response.data else 0
        logger.info(f"Deleted {deleted_counts['crisis_plan']} crisis plans")
        
        # 3. Delete clinical notes (both as patient and therapist)
        response = await supabase.table('clinical_notes').delete().eq('patient_id', user_id).execute()
        count_as_patient = len(response.data) if response.data else 0
        
        response = await supabase.table('clinical_notes').delete().eq('therapist_id', user_id).execute()
        count_as_therapist = len(response.data) if response.data else 0
        
        deleted_counts['clinical_notes'] = count_as_patient + count_as_therapist
        logger.info(f"Deleted {deleted_counts['clinical_notes']} clinical notes")
        
        # 4. Delete therapist-patient relationships (both as patient and therapist)
        response = await supabase.table('therapist_patients').delete().eq('patient_id', user_id).execute()
        count_as_patient = len(response.data) if response.data else 0
        
        response = await supabase.table('therapist_patients').delete().eq('therapist_id', user_id).execute()
        count_as_therapist = len(response.data) if response.data else 0
        
        deleted_counts['therapist_patients'] = count_as_patient + count_as_therapist
        logger.info(f"Deleted {deleted_counts['therapist_patients']} therapist-patient relationships")
        
        # 5. Delete user consent
        response = await supabase.table('user_consent').delete().eq('user_id', user_id).execute()
        deleted_counts['user_consent'] = len(response.data) if response.data else 0
        logger.info(f"Deleted {deleted_counts['user_consent']} consent records")
        
        # 6. Delete profile (this will cascade to any remaining related records)
        response = await supabase.table('profiles').delete().eq('id', user_id).execute()
        deleted_counts['profile'] = len(response.data) if response.data else 0
        logger.info(f"Deleted {deleted_counts['profile']} profile record")
        
        # 7. Optionally delete from Supabase Auth
        # Note: This requires admin privileges and should be done carefully
        # await supabase.auth.admin.delete_user(user_id)
        # logger.info(f"Deleted user from Supabase Auth")
        
        return deleted_counts
        
    except Exception as e:
        logger.error(f"Error during hard delete for user {user_id}: {e}")
        raise


async def process_scheduled_deletions() -> Dict[str, Any]:
    """
    Process all users scheduled for deletion.
    
    This function finds all profiles where:
    - deletion_scheduled_at <= now()
    - deleted_at IS NULL
    
    And performs hard deletion for each one.
    
    Returns:
        Dictionary with job statistics
    """
    logger.info("=== Starting scheduled deletion job ===")
    start_time = datetime.now(timezone.utc)
    
    stats = {
        'started_at': start_time.isoformat(),
        'users_processed': 0,
        'users_deleted': 0,
        'errors': [],
        'total_records_deleted': {}
    }
    
    try:
        supabase = await get_supabase_admin_client()
        
        # Find users scheduled for deletion
        response = await supabase.table('profiles')\
            .select('id, email, role, deletion_scheduled_at')\
            .lte('deletion_scheduled_at', datetime.now(timezone.utc).isoformat())\
            .is_('deleted_at', 'null')\
            .execute()
        
        users_to_delete = response.data if response.data else []
        logger.info(f"Found {len(users_to_delete)} users scheduled for deletion")
        
        for user in users_to_delete:
            user_id = user['id']
            user_email = user.get('email', 'unknown')
            user_role = user.get('role', 'patient')
            
            stats['users_processed'] += 1
            
            try:
                logger.info(f"Processing deletion for user {user_id[:8]}... ({user_email})")
                
                # Perform hard delete
                deleted_counts = await hard_delete_user_data(supabase, user_id, user_role)
                
                # Update statistics
                for key, count in deleted_counts.items():
                    if key not in stats['total_records_deleted']:
                        stats['total_records_deleted'][key] = 0
                    stats['total_records_deleted'][key] += count
                
                # Log audit event
                await log_audit_event(
                    supabase,
                    user_id,
                    'hard_deleted',
                    {
                        'email': user_email,
                        'role': user_role,
                        'deletion_scheduled_at': user.get('deletion_scheduled_at'),
                        'deleted_records': deleted_counts
                    }
                )
                
                stats['users_deleted'] += 1
                logger.info(f"Successfully deleted user {user_id[:8]}...")
                
            except Exception as e:
                error_msg = f"Failed to delete user {user_id} ({user_email}): {str(e)}"
                logger.error(error_msg)
                stats['errors'].append({
                    'user_id': user_id,
                    'email': user_email,
                    'error': str(e)
                })
        
        end_time = datetime.now(timezone.utc)
        stats['completed_at'] = end_time.isoformat()
        stats['duration_seconds'] = (end_time - start_time).total_seconds()
        
        logger.info(f"=== Deletion job completed ===")
        logger.info(f"Processed: {stats['users_processed']}, Deleted: {stats['users_deleted']}, Errors: {len(stats['errors'])}")
        logger.info(f"Duration: {stats['duration_seconds']} seconds")
        
        return stats
        
    except Exception as e:
        logger.exception(f"Fatal error in deletion job: {e}")
        stats['fatal_error'] = str(e)
        return stats


# Main entry point for scheduled execution
async def main():
    """Main entry point for the deletion job."""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    try:
        stats = await process_scheduled_deletions()
        print(f"Job completed: {stats}")
        return stats
    except Exception as e:
        logger.exception(f"Job failed: {e}")
        raise


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
