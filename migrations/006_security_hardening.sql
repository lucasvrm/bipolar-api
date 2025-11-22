-- Migration: Security Hardening - RLS and Search Path Fix
-- Description: Enables Row Level Security on audit_log and fixes search_path for database functions
-- Version: 006
-- Date: 2024-11-22

-- ============================================================================
-- 1. Enable Row Level Security on audit_log table
-- ============================================================================

-- Enable RLS on the audit_log table to prevent unauthorized access
ALTER TABLE public.audit_log ENABLE ROW LEVEL SECURITY;

-- ============================================================================
-- 2. Create RLS Policies for audit_log
-- ============================================================================

-- Drop existing policies if they exist (for idempotency)
DROP POLICY IF EXISTS "service_role_full_access" ON public.audit_log;
DROP POLICY IF EXISTS "users_read_own_audit_logs" ON public.audit_log;

-- Policy: Allow service_role to have full access to audit_log
-- This is needed for backend operations and admin functions
CREATE POLICY "service_role_full_access" ON public.audit_log
  FOR ALL
  TO service_role
  USING (true)
  WITH CHECK (true);

-- Policy: Allow authenticated users to view only their own audit logs
-- Users can SELECT their own audit logs via user_id
CREATE POLICY "users_read_own_audit_logs" ON public.audit_log
  FOR SELECT
  TO authenticated
  USING (auth.uid() = user_id);

-- Policy: Block INSERT/UPDATE/DELETE for anon and authenticated roles
-- Only service_role can modify audit_log entries
-- Note: This is implicitly handled by not creating policies for these operations
-- for anon and authenticated roles, but we make it explicit here with comments

-- ============================================================================
-- 3. Fix search_path for Functions to Prevent Hijacking
-- ============================================================================

-- Fix search_path for update_updated_at_column function
-- This prevents search path hijacking attacks
ALTER FUNCTION public.update_updated_at_column() SET search_path = public, extensions;

-- Fix search_path for handle_new_user function
-- This prevents search path hijacking attacks
ALTER FUNCTION public.handle_new_user() SET search_path = public, extensions;

-- ============================================================================
-- Comments for documentation
-- ============================================================================

COMMENT ON POLICY "service_role_full_access" ON public.audit_log IS 
  'Allows service_role (backend) full access to audit logs for system operations';

COMMENT ON POLICY "users_read_own_audit_logs" ON public.audit_log IS 
  'Allows authenticated users to read only their own audit log entries';
