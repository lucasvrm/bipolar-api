-- Migration: Add source column to profiles table
-- Description: Adds source field to distinguish between manual, synthetic, and real users
-- Version: 007
-- Date: 2024-11-23

-- Add source column to profiles table (idempotent)
DO $$ 
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_schema = 'public' 
        AND table_name = 'profiles' 
        AND column_name = 'source'
    ) THEN
        ALTER TABLE public.profiles
        ADD COLUMN source text DEFAULT 'unknown';
    END IF;
END $$;

-- Create index for performance when filtering by source
CREATE INDEX IF NOT EXISTS idx_profiles_source 
  ON public.profiles(source);

-- Add helpful comment
COMMENT ON COLUMN public.profiles.source IS 'Source of user creation: admin_manual, synthetic, signup, or unknown';

-- Update existing test patients to have source='synthetic'
UPDATE public.profiles
SET source = 'synthetic'
WHERE is_test_patient = TRUE AND (source = 'unknown' OR source IS NULL);

-- Update remaining unknown to 'signup' (assumed real users)
UPDATE public.profiles
SET source = 'signup'
WHERE source = 'unknown' OR source IS NULL;
