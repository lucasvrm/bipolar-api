-- Migration: Create audit log table for tracking account operations
-- Description: Tracks delete requests, cancellations, hard deletions, and data exports
-- Version: 002
-- Date: 2024-01-15

-- Create audit log table
CREATE TABLE IF NOT EXISTS public.audit_log (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id uuid NOT NULL,
  action text NOT NULL, -- 'delete_requested' | 'delete_cancelled' | 'hard_deleted' | 'export_requested'
  details jsonb,
  performed_by uuid, -- null if performed by the user themselves
  created_at timestamp with time zone DEFAULT now()
);

-- Create indexes for querying
CREATE INDEX IF NOT EXISTS idx_audit_log_user_id 
  ON public.audit_log(user_id);

CREATE INDEX IF NOT EXISTS idx_audit_log_action 
  ON public.audit_log(action);

CREATE INDEX IF NOT EXISTS idx_audit_log_created_at 
  ON public.audit_log(created_at DESC);

-- Add helpful comments
COMMENT ON TABLE public.audit_log IS 'Audit log for account deletion and data export operations';
COMMENT ON COLUMN public.audit_log.action IS 'Type of action: delete_requested, delete_cancelled, hard_deleted, export_requested';
COMMENT ON COLUMN public.audit_log.details IS 'Additional details about the action (JSON)';
COMMENT ON COLUMN public.audit_log.performed_by IS 'User ID of who performed the action (null if self-service)';
