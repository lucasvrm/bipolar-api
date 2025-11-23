-- Migration: Add source column to profiles table
-- Description: Adds source field to distinguish between manual, synthetic, and real users
-- Version: 007
-- Date: 2024-11-23

-- Add source column to profiles table
ALTER TABLE public.profiles
ADD COLUMN IF NOT EXISTS source text DEFAULT 'unknown';

-- Create index for performance when filtering by source
CREATE INDEX IF NOT EXISTS idx_profiles_source 
  ON public.profiles(source);

-- Add helpful comment
COMMENT ON COLUMN public.profiles.source IS 'Source of user creation: admin_manual, synthetic, signup, or unknown';

-- Update existing test patients to have source='synthetic'
UPDATE public.profiles
SET source = 'synthetic'
WHERE is_test_patient = TRUE AND source = 'unknown';

-- Update remaining unknown to 'signup' (assumed real users)
UPDATE public.profiles
SET source = 'signup'
WHERE source = 'unknown';
