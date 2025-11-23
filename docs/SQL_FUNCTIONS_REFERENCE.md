# SQL Helper Functions - Quick Reference Guide

This is a quick reference for using the SQL helper functions for admin operations. For comprehensive documentation, see [DATABASE_ARCHITECTURE.md](./DATABASE_ARCHITECTURE.md).

## Table of Contents

- [log_admin_action](#log_admin_action)
- [delete_test_users](#delete_test_users)
- [clear_database](#clear_database)
- [Common Patterns](#common-patterns)

---

## log_admin_action

**Purpose**: Create audit log entries for admin operations

**Signature**:
```sql
log_admin_action(
  p_action text,
  p_performed_by uuid,
  p_user_id uuid DEFAULT NULL,
  p_details jsonb DEFAULT NULL
) RETURNS uuid
```

**Quick Examples**:

```sql
-- Log bulk user creation
SELECT log_admin_action(
  'bulk_users_create',
  '550e8400-e29b-41d4-a716-446655440000',  -- admin UUID
  NULL,
  '{"created": 10, "role": "patient"}'::jsonb
);

-- Log synthetic data generation
SELECT log_admin_action(
  'synthetic_generate',
  '550e8400-e29b-41d4-a716-446655440000',
  NULL,
  '{"patients": 5, "checkins": 75, "pattern": "cycling"}'::jsonb
);

-- Log single user deletion
SELECT log_admin_action(
  'user_delete',
  '550e8400-e29b-41d4-a716-446655440000',
  '660e8400-e29b-41d4-a716-446655440000',  -- deleted user UUID
  '{"reason": "test_user", "hard_delete": true}'::jsonb
);
```

**Python (Supabase)**:
```python
audit_id = supabase.rpc('log_admin_action', {
    'p_action': 'synthetic_generate',
    'p_performed_by': admin_user_id,
    'p_user_id': None,
    'p_details': {
        'patients_created': 10,
        'therapists_created': 2,
        'environment': 'production'
    }
}).execute().data
```

---

## delete_test_users

**Purpose**: Hard delete test/synthetic users and all related data

**Signature**:
```sql
delete_test_users(
  p_dry_run boolean DEFAULT true,
  p_before_date timestamp with time zone DEFAULT NULL,
  p_limit integer DEFAULT NULL
) RETURNS jsonb
```

**⚠️ Important**: Does NOT delete `auth.users` - backend must handle that separately.

**Quick Examples**:

```sql
-- 1. Dry run (safe preview)
SELECT delete_test_users(p_dry_run := true);

-- 2. Delete all test users
SELECT delete_test_users(p_dry_run := false);

-- 3. Delete test users created before specific date
SELECT delete_test_users(
  p_dry_run := false,
  p_before_date := '2024-01-01T00:00:00+00:00'
);

-- 4. Delete up to 50 test users (safety limit)
SELECT delete_test_users(p_dry_run := false, p_limit := 50);

-- 5. Delete old test users with limit
SELECT delete_test_users(
  p_dry_run := false,
  p_before_date := '2024-11-01T00:00:00+00:00',
  p_limit := 100
);
```

**Python (Supabase)**:
```python
# Dry run first
result = supabase.rpc('delete_test_users', {
    'p_dry_run': True
}).execute()

print(f"Would delete {result.data['deleted_profiles']} profiles")
print(f"Would delete {result.data['deleted_check_ins']} check-ins")

# Actual deletion
if user_confirms:
    result = supabase.rpc('delete_test_users', {
        'p_dry_run': False,
        'p_limit': 50
    }).execute()
    
    # Also delete from auth.users
    for user_id in result.data.get('sample_user_ids', []):
        supabase.auth.admin.delete_user(user_id)
```

**Return Value**:
```json
{
  "dry_run": false,
  "deleted_profiles": 10,
  "deleted_check_ins": 150,
  "deleted_clinical_notes": 25,
  "deleted_crisis_plans": 8,
  "deleted_therapist_patients": 10,
  "sample_user_ids": ["uuid1", "uuid2", "uuid3", "uuid4", "uuid5"],
  "execution_time_ms": 245.67
}
```

---

## clear_database

**Purpose**: Wipe domain tables while respecting hard/soft delete rules

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

**⚠️ WARNING**: Destructive operation - use with extreme caution!

**Quick Examples**:

```sql
-- 1. Dry run (safe preview)
SELECT clear_database(p_dry_run := true);

-- 2. Clear all domain data + delete test users (common cleanup)
SELECT clear_database(
  p_dry_run := false,
  p_delete_test_users := true
);

-- 3. Clear domain data only, keep all profiles
SELECT clear_database(
  p_dry_run := false,
  p_clear_domain_data_only := true
);

-- 4. Full database wipe (test environment reset)
SELECT clear_database(
  p_dry_run := false,
  p_delete_test_users := true,
  p_soft_delete_normal_users := true,
  p_clear_audit_log := true
);

-- 5. Clear domain data but keep test users for reuse
SELECT clear_database(
  p_dry_run := false,
  p_delete_test_users := false,
  p_clear_domain_data_only := true
);
```

**Python (Supabase)**:
```python
# Dry run first
result = supabase.rpc('clear_database', {
    'p_dry_run': True
}).execute()

print(f"Would clear {result.data['cleared_check_ins']} check-ins")
print(f"Would delete {result.data['deleted_test_profiles']} test profiles")

# Actual clearing
if user_confirms:
    result = supabase.rpc('clear_database', {
        'p_dry_run': False,
        'p_delete_test_users': True,
        'p_clear_domain_data_only': False
    }).execute()
```

**Return Value**:
```json
{
  "dry_run": false,
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

---

## Common Patterns

### Pattern 1: Cleanup Test Data (Safest)

```sql
-- Step 1: Preview what will be deleted
SELECT delete_test_users(p_dry_run := true);

-- Step 2: Delete test users only
SELECT delete_test_users(p_dry_run := false);

-- Step 3: Log the operation
SELECT log_admin_action(
  'cleanup_test_users',
  'admin-uuid',
  NULL,
  '{"deleted": 10}'::jsonb
);
```

### Pattern 2: Test Environment Reset

```sql
-- Step 1: Preview
SELECT clear_database(p_dry_run := true);

-- Step 2: Full wipe
SELECT clear_database(
  p_dry_run := false,
  p_delete_test_users := true,
  p_soft_delete_normal_users := true,
  p_clear_audit_log := true
);

-- Step 3: Log
SELECT log_admin_action(
  'test_environment_reset',
  'admin-uuid',
  NULL,
  '{"environment": "staging"}'::jsonb
);
```

### Pattern 3: Clear Data, Keep Users

```sql
-- Clear all domain data but keep user profiles
SELECT clear_database(
  p_dry_run := false,
  p_clear_domain_data_only := true
);
```

### Pattern 4: Delete Old Test Users

```sql
-- Delete test users older than 30 days
SELECT delete_test_users(
  p_dry_run := false,
  p_before_date := (now() - interval '30 days')::timestamp,
  p_limit := 100
);
```

### Pattern 5: Complete Cleanup Workflow (Python)

```python
async def cleanup_test_data(supabase: Client, admin_user_id: str):
    """Complete cleanup workflow with safety checks."""
    
    # 1. Dry run to see what will be affected
    dry_run = supabase.rpc('delete_test_users', {
        'p_dry_run': True
    }).execute()
    
    profiles_to_delete = dry_run.data['deleted_profiles']
    
    if profiles_to_delete == 0:
        print("No test users to delete")
        return
    
    print(f"Will delete {profiles_to_delete} test users")
    
    # 2. Get user IDs before deletion (for auth.users cleanup)
    test_users = supabase.table('profiles')\
        .select('id')\
        .eq('is_test_patient', True)\
        .is_('deleted_at', 'null')\
        .execute()
    
    user_ids = [u['id'] for u in test_users.data]
    
    # 3. Delete from database
    result = supabase.rpc('delete_test_users', {
        'p_dry_run': False
    }).execute()
    
    # 4. Delete from auth.users
    deleted_auth_users = 0
    for user_id in user_ids:
        try:
            supabase.auth.admin.delete_user(user_id)
            deleted_auth_users += 1
        except Exception as e:
            print(f"Failed to delete auth user {user_id}: {e}")
    
    # 5. Log the operation
    supabase.rpc('log_admin_action', {
        'p_action': 'cleanup_test_users',
        'p_performed_by': admin_user_id,
        'p_user_id': None,
        'p_details': {
            'deleted_profiles': result.data['deleted_profiles'],
            'deleted_check_ins': result.data['deleted_check_ins'],
            'deleted_auth_users': deleted_auth_users,
            'execution_time_ms': result.data['execution_time_ms']
        }
    }).execute()
    
    return result.data
```

---

## Safety Checklist

Before running any destructive operation:

- [ ] Run with `p_dry_run := true` first
- [ ] Review the statistics returned
- [ ] Verify you're in the correct environment (dev/staging/prod)
- [ ] Confirm admin authorization
- [ ] Have a database backup (for production)
- [ ] Log the operation for audit trail
- [ ] For `delete_test_users`: Remember to also delete auth.users
- [ ] For `clear_database`: Double-check the parameters

---

## Error Handling

### Common Errors

**"Function does not exist"**
- Migration 009 not applied
- Wrong schema or function name
- Solution: Apply migration 009

**"Permission denied"**
- Not using service_role client
- User doesn't have admin role
- Solution: Use service_role or verify admin permissions

**"Foreign key violation"**
- Shouldn't happen - functions handle order correctly
- May indicate custom FK constraints
- Solution: Check schema for custom constraints

**"auth.users not deleted"**
- Expected behavior - by design
- Solution: Use Supabase Admin API to delete auth.users

---

## Performance Notes

- `delete_test_users`: O(n) where n = number of test users
- `clear_database`: O(n) where n = total rows in domain tables
- Both use batch operations for efficiency
- Execution time included in return value
- Large operations (>1000 users): Consider using `p_limit` parameter

---

## Related Documentation

- [DATABASE_ARCHITECTURE.md](./DATABASE_ARCHITECTURE.md) - Comprehensive architecture guide
- [Migration 009](../migrations/009_admin_rls_and_sql_functions.sql) - SQL source code
- [Migrations README](../migrations/README.md) - Migration documentation
