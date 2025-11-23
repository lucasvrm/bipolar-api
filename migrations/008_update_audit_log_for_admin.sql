-- Migration: Update audit_log table for admin operations
-- Description: Make user_id nullable and update comments for broader admin usage
-- Version: 008
-- Date: 2024-11-23

-- Make user_id nullable (some admin actions like cleanup don't target specific users)
ALTER TABLE public.audit_log
ALTER COLUMN user_id DROP NOT NULL;

-- Update comments to reflect expanded usage
COMMENT ON TABLE public.audit_log IS 'Audit log for admin operations including user creation, data generation, cleanup, and account operations';
COMMENT ON COLUMN public.audit_log.action IS 'Type of action: user_create, synthetic_generate, cleanup, delete_requested, delete_cancelled, hard_deleted, export_requested, etc.';
COMMENT ON COLUMN public.audit_log.user_id IS 'User ID affected by the action (nullable for bulk operations)';
