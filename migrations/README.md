# Database Migrations

## 🚨 CRITICAL: Infinite Recursion Error

**If your API is failing with "infinite recursion detected in policy for relation 'profiles'":**

**IMMEDIATE ACTION REQUIRED:** Go to your Supabase SQL Editor and run `010_admin_security_definer_function.sql`

See [URGENT_FIX_INFINITE_RECURSION.md](../URGENT_FIX_INFINITE_RECURSION.md) for detailed instructions.

---

This directory contains SQL migration files for the account deletion and data management features.

## Migration Order

These migrations must be executed in the following order:

1. **001_add_soft_delete_to_profiles.sql** - Adds soft delete fields to profiles table
2. **002_create_audit_log_table.sql** - Creates audit log table for tracking operations
3. **003_create_missing_tables.sql** - Creates therapist_patients, crisis_plan, and clinical_notes tables
4. **004_add_is_test_patient_column.sql** - Adds is_test_patient column
5. **005_ensure_check_ins_fk_cascade.sql** - Ensures foreign key cascade for check_ins
6. **006_security_hardening.sql** - Enables RLS on audit_log and fixes function search_path security
7. **007_add_source_column_to_profiles.sql** - Adds source column to distinguish user creation methods
8. **008_update_audit_log_for_admin.sql** - Makes user_id nullable for bulk admin operations
9. **009_admin_rls_and_sql_functions.sql** - Adds admin RLS policies and SQL helper functions for safe operations
10. **010_admin_security_definer_function.sql** - **CRITICAL FIX** - Fixes infinite recursion in admin RLS policies

## Running Migrations

### Option 1: Supabase Dashboard
1. Go to your Supabase project dashboard
2. Navigate to SQL Editor
3. Copy and paste each migration file in order
4. Execute each migration

### Option 2: Supabase CLI
```bash
# Apply migrations in order
supabase db push

# Or manually execute each file
psql $DATABASE_URL -f migrations/001_add_soft_delete_to_profiles.sql
psql $DATABASE_URL -f migrations/002_create_audit_log_table.sql
psql $DATABASE_URL -f migrations/003_create_missing_tables.sql
psql $DATABASE_URL -f migrations/004_add_is_test_patient_column.sql
psql $DATABASE_URL -f migrations/005_ensure_check_ins_fk_cascade.sql
psql $DATABASE_URL -f migrations/006_security_hardening.sql
psql $DATABASE_URL -f migrations/007_add_source_column_to_profiles.sql
psql $DATABASE_URL -f migrations/008_update_audit_log_for_admin.sql
psql $DATABASE_URL -f migrations/009_admin_rls_and_sql_functions.sql
psql $DATABASE_URL -f migrations/010_admin_security_definer_function.sql
```

## Verification

After running migrations, verify the schema:

```sql
-- Check profiles table structure
\d profiles

-- Check audit_log table
\d audit_log

-- Verify indexes
SELECT indexname, tablename FROM pg_indexes 
WHERE tablename IN ('profiles', 'audit_log', 'therapist_patients', 'crisis_plan', 'clinical_notes');

-- Test query with filters
EXPLAIN ANALYZE 
SELECT * FROM profiles 
WHERE deleted_at IS NULL 
  AND (deletion_scheduled_at IS NULL OR deletion_scheduled_at > now());
```

## Migration 009: Admin RLS and SQL Functions

This migration adds comprehensive database-level support for admin operations:

### RLS Policies for Admin Access

Admin RLS policies allow authenticated users with `role='admin'` in the profiles table to have full CRUD access to:
- `check_ins` - All patient check-in data
- `clinical_notes` - All clinical notes (therapist and patient perspectives)
- `crisis_plan` - All crisis intervention plans
- `profiles` - All user profiles
- `therapist_patients` - All therapist-patient relationships

These policies complement the existing `service_role` policies and enable admin operations through authenticated requests.

**IMPORTANT:** Migration 009 introduced a critical bug (infinite recursion) which is fixed by Migration 010.

## Migration 010: Fix RLS Infinite Recursion (CRITICAL)

This migration fixes a critical bug introduced in Migration 009 that caused API calls to fail with:
```
infinite recursion detected in policy for relation "profiles"
```

### Problem
The admin RLS policies in Migration 009 had infinite recursion because they queried the `profiles` table from within policies on the `profiles` table itself:

```sql
-- BUGGY CODE (from migration 009)
CREATE POLICY "admin_full_access_profiles" ON public.profiles
  USING (
    EXISTS (
      SELECT 1 FROM public.profiles  -- This causes infinite recursion!
      WHERE id = auth.uid() AND role = 'admin'
    )
  );
```

When checking access to `profiles`, the policy would trigger, which would query `profiles`, which would trigger the policy again, creating an infinite loop.

### Solution
Migration 011 creates a `SECURITY DEFINER` function that bypasses RLS to safely check admin status:

```sql
CREATE FUNCTION public.is_admin(user_id uuid)
RETURNS boolean
SECURITY DEFINER  -- Bypasses RLS
AS $$
BEGIN
  RETURN EXISTS (
    SELECT 1 FROM public.profiles 
    WHERE id = user_id AND role = 'admin'
  );
END;
$$;
```

All admin policies are then updated to use this function instead of direct queries:

```sql
CREATE POLICY "admin_full_access_profiles" ON public.profiles
  USING (public.is_admin(auth.uid()))  -- No more recursion!
  WITH CHECK (public.is_admin(auth.uid()));
```

### Impact
- **Before Migration 010:** All API calls to `/api/profile`, `/data/latest_checkin`, etc. fail with 500 errors
- **After Migration 010:** API calls work correctly, admin policies function as intended

**This migration (010) must be applied immediately if Migration 009 has been applied.**

## SQL Helper Functions

#### 1. `log_admin_action(action, performed_by, user_id, details)`

Helper function for macro-level audit logging of admin operations.

**Parameters:**
- `p_action` (text): Action identifier (e.g., 'delete_test_users', 'synthetic_generate')
- `p_performed_by` (uuid): Admin user's UUID
- `p_user_id` (uuid, optional): Primary affected user (NULL for bulk operations)
- `p_details` (jsonb, optional): Operation details (counts, parameters, etc.)

**Returns:** UUID of created audit log entry

**Example:**
```sql
SELECT log_admin_action(
  'delete_test_users',
  'admin-uuid-here',
  NULL,
  jsonb_build_object(
    'deleted_profiles', 10,
    'deleted_checkins', 150,
    'test_users_only', true
  )
);
```

#### 2. `delete_test_users(dry_run, before_date, limit)`

Hard delete test/synthetic users and all their related data in the correct order to maintain referential integrity.

**Deletion Order:**
1. therapist_patients (relationships)
2. clinical_notes (notes where user is therapist or patient)
3. check_ins (patient check-in data)
4. crisis_plan (patient crisis plans)
5. profiles (user identity)

**Parameters:**
- `p_dry_run` (boolean, default: true): If true, returns counts without deleting
- `p_before_date` (timestamp, optional): Only delete users created before this date
- `p_limit` (integer, optional): Maximum number of users to delete

**Returns:** JSONB with statistics (deleted counts per table, sample IDs, execution time)

**Important:** This function does NOT delete `auth.users` rows - that must be done by the backend using Supabase Admin API.

**Examples:**
```sql
-- Dry run to see what would be deleted
SELECT delete_test_users(p_dry_run := true);

-- Delete all test users
SELECT delete_test_users(p_dry_run := false);

-- Delete test users created before Jan 1, 2024
SELECT delete_test_users(
  p_dry_run := false,
  p_before_date := '2024-01-01T00:00:00+00:00'
);

-- Delete up to 50 test users
SELECT delete_test_users(p_dry_run := false, p_limit := 50);
```

#### 3. `clear_database(dry_run, delete_test_users, soft_delete_normal_users, clear_audit_log, clear_domain_data_only)`

Wipe domain tables while respecting hard/soft delete rules. Use with extreme caution - primarily for testing/reset scenarios.

**Deletion Strategy:**
- Test users (`is_test_patient = true`): HARD DELETE all data
- Normal users (`is_test_patient = false`): SOFT DELETE (set `deleted_at`)
- Domain tables wiped: therapist_patients, clinical_notes, check_ins, crisis_plan

**Parameters:**
- `p_dry_run` (boolean, default: true): If true, returns counts without deleting
- `p_delete_test_users` (boolean, default: true): Hard delete test users
- `p_soft_delete_normal_users` (boolean, default: false): Soft delete normal users
- `p_clear_audit_log` (boolean, default: false): Also clear audit_log table
- `p_clear_domain_data_only` (boolean, default: false): Only clear domain data, keep profiles

**Returns:** JSONB with statistics about what was deleted/cleared

**Examples:**
```sql
-- Dry run to see what would be affected
SELECT clear_database(p_dry_run := true);

-- Clear all domain data and hard delete test users
SELECT clear_database(
  p_dry_run := false,
  p_delete_test_users := true
);

-- Clear domain data only, keep all profiles
SELECT clear_database(
  p_dry_run := false,
  p_clear_domain_data_only := true
);

-- Full wipe including soft delete of normal users
SELECT clear_database(
  p_dry_run := false,
  p_delete_test_users := true,
  p_soft_delete_normal_users := true,
  p_clear_audit_log := true
);
```

### Security Considerations

- All functions use `SECURITY DEFINER` to run with elevated privileges
- All functions set `search_path = public, extensions` to prevent injection attacks
- Admin RLS policies check `role='admin'` in profiles table
- Functions are granted to both `authenticated` and `service_role`
- All operations respect referential integrity constraints

## Notes

- All migrations use `IF NOT EXISTS` clauses to be idempotent
- Indexes are created for optimal query performance
- Foreign key constraints ensure referential integrity
- Cascading deletes are configured for cleanup
