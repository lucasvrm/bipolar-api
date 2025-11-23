# Database Architecture and Admin Operations Guide

## Overview

This document describes the database architecture, Row-Level Security (RLS) policies, and SQL helper functions for the Bipolar API mental health SaaS platform. It is intended for backend developers who need to understand how to safely perform admin operations at the database level.

## Table of Contents

1. [Schema Overview](#schema-overview)
2. [User Types and Deletion Semantics](#user-types-and-deletion-semantics)
3. [RLS Policies](#rls-policies)
4. [SQL Helper Functions](#sql-helper-functions)
5. [Backend Integration Guide](#backend-integration-guide)
6. [Security Considerations](#security-considerations)

## Schema Overview

### Core Tables

#### profiles
User identity table with the following key columns:
- `id` (uuid, PK): References `auth.users(id)` - created by trigger
- `role` (text): 'patient', 'therapist', or 'admin'
- `email` (text): User email
- `is_test_patient` (boolean): Flag for test/synthetic users
- `source` (text): 'admin_manual', 'synthetic', 'signup', or 'unknown'
- `deleted_at` (timestamp): Soft delete timestamp
- `deletion_scheduled_at` (timestamp): Account deletion scheduling
- `deletion_token` (uuid): Token for canceling deletion

**CRITICAL INVARIANT**: When a new `auth.users` row is created, a Supabase trigger automatically inserts a row into `public.profiles`. Backend code should:
1. Create user in `auth.users` (via Supabase Admin API)
2. UPDATE the auto-created profile row with additional data
3. Only INSERT to profiles as fallback if trigger failed

#### check_ins
Daily patient check-in data:
- `id` (uuid, PK)
- `user_id` (uuid, FK → profiles.id ON DELETE CASCADE)
- `checkin_date` (date)
- `sleep_data` (jsonb)
- `mood_data` (jsonb)
- `symptoms_data` (jsonb)
- `risk_routine_data` (jsonb)
- `appetite_impulse_data` (jsonb)
- `meds_context_data` (jsonb)

#### clinical_notes
Therapist notes about therapy sessions:
- `id` (uuid, PK)
- `therapist_id` (uuid, FK → profiles.id ON DELETE CASCADE)
- `patient_id` (uuid, FK → profiles.id ON DELETE CASCADE)
- `note_content` (text)
- `title` (text)

#### crisis_plan
Patient crisis intervention plans:
- `id` (uuid, PK)
- `user_id` (uuid, FK → profiles.id ON DELETE CASCADE, UNIQUE)
- `triggers` (text)
- `warningsigns` (text)
- `copingstrategies` (text)
- `whatnottodo` (text)
- `spotifyplaylists` (jsonb)
- `emergency_contacts` (jsonb)

#### therapist_patients
Therapist-patient relationship mapping:
- `therapist_id` (uuid, FK → profiles.id ON DELETE CASCADE)
- `patient_id` (uuid, FK → profiles.id ON DELETE CASCADE, UNIQUE)
- Each patient can have exactly one therapist (patient_id is UNIQUE)

#### audit_log
Macro-level audit logging for admin operations:
- `id` (uuid, PK)
- `user_id` (uuid, nullable): Primary affected user
- `action` (text): Action identifier
- `details` (jsonb): Operation statistics and parameters
- `performed_by` (uuid): Admin user ID
- `created_at` (timestamp)

## User Types and Deletion Semantics

### Test/Synthetic Users (`is_test_patient = true`)

**Deletion Strategy: HARD DELETE**

When deleting test users, ALL related data is permanently removed in this order:
1. therapist_patients (relationships)
2. clinical_notes (as therapist or patient)
3. check_ins (patient data)
4. crisis_plan (patient data)
5. profiles (user identity)
6. auth.users (via backend Supabase Admin API - NOT by SQL)

**Source Values**: 
- 'synthetic': Auto-generated test data
- 'admin_manual': Manually created test users

### Normal Users (`is_test_patient = false`)

**Deletion Strategy: SOFT DELETE**

Normal users are soft-deleted by setting:
- `deleted_at`: Current timestamp
- `deletion_scheduled_at`: When deletion was requested

Domain data (check_ins, clinical_notes, etc.) may be wiped in mass "clear database" operations, but the user identity (`profiles` row) remains with `deleted_at` set.

**Source Values**:
- 'signup': Normal user registration
- 'admin_manual': Manually created real users

## RLS Policies

### Admin Access Policies

All core tables have RLS policies that grant full CRUD access to authenticated users with `role='admin'`:

```sql
-- Example: Admin access to check_ins
CREATE POLICY "admin_full_access_check_ins" ON public.check_ins
  FOR ALL
  TO authenticated
  USING (
    EXISTS (
      SELECT 1 FROM public.profiles
      WHERE id = auth.uid() AND role = 'admin'
    )
  )
  WITH CHECK (
    EXISTS (
      SELECT 1 FROM public.profiles
      WHERE id = auth.uid() AND role = 'admin'
    )
  );
```

**Tables with Admin Policies**:
- check_ins
- clinical_notes
- crisis_plan
- profiles
- therapist_patients

### Service Role Access

The `service_role` has unrestricted access to all tables. Most admin operations in production should use the service role for backend operations.

### Patient and Therapist Policies

Existing RLS policies (not modified by this implementation):

**check_ins**:
- Patients: CRUD own rows (`auth.uid() = user_id`)
- Therapists: SELECT patient check-ins if linked in therapist_patients

**clinical_notes**:
- Therapists: CRUD own notes (`auth.uid() = therapist_id`)

**crisis_plan**:
- Patients: CRUD own plan (`auth.uid() = user_id`)
- Therapists: SELECT if linked via therapist_patients

**profiles**:
- Users: INSERT/READ/UPDATE own profile (`auth.uid() = id`)
- Therapists: READ patient profiles if linked via therapist_patients

**therapist_patients**:
- Patients: VIEW their therapist
- Therapists: VIEW their patients

## SQL Helper Functions

### 1. log_admin_action

Create macro-level audit log entries for admin operations.

**Signature**:
```sql
log_admin_action(
  p_action text,
  p_performed_by uuid,
  p_user_id uuid DEFAULT NULL,
  p_details jsonb DEFAULT NULL
) RETURNS uuid
```

**Parameters**:
- `p_action`: Action identifier (e.g., 'delete_test_users', 'synthetic_generate', 'bulk_users_create')
- `p_performed_by`: UUID of admin user performing the action
- `p_user_id`: Optional UUID of primary affected user (NULL for bulk operations)
- `p_details`: JSONB object with operation details (counts, parameters, environment, etc.)

**Returns**: UUID of created audit log entry

**Example Usage**:
```sql
-- Log synthetic data generation
SELECT log_admin_action(
  'synthetic_generate',
  'xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx',  -- admin UUID
  NULL,                                      -- no specific user
  jsonb_build_object(
    'patients_created', 10,
    'therapists_created', 2,
    'checkins_created', 150,
    'pattern', 'cycling',
    'environment', 'production'
  )
);

-- Log user deletion
SELECT log_admin_action(
  'delete_test_users',
  'xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx',  -- admin UUID
  NULL,                                      -- bulk operation
  jsonb_build_object(
    'deleted_profiles', 5,
    'deleted_checkins', 75,
    'deleted_clinical_notes', 10,
    'sample_ids', ARRAY['user-id-1', 'user-id-2']
  )
);
```

### 2. delete_test_users

Hard delete test/synthetic users and all their related data.

**Signature**:
```sql
delete_test_users(
  p_dry_run boolean DEFAULT true,
  p_before_date timestamp with time zone DEFAULT NULL,
  p_limit integer DEFAULT NULL
) RETURNS jsonb
```

**Parameters**:
- `p_dry_run`: If true, returns counts without actually deleting (default: true)
- `p_before_date`: Only delete users created before this timestamp (optional)
- `p_limit`: Maximum number of users to delete (optional, for safety)

**Returns**: JSONB object with statistics:
```json
{
  "dry_run": true/false,
  "deleted_profiles": 10,
  "deleted_check_ins": 150,
  "deleted_clinical_notes": 25,
  "deleted_crisis_plans": 8,
  "deleted_therapist_patients": 10,
  "sample_user_ids": ["uuid1", "uuid2", "..."],
  "execution_time_ms": 245.67
}
```

**Deletion Order** (maintains referential integrity):
1. therapist_patients
2. clinical_notes
3. check_ins
4. crisis_plan
5. profiles

**⚠️ CRITICAL**: This function does NOT delete `auth.users` rows. Backend must handle that separately using Supabase Admin API.

**Example Usage**:
```sql
-- Dry run to preview what would be deleted
SELECT delete_test_users(p_dry_run := true);

-- Delete all test users
SELECT delete_test_users(p_dry_run := false);

-- Delete test users created before Jan 1, 2024
SELECT delete_test_users(
  p_dry_run := false,
  p_before_date := '2024-01-01T00:00:00Z'
);

-- Delete up to 50 oldest test users
SELECT delete_test_users(
  p_dry_run := false,
  p_limit := 50
);
```

### 3. clear_database

Wipe domain tables while respecting hard/soft delete rules.

**Signature**:
```sql
clear_database(
  p_dry_run boolean DEFAULT true,
  p_delete_test_users boolean DEFAULT true,
  p_soft_delete_normal_users boolean DEFAULT false,
  p_clear_audit_log boolean DEFAULT false,
  p_clear_domain_data_only boolean DEFAULT false
) RETURNS jsonb
```

**Parameters**:
- `p_dry_run`: If true, returns counts without deleting (default: true)
- `p_delete_test_users`: If true, hard delete test users (default: true)
- `p_soft_delete_normal_users`: If true, soft delete normal users (default: false)
- `p_clear_audit_log`: If true, also clear audit_log table (default: false)
- `p_clear_domain_data_only`: If true, only clear domain data, keep profiles (default: false)

**Returns**: JSONB object with statistics:
```json
{
  "dry_run": true/false,
  "cleared_therapist_patients": 25,
  "cleared_clinical_notes": 100,
  "cleared_check_ins": 500,
  "cleared_crisis_plans": 20,
  "deleted_test_profiles": 10,
  "soft_deleted_normal_users": 0,
  "cleared_audit_logs": 0,
  "execution_time_ms": 567.89,
  "options": {
    "delete_test_users": true,
    "soft_delete_normal_users": false,
    "clear_audit_log": false,
    "clear_domain_data_only": false
  }
}
```

**⚠️ WARNING**: This is a powerful and destructive function. Use with extreme caution, primarily for testing/reset scenarios.

**Example Usage**:
```sql
-- Dry run to see what would be affected
SELECT clear_database(p_dry_run := true);

-- Clear all domain data and hard delete test users (common test cleanup)
SELECT clear_database(
  p_dry_run := false,
  p_delete_test_users := true
);

-- Clear domain data only, keep all profiles intact
SELECT clear_database(
  p_dry_run := false,
  p_clear_domain_data_only := true
);

-- Full wipe including soft delete of normal users and audit logs
SELECT clear_database(
  p_dry_run := false,
  p_delete_test_users := true,
  p_soft_delete_normal_users := true,
  p_clear_audit_log := true
);
```

## Backend Integration Guide

### Using SQL Functions from Python/FastAPI

```python
from supabase import Client

async def delete_test_users_backend(
    supabase: Client,
    admin_user_id: str,
    dry_run: bool = True,
    before_date: str = None,
    limit: int = None
):
    """
    Delete test users using the delete_test_users SQL function.
    
    Args:
        supabase: Supabase service role client
        admin_user_id: UUID of admin performing the operation
        dry_run: If True, only return counts without deleting
        before_date: ISO timestamp string to filter users
        limit: Maximum number of users to delete
    
    Returns:
        dict: Statistics about deleted records
    """
    # Call the SQL function via RPC
    result = supabase.rpc(
        'delete_test_users',
        {
            'p_dry_run': dry_run,
            'p_before_date': before_date,
            'p_limit': limit
        }
    ).execute()
    
    stats = result.data
    
    # If not dry run, also delete auth.users
    if not dry_run and stats.get('deleted_profiles', 0) > 0:
        user_ids = stats.get('sample_user_ids', [])
        # Expand to get all affected user IDs if needed
        # Then delete from auth.users using Admin API
        for user_id in user_ids:
            try:
                supabase.auth.admin.delete_user(user_id)
            except Exception as e:
                logger.error(f"Failed to delete auth.user {user_id}: {e}")
    
    # Log the operation
    await log_admin_action(
        supabase=supabase,
        action='delete_test_users',
        performed_by=admin_user_id,
        user_id=None,  # bulk operation
        details={
            'dry_run': dry_run,
            'stats': stats,
            'before_date': before_date,
            'limit': limit
        }
    )
    
    return stats


async def log_admin_action(
    supabase: Client,
    action: str,
    performed_by: str = None,
    user_id: str = None,
    details: dict = None
):
    """
    Log an admin action using the log_admin_action SQL function.
    
    Args:
        supabase: Supabase service role client
        action: Action identifier
        performed_by: UUID of admin user (can be None for system operations)
        user_id: Optional UUID of affected user
        details: Dictionary with operation details
    
    Returns:
        str: UUID of created audit log entry
    """
    import json
    
    result = supabase.rpc(
        'log_admin_action',
        {
            'p_action': action,
            'p_performed_by': performed_by,
            'p_user_id': user_id,
            'p_details': json.dumps(details) if details else None
        }
    ).execute()
    
    return result.data


async def clear_database_backend(
    supabase: Client,
    admin_user_id: str,
    dry_run: bool = True,
    delete_test_users: bool = True,
    soft_delete_normal_users: bool = False,
    clear_audit_log: bool = False,
    clear_domain_data_only: bool = False
):
    """
    Clear database using the clear_database SQL function.
    
    WARNING: This is a destructive operation. Use with extreme caution.
    
    Args:
        supabase: Supabase service role client
        admin_user_id: UUID of admin performing the operation
        dry_run: If True, only return counts without deleting
        delete_test_users: If True, hard delete test users
        soft_delete_normal_users: If True, soft delete normal users
        clear_audit_log: If True, also clear audit log
        clear_domain_data_only: If True, only clear domain data
    
    Returns:
        dict: Statistics about cleared/deleted records
    """
    result = supabase.rpc(
        'clear_database',
        {
            'p_dry_run': dry_run,
            'p_delete_test_users': delete_test_users,
            'p_soft_delete_normal_users': soft_delete_normal_users,
            'p_clear_audit_log': clear_audit_log,
            'p_clear_domain_data_only': clear_domain_data_only
        }
    ).execute()
    
    stats = result.data
    
    # If not dry run and test users were deleted, also clean auth.users
    if not dry_run and delete_test_users and stats.get('deleted_test_profiles', 0) > 0:
        # Get all test user IDs and delete from auth
        test_users = supabase.table('profiles')\
            .select('id')\
            .eq('is_test_patient', True)\
            .execute()
        
        # Note: These profiles are already deleted, so this query won't find them
        # Backend should track user IDs before calling clear_database if needed
    
    # Log the operation
    await log_admin_action(
        supabase=supabase,
        action='clear_database',
        performed_by=admin_user_id,
        user_id=None,
        details={
            'dry_run': dry_run,
            'stats': stats,
            'options': {
                'delete_test_users': delete_test_users,
                'soft_delete_normal_users': soft_delete_normal_users,
                'clear_audit_log': clear_audit_log,
                'clear_domain_data_only': clear_domain_data_only
            }
        }
    )
    
    return stats
```

### Recommended Backend Workflow

1. **Always use dry_run first**: Preview what will be affected before actual deletion
2. **Log all operations**: Use `log_admin_action` for audit trail
3. **Handle auth.users separately**: SQL functions don't delete auth.users - use Admin API
4. **Use service role**: Most admin operations should use service_role client
5. **Rate limit**: Implement rate limiting on admin endpoints
6. **Validate admin role**: Always verify user has admin role before operations

### Example Endpoint Implementation

```python
from fastapi import APIRouter, Depends, HTTPException
from api.dependencies import get_supabase_service, verify_admin_authorization

router = APIRouter(prefix="/api/admin", tags=["Admin"])

@router.post("/delete-test-users")
async def delete_test_users_endpoint(
    dry_run: bool = True,
    before_date: str = None,
    limit: int = None,
    supabase: Client = Depends(get_supabase_service),
    is_admin: bool = Depends(verify_admin_authorization),
):
    """
    Delete test/synthetic users and their data.
    
    Requires admin role.
    """
    try:
        # Get admin user ID from auth context
        admin_user = supabase.auth.get_user()
        admin_user_id = admin_user.user.id if admin_user and admin_user.user else None
        
        # Call backend helper
        stats = await delete_test_users_backend(
            supabase=supabase,
            admin_user_id=admin_user_id,
            dry_run=dry_run,
            before_date=before_date,
            limit=limit
        )
        
        return {
            "status": "success",
            "dry_run": dry_run,
            "statistics": stats
        }
    except Exception as e:
        logger.exception("Failed to delete test users")
        raise HTTPException(status_code=500, detail=str(e))
```

## Security Considerations

### Function Security

All SQL functions are implemented with:
- **SECURITY DEFINER**: Functions run with elevated privileges
- **search_path = public, extensions**: Prevents injection attacks
- **Input validation**: All parameters validated before use
- **Idempotent operations**: Can be re-run safely

### Access Control

- **Service Role**: Has unrestricted access to all tables and functions
- **Admin Role**: RLS policies grant full access when `role='admin'`
- **Authenticated Users**: Limited by existing RLS policies for their role
- **Anonymous Users**: No access to these operations

### Best Practices

1. **Never expose service role key**: Keep it secure, use only in backend
2. **Always verify admin role**: Check user role before operations
3. **Log all admin actions**: Use audit_log for compliance
4. **Use dry_run by default**: Preview changes before execution
5. **Limit blast radius**: Use `p_limit` parameter for large operations
6. **Monitor audit logs**: Regularly review admin operations
7. **Test in non-prod first**: Validate operations in dev/staging

### Data Protection

- **Soft delete by default**: Normal users are soft deleted
- **Hard delete only for test data**: Test users can be permanently removed
- **Referential integrity**: All deletions respect FK constraints
- **Cascading deletes**: Configured correctly to avoid orphaned data
- **No auth.users deletion**: SQL functions don't delete auth, preventing lockouts

## Troubleshooting

### Function doesn't exist

If you get "function does not exist" errors:
1. Verify migration 009 has been applied
2. Check schema: `\df public.delete_test_users` in psql
3. Ensure function name and parameters match

### Permission denied

If you get permission errors:
1. Verify using service_role client for backend operations
2. Check user has admin role for authenticated requests
3. Ensure GRANT statements were executed

### Cascade violations

If you get foreign key constraint errors:
1. Functions handle deletion order correctly - shouldn't happen
2. Check if custom FK constraints exist
3. Verify CASCADE is configured on foreign keys

### Auth.users not deleted

This is expected behavior:
1. SQL functions don't delete auth.users (by design)
2. Backend must delete from auth.users using Admin API
3. Prevents accidental account lockouts

## Migration Checklist

When deploying migration 009:

- [ ] Backup database before applying
- [ ] Apply migration in test environment first
- [ ] Verify all functions created: `\df public.*`
- [ ] Verify all policies created: `\d+ check_ins` (etc.)
- [ ] Test dry_run mode for all functions
- [ ] Test actual deletion with small dataset
- [ ] Verify audit logging works
- [ ] Update backend code to use new functions
- [ ] Update documentation
- [ ] Test admin RLS policies
- [ ] Deploy to staging
- [ ] Deploy to production

## Additional Resources

- [Supabase RLS Documentation](https://supabase.com/docs/guides/auth/row-level-security)
- [PostgreSQL Functions](https://www.postgresql.org/docs/current/sql-createfunction.html)
- [JSONB Functions](https://www.postgresql.org/docs/current/functions-json.html)
- Migration files: `/migrations/009_admin_rls_and_sql_functions.sql`
