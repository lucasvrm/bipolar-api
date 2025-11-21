-- Migration: Add is_test_patient column to profiles table
-- Description: Adds boolean flag to identify synthetic/test patients for easier filtering
-- Version: 004
-- Date: 2024-11-21

-- Add is_test_patient column to profiles table
ALTER TABLE public.profiles
ADD COLUMN IF NOT EXISTS is_test_patient BOOLEAN DEFAULT FALSE;

-- Create index for performance when filtering synthetic vs real patients
CREATE INDEX IF NOT EXISTS idx_profiles_is_test_patient 
  ON public.profiles(is_test_patient);

-- Add helpful comment
COMMENT ON COLUMN public.profiles.is_test_patient IS 'Flag to identify synthetic/test patients (true) vs real patients (false)';
