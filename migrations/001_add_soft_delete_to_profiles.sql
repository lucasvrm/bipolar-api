-- Migration: Add soft delete and account deletion scheduling fields to profiles table
-- Description: Adds fields for soft scheduling, hard delete tracking, and deletion tokens
-- Version: 001
-- Date: 2024-01-15

-- Add soft scheduling and hard delete fields to profiles table
ALTER TABLE public.profiles
ADD COLUMN IF NOT EXISTS deletion_scheduled_at timestamp with time zone,
ADD COLUMN IF NOT EXISTS deleted_at timestamp with time zone,
ADD COLUMN IF NOT EXISTS deletion_token uuid DEFAULT gen_random_uuid();

-- Create indexes for performance
CREATE INDEX IF NOT EXISTS idx_profiles_deletion_scheduled_at 
  ON public.profiles(deletion_scheduled_at) WHERE deletion_scheduled_at IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_profiles_deleted_at 
  ON public.profiles(deleted_at);

-- Add helpful comments
COMMENT ON COLUMN public.profiles.deletion_scheduled_at IS 'Timestamp when account deletion was scheduled (14 days grace period)';
COMMENT ON COLUMN public.profiles.deleted_at IS 'Timestamp when account was hard deleted';
COMMENT ON COLUMN public.profiles.deletion_token IS 'Unique token for canceling deletion request';
