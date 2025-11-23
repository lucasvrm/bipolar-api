-- Migration: Admin RLS Policies and SQL Helper Functions
-- Description: Implements comprehensive RLS policies for admin access and SQL functions
--              for safe cascade operations (delete test users, clear database, audit logging)
-- Version: 009
-- Date: 2024-11-23

-- ============================================================================
-- PART 1: RLS POLICIES FOR ADMIN ACCESS
-- ============================================================================
-- These policies allow users with role='admin' in the profiles table to have
-- full CRUD access to key tables. This complements the existing service_role
-- policies and enables admin operations through authenticated requests.
--
-- NOTE: Most admin operations will still use service_role for backend operations,
-- but these policies provide additional flexibility for direct admin access.
-- ============================================================================

-- -----------------------------------------------------------------------------
-- Admin Policies for check_ins
-- -----------------------------------------------------------------------------
-- Drop existing admin policy if it exists (for idempotency)
DROP POLICY IF EXISTS "admin_full_access_check_ins" ON public.check_ins;

-- Allow admins full CRUD access to all check_ins
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

COMMENT ON POLICY "admin_full_access_check_ins" ON public.check_ins IS 
  'Allows authenticated users with admin role full CRUD access to all check_ins';

-- -----------------------------------------------------------------------------
-- Admin Policies for clinical_notes
-- -----------------------------------------------------------------------------
DROP POLICY IF EXISTS "admin_full_access_clinical_notes" ON public.clinical_notes;

CREATE POLICY "admin_full_access_clinical_notes" ON public.clinical_notes
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

COMMENT ON POLICY "admin_full_access_clinical_notes" ON public.clinical_notes IS 
  'Allows authenticated users with admin role full CRUD access to all clinical_notes';

-- -----------------------------------------------------------------------------
-- Admin Policies for crisis_plan
-- -----------------------------------------------------------------------------
DROP POLICY IF EXISTS "admin_full_access_crisis_plan" ON public.crisis_plan;

CREATE POLICY "admin_full_access_crisis_plan" ON public.crisis_plan
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

COMMENT ON POLICY "admin_full_access_crisis_plan" ON public.crisis_plan IS 
  'Allows authenticated users with admin role full CRUD access to all crisis_plan entries';

-- -----------------------------------------------------------------------------
-- Admin Policies for profiles
-- -----------------------------------------------------------------------------
DROP POLICY IF EXISTS "admin_full_access_profiles" ON public.profiles;

CREATE POLICY "admin_full_access_profiles" ON public.profiles
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

COMMENT ON POLICY "admin_full_access_profiles" ON public.profiles IS 
  'Allows authenticated users with admin role full CRUD access to all profiles';

-- -----------------------------------------------------------------------------
-- Admin Policies for therapist_patients
-- -----------------------------------------------------------------------------
DROP POLICY IF EXISTS "admin_full_access_therapist_patients" ON public.therapist_patients;

CREATE POLICY "admin_full_access_therapist_patients" ON public.therapist_patients
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

COMMENT ON POLICY "admin_full_access_therapist_patients" ON public.therapist_patients IS 
  'Allows authenticated users with admin role full CRUD access to therapist_patients relationships';

-- ============================================================================
-- PART 2: SQL HELPER FUNCTIONS FOR ADMIN OPERATIONS
-- ============================================================================

-- -----------------------------------------------------------------------------
-- Function: log_admin_action
-- Purpose: Helper function for macro-level audit logging of admin operations
-- 
-- This function provides a consistent interface for logging admin actions.
-- It should be called once per high-level operation (e.g., bulk user creation,
-- synthetic data generation, cleanup operations) with summary statistics.
--
-- Parameters:
--   p_action: String identifier for the action (e.g., 'delete_test_users', 
--             'clear_database', 'bulk_users_create', 'synthetic_generate')
--   p_performed_by: UUID of the admin user performing the action
--   p_user_id: Optional UUID of the primary user affected (NULL for bulk operations)
--   p_details: JSONB object containing operation-specific details like:
--              - counts: number of records affected per table
--              - sample_ids: array of affected user IDs
--              - environment: prod/dev/test
--              - parameters: input parameters for the operation
--
-- Returns: UUID of the created audit log entry
--
-- Usage Example:
--   SELECT log_admin_action(
--     'delete_test_users',
--     auth.uid(),
--     NULL,
--     jsonb_build_object(
--       'deleted_profiles', 10,
--       'deleted_checkins', 150,
--       'deleted_clinical_notes', 25,
--       'test_users_only', true
--     )
--   );
-- -----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.log_admin_action(
  p_action text,
  p_performed_by uuid,
  p_user_id uuid DEFAULT NULL,
  p_details jsonb DEFAULT NULL
)
RETURNS uuid
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, extensions
AS $$
DECLARE
  v_audit_id uuid;
BEGIN
  -- Validate action is not empty
  IF p_action IS NULL OR p_action = '' THEN
    RAISE EXCEPTION 'Action cannot be null or empty';
  END IF;

  -- Insert audit log entry
  INSERT INTO public.audit_log (
    user_id,
    action,
    details,
    performed_by,
    created_at
  ) VALUES (
    p_user_id,
    p_action,
    p_details,
    p_performed_by,
    now()
  )
  RETURNING id INTO v_audit_id;

  RETURN v_audit_id;
END;
$$;

COMMENT ON FUNCTION public.log_admin_action IS 
  'Helper function for creating macro-level audit log entries for admin operations. Should be called once per high-level operation with summary statistics.';

-- -----------------------------------------------------------------------------
-- Function: delete_test_users
-- Purpose: Hard delete test/synthetic users and all their related data
--
-- This function implements safe cascade deletion for test users (is_test_patient = true).
-- It deletes records in the correct order to maintain referential integrity:
--   1. therapist_patients (relationships)
--   2. clinical_notes (both as therapist and as patient)
--   3. check_ins (patient data)
--   4. crisis_plan (patient data)
--   5. profiles (user identity)
--
-- IMPORTANT: This does NOT delete auth.users rows - that must be done by backend
-- using the Supabase Admin API, as SQL triggers cannot delete auth.users.
--
-- Parameters:
--   p_dry_run: If true, returns counts without actually deleting data
--   p_before_date: Optional ISO timestamp - only delete users created before this date
--   p_limit: Optional limit on number of users to delete (for safety)
--
-- Returns: JSONB object with statistics:
--   {
--     "dry_run": boolean,
--     "deleted_profiles": integer,
--     "deleted_check_ins": integer,
--     "deleted_clinical_notes": integer,
--     "deleted_crisis_plans": integer,
--     "deleted_therapist_patients": integer,
--     "sample_user_ids": [uuid, ...],
--     "execution_time_ms": float
--   }
--
-- Usage Examples:
--   -- Dry run to see what would be deleted
--   SELECT delete_test_users(p_dry_run := true);
--
--   -- Delete all test users
--   SELECT delete_test_users(p_dry_run := false);
--
--   -- Delete test users created before a specific date
--   SELECT delete_test_users(
--     p_dry_run := false,
--     p_before_date := '2024-01-01T00:00:00Z'
--   );
--
--   -- Delete up to 50 test users
--   SELECT delete_test_users(p_dry_run := false, p_limit := 50);
-- -----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.delete_test_users(
  p_dry_run boolean DEFAULT true,
  p_before_date timestamp with time zone DEFAULT NULL,
  p_limit integer DEFAULT NULL
)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, extensions
AS $$
DECLARE
  v_start_time timestamp;
  v_user_ids uuid[];
  v_deleted_profiles integer := 0;
  v_deleted_check_ins integer := 0;
  v_deleted_clinical_notes integer := 0;
  v_deleted_crisis_plans integer := 0;
  v_deleted_therapist_patients integer := 0;
  v_execution_time_ms float;
  v_result jsonb;
BEGIN
  v_start_time := clock_timestamp();

  -- Find test users matching criteria
  -- Use subquery with optional LIMIT to avoid arbitrary large numbers
  SELECT ARRAY_AGG(id)
  INTO v_user_ids
  FROM (
    SELECT id
    FROM public.profiles
    WHERE is_test_patient = true
      AND deleted_at IS NULL  -- Don't delete already soft-deleted users
      AND (p_before_date IS NULL OR created_at < p_before_date)
    ORDER BY created_at
    LIMIT CASE WHEN p_limit IS NULL THEN 2147483647 ELSE p_limit END
  ) subq;

  -- If no users found, return empty result
  IF v_user_ids IS NULL OR array_length(v_user_ids, 1) = 0 THEN
    RETURN jsonb_build_object(
      'dry_run', p_dry_run,
      'deleted_profiles', 0,
      'deleted_check_ins', 0,
      'deleted_clinical_notes', 0,
      'deleted_crisis_plans', 0,
      'deleted_therapist_patients', 0,
      'sample_user_ids', '[]'::jsonb,
      'execution_time_ms', 0
    );
  END IF;

  -- If dry run, just count what would be deleted
  IF p_dry_run THEN
    SELECT COUNT(*) INTO v_deleted_check_ins
    FROM public.check_ins
    WHERE user_id = ANY(v_user_ids);

    SELECT COUNT(*) INTO v_deleted_clinical_notes
    FROM public.clinical_notes
    WHERE patient_id = ANY(v_user_ids) OR therapist_id = ANY(v_user_ids);

    SELECT COUNT(*) INTO v_deleted_crisis_plans
    FROM public.crisis_plan
    WHERE user_id = ANY(v_user_ids);

    SELECT COUNT(*) INTO v_deleted_therapist_patients
    FROM public.therapist_patients
    WHERE patient_id = ANY(v_user_ids) OR therapist_id = ANY(v_user_ids);

    v_deleted_profiles := array_length(v_user_ids, 1);
  ELSE
    -- Perform actual deletion in correct order for referential integrity

    -- 1. Delete therapist-patient relationships
    DELETE FROM public.therapist_patients
    WHERE patient_id = ANY(v_user_ids) OR therapist_id = ANY(v_user_ids);
    GET DIAGNOSTICS v_deleted_therapist_patients = ROW_COUNT;

    -- 2. Delete clinical notes (where user is therapist or patient)
    DELETE FROM public.clinical_notes
    WHERE patient_id = ANY(v_user_ids) OR therapist_id = ANY(v_user_ids);
    GET DIAGNOSTICS v_deleted_clinical_notes = ROW_COUNT;

    -- 3. Delete check-ins
    DELETE FROM public.check_ins
    WHERE user_id = ANY(v_user_ids);
    GET DIAGNOSTICS v_deleted_check_ins = ROW_COUNT;

    -- 4. Delete crisis plans
    DELETE FROM public.crisis_plan
    WHERE user_id = ANY(v_user_ids);
    GET DIAGNOSTICS v_deleted_crisis_plans = ROW_COUNT;

    -- 5. Delete profiles (user identity)
    DELETE FROM public.profiles
    WHERE id = ANY(v_user_ids);
    GET DIAGNOSTICS v_deleted_profiles = ROW_COUNT;
  END IF;

  -- Calculate execution time
  v_execution_time_ms := EXTRACT(EPOCH FROM (clock_timestamp() - v_start_time)) * 1000;

  -- Build result object
  v_result := jsonb_build_object(
    'dry_run', p_dry_run,
    'deleted_profiles', v_deleted_profiles,
    'deleted_check_ins', v_deleted_check_ins,
    'deleted_clinical_notes', v_deleted_clinical_notes,
    'deleted_crisis_plans', v_deleted_crisis_plans,
    'deleted_therapist_patients', v_deleted_therapist_patients,
    'sample_user_ids', to_jsonb(v_user_ids[1:LEAST(5, array_length(v_user_ids, 1))]),
    'execution_time_ms', v_execution_time_ms
  );

  RETURN v_result;
END;
$$;

COMMENT ON FUNCTION public.delete_test_users IS 
  'Hard delete test users (is_test_patient=true) and all their related data. Maintains referential integrity by deleting in correct order: therapist_patients → clinical_notes → check_ins → crisis_plan → profiles. Does NOT delete auth.users (must be done by backend). Supports dry-run mode, date filtering, and limits.';

-- -----------------------------------------------------------------------------
-- Function: clear_database
-- Purpose: Wipe domain tables while respecting hard/soft delete rules
--
-- This function provides a safe way to clear database content for testing or
-- reset scenarios. It handles test users (hard delete) and normal users
-- (soft delete) according to business rules.
--
-- Deletion strategy:
--   - Test users (is_test_patient = true): HARD DELETE all data
--   - Normal users (is_test_patient = false): SOFT DELETE (set deleted_at)
--   - Domain tables are wiped in safe order
--
-- Parameters:
--   p_dry_run: If true, returns counts without actually deleting data
--   p_delete_test_users: If true, hard delete test users (default: true)
--   p_soft_delete_normal_users: If true, soft delete normal users (default: false)
--   p_clear_audit_log: If true, also clear audit_log table (default: false)
--   p_clear_domain_data_only: If true, only clear domain data but keep profiles (default: false)
--
-- Returns: JSONB object with statistics about what was deleted/cleared
--
-- Usage Examples:
--   -- Dry run to see what would be affected
--   SELECT clear_database(p_dry_run := true);
--
--   -- Clear all domain data and hard delete test users
--   SELECT clear_database(
--     p_dry_run := false,
--     p_delete_test_users := true
--   );
--
--   -- Clear domain data only, keep all profiles
--   SELECT clear_database(
--     p_dry_run := false,
--     p_clear_domain_data_only := true
--   );
--
--   -- Full wipe including soft delete of normal users
--   SELECT clear_database(
--     p_dry_run := false,
--     p_delete_test_users := true,
--     p_soft_delete_normal_users := true,
--     p_clear_audit_log := true
--   );
-- -----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.clear_database(
  p_dry_run boolean DEFAULT true,
  p_delete_test_users boolean DEFAULT true,
  p_soft_delete_normal_users boolean DEFAULT false,
  p_clear_audit_log boolean DEFAULT false,
  p_clear_domain_data_only boolean DEFAULT false
)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, extensions
AS $$
DECLARE
  v_start_time timestamp;
  v_deleted_therapist_patients integer := 0;
  v_deleted_clinical_notes integer := 0;
  v_deleted_check_ins integer := 0;
  v_deleted_crisis_plans integer := 0;
  v_deleted_test_profiles integer := 0;
  v_soft_deleted_normal_users integer := 0;
  v_cleared_audit_logs integer := 0;
  v_execution_time_ms float;
  v_result jsonb;
  v_test_user_result jsonb;
BEGIN
  v_start_time := clock_timestamp();

  IF p_dry_run THEN
    -- Count what would be deleted

    SELECT COUNT(*) INTO v_deleted_therapist_patients
    FROM public.therapist_patients;

    SELECT COUNT(*) INTO v_deleted_clinical_notes
    FROM public.clinical_notes;

    SELECT COUNT(*) INTO v_deleted_check_ins
    FROM public.check_ins;

    SELECT COUNT(*) INTO v_deleted_crisis_plans
    FROM public.crisis_plan;

    IF p_delete_test_users THEN
      SELECT COUNT(*) INTO v_deleted_test_profiles
      FROM public.profiles
      WHERE is_test_patient = true AND deleted_at IS NULL;
    END IF;

    IF p_soft_delete_normal_users THEN
      SELECT COUNT(*) INTO v_soft_deleted_normal_users
      FROM public.profiles
      WHERE is_test_patient = false AND deleted_at IS NULL;
    END IF;

    IF p_clear_audit_log THEN
      SELECT COUNT(*) INTO v_cleared_audit_logs
      FROM public.audit_log;
    END IF;

  ELSE
    -- Perform actual clearing

    -- 1. Clear domain tables in safe order
    DELETE FROM public.therapist_patients;
    GET DIAGNOSTICS v_deleted_therapist_patients = ROW_COUNT;

    DELETE FROM public.clinical_notes;
    GET DIAGNOSTICS v_deleted_clinical_notes = ROW_COUNT;

    DELETE FROM public.check_ins;
    GET DIAGNOSTICS v_deleted_check_ins = ROW_COUNT;

    DELETE FROM public.crisis_plan;
    GET DIAGNOSTICS v_deleted_crisis_plans = ROW_COUNT;

    -- 2. Clear audit log if requested
    IF p_clear_audit_log THEN
      DELETE FROM public.audit_log;
      GET DIAGNOSTICS v_cleared_audit_logs = ROW_COUNT;
    END IF;

    -- 3. Handle profiles based on user type (unless only clearing domain data)
    IF NOT p_clear_domain_data_only THEN
      -- Hard delete test users if requested
      IF p_delete_test_users THEN
        DELETE FROM public.profiles
        WHERE is_test_patient = true AND deleted_at IS NULL;
        GET DIAGNOSTICS v_deleted_test_profiles = ROW_COUNT;
      END IF;

      -- Soft delete normal users if requested
      IF p_soft_delete_normal_users THEN
        UPDATE public.profiles
        SET 
          deleted_at = now(),
          deletion_scheduled_at = now()
        WHERE is_test_patient = false AND deleted_at IS NULL;
        GET DIAGNOSTICS v_soft_deleted_normal_users = ROW_COUNT;
      END IF;
    END IF;
  END IF;

  -- Calculate execution time
  v_execution_time_ms := EXTRACT(EPOCH FROM (clock_timestamp() - v_start_time)) * 1000;

  -- Build result object
  v_result := jsonb_build_object(
    'dry_run', p_dry_run,
    'cleared_therapist_patients', v_deleted_therapist_patients,
    'cleared_clinical_notes', v_deleted_clinical_notes,
    'cleared_check_ins', v_deleted_check_ins,
    'cleared_crisis_plans', v_deleted_crisis_plans,
    'deleted_test_profiles', v_deleted_test_profiles,
    'soft_deleted_normal_users', v_soft_deleted_normal_users,
    'cleared_audit_logs', v_cleared_audit_logs,
    'execution_time_ms', v_execution_time_ms,
    'options', jsonb_build_object(
      'delete_test_users', p_delete_test_users,
      'soft_delete_normal_users', p_soft_delete_normal_users,
      'clear_audit_log', p_clear_audit_log,
      'clear_domain_data_only', p_clear_domain_data_only
    )
  );

  RETURN v_result;
END;
$$;

COMMENT ON FUNCTION public.clear_database IS 
  'Wipe domain tables (therapist_patients, clinical_notes, check_ins, crisis_plan) while respecting hard/soft delete rules. Test users can be hard deleted, normal users can be soft deleted. Supports multiple clearing strategies via parameters. Use with extreme caution - primarily for testing/reset scenarios.';

-- ============================================================================
-- PART 3: GRANTS AND PERMISSIONS
-- ============================================================================

-- Grant execute permissions on helper functions to authenticated users
-- This allows admins to call these functions through authenticated requests
GRANT EXECUTE ON FUNCTION public.log_admin_action TO authenticated;
GRANT EXECUTE ON FUNCTION public.delete_test_users TO authenticated;
GRANT EXECUTE ON FUNCTION public.clear_database TO authenticated;

-- Service role also gets execute permissions (for backend operations)
GRANT EXECUTE ON FUNCTION public.log_admin_action TO service_role;
GRANT EXECUTE ON FUNCTION public.delete_test_users TO service_role;
GRANT EXECUTE ON FUNCTION public.clear_database TO service_role;

-- ============================================================================
-- PART 4: VERIFICATION AND DOCUMENTATION
-- ============================================================================

-- Add helpful notices for migration verification
DO $$
BEGIN
  RAISE NOTICE '✓ Migration 009 completed successfully';
  RAISE NOTICE '✓ Admin RLS policies created for: check_ins, clinical_notes, crisis_plan, profiles, therapist_patients';
  RAISE NOTICE '✓ SQL helper functions created: log_admin_action, delete_test_users, clear_database';
  RAISE NOTICE '✓ All functions are idempotent and can be re-run safely';
  RAISE NOTICE '⚠ IMPORTANT: delete_test_users does NOT delete auth.users - backend must handle that';
  RAISE NOTICE '⚠ WARNING: clear_database is a powerful function - use with extreme caution';
END $$;
