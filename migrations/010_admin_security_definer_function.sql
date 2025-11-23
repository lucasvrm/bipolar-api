-- Migration: Admin SECURITY DEFINER Function to Prevent RLS Infinite Recursion
-- Description: Creates a SECURITY DEFINER function to check admin status and updates
--              all admin RLS policies to use this function instead of subselects.
--              This prevents "infinite recursion detected in policy" errors.
-- Version: 010
-- Date: 2025-11-23

-- ============================================================================
-- PART 1: CREATE SECURITY DEFINER FUNCTION
-- ============================================================================
-- This function bypasses RLS when checking if a user is an admin.
-- By using SECURITY DEFINER, it runs with the privileges of the function owner,
-- not the caller, allowing it to read from profiles without triggering RLS recursion.
-- ============================================================================

CREATE OR REPLACE FUNCTION public.is_admin(user_id uuid)
RETURNS boolean
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, extensions
AS $$
DECLARE
  user_role text;
BEGIN
  -- If user_id is NULL, not an admin
  IF user_id IS NULL THEN
    RETURN false;
  END IF;

  -- Fetch role from profiles table (bypasses RLS due to SECURITY DEFINER)
  SELECT role INTO user_role
  FROM public.profiles
  WHERE id = user_id
    AND deleted_at IS NULL
  LIMIT 1;

  -- Return true if role is 'admin', false otherwise
  RETURN (user_role = 'admin');
END;
$$;

COMMENT ON FUNCTION public.is_admin IS 
  'SECURITY DEFINER function to check if a user has admin role. Prevents infinite recursion in RLS policies by bypassing RLS when checking admin status.';

-- ============================================================================
-- PART 2: RECREATE ADMIN RLS POLICIES USING is_admin()
-- ============================================================================
-- Drop and recreate all admin policies to use the new is_admin() function
-- instead of direct subselects on the profiles table.
-- ============================================================================

-- -----------------------------------------------------------------------------
-- Admin Policies for check_ins
-- -----------------------------------------------------------------------------
DROP POLICY IF EXISTS "admin_full_access_check_ins" ON public.check_ins;

CREATE POLICY "admin_full_access_check_ins" ON public.check_ins
  FOR ALL
  TO authenticated
  USING (public.is_admin(auth.uid()))
  WITH CHECK (public.is_admin(auth.uid()));

COMMENT ON POLICY "admin_full_access_check_ins" ON public.check_ins IS 
  'Allows authenticated users with admin role full CRUD access to all check_ins. Uses is_admin() to prevent RLS recursion.';

-- -----------------------------------------------------------------------------
-- Admin Policies for clinical_notes
-- -----------------------------------------------------------------------------
DROP POLICY IF EXISTS "admin_full_access_clinical_notes" ON public.clinical_notes;

CREATE POLICY "admin_full_access_clinical_notes" ON public.clinical_notes
  FOR ALL
  TO authenticated
  USING (public.is_admin(auth.uid()))
  WITH CHECK (public.is_admin(auth.uid()));

COMMENT ON POLICY "admin_full_access_clinical_notes" ON public.clinical_notes IS 
  'Allows authenticated users with admin role full CRUD access to all clinical_notes. Uses is_admin() to prevent RLS recursion.';

-- -----------------------------------------------------------------------------
-- Admin Policies for crisis_plan
-- -----------------------------------------------------------------------------
DROP POLICY IF EXISTS "admin_full_access_crisis_plan" ON public.crisis_plan;

CREATE POLICY "admin_full_access_crisis_plan" ON public.crisis_plan
  FOR ALL
  TO authenticated
  USING (public.is_admin(auth.uid()))
  WITH CHECK (public.is_admin(auth.uid()));

COMMENT ON POLICY "admin_full_access_crisis_plan" ON public.crisis_plan IS 
  'Allows authenticated users with admin role full CRUD access to all crisis_plan entries. Uses is_admin() to prevent RLS recursion.';

-- -----------------------------------------------------------------------------
-- Admin Policies for profiles
-- -----------------------------------------------------------------------------
DROP POLICY IF EXISTS "admin_full_access_profiles" ON public.profiles;

CREATE POLICY "admin_full_access_profiles" ON public.profiles
  FOR ALL
  TO authenticated
  USING (public.is_admin(auth.uid()))
  WITH CHECK (public.is_admin(auth.uid()));

COMMENT ON POLICY "admin_full_access_profiles" ON public.profiles IS 
  'Allows authenticated users with admin role full CRUD access to all profiles. Uses is_admin() to prevent RLS recursion.';

-- -----------------------------------------------------------------------------
-- Admin Policies for therapist_patients
-- -----------------------------------------------------------------------------
DROP POLICY IF EXISTS "admin_full_access_therapist_patients" ON public.therapist_patients;

CREATE POLICY "admin_full_access_therapist_patients" ON public.therapist_patients
  FOR ALL
  TO authenticated
  USING (public.is_admin(auth.uid()))
  WITH CHECK (public.is_admin(auth.uid()));

COMMENT ON POLICY "admin_full_access_therapist_patients" ON public.therapist_patients IS 
  'Allows authenticated users with admin role full CRUD access to therapist_patients relationships. Uses is_admin() to prevent RLS recursion.';

-- ============================================================================
-- PART 3: GRANTS AND PERMISSIONS
-- ============================================================================

-- Grant execute permissions to authenticated users (allows policy checks)
GRANT EXECUTE ON FUNCTION public.is_admin TO authenticated;

-- Service role also gets execute permissions
GRANT EXECUTE ON FUNCTION public.is_admin TO service_role;

-- Anonymous role needs execute to allow policy evaluation during auth
GRANT EXECUTE ON FUNCTION public.is_admin TO anon;

-- ============================================================================
-- PART 4: VERIFICATION AND DOCUMENTATION
-- ============================================================================

DO $$
BEGIN
  RAISE NOTICE '✓ Migration 010 completed successfully';
  RAISE NOTICE '✓ SECURITY DEFINER function public.is_admin(uuid) created';
  RAISE NOTICE '✓ Admin RLS policies updated for: check_ins, clinical_notes, crisis_plan, profiles, therapist_patients';
  RAISE NOTICE '✓ All policies now use public.is_admin(auth.uid()) to prevent infinite recursion';
  RAISE NOTICE '✓ Function permissions granted to authenticated, service_role, and anon';
  RAISE NOTICE 'ℹ This migration resolves potential "infinite recursion detected in policy" errors';
END $$;
