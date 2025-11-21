-- Migration: Create missing tables referenced in requirements
-- Description: Creates therapist_patients, crisis_plan, and clinical_notes tables if they don't exist
-- Version: 003
-- Date: 2024-01-15

-- Create therapist_patients relationship table
CREATE TABLE IF NOT EXISTS public.therapist_patients (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  therapist_id uuid NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,
  patient_id uuid NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,
  created_at timestamp with time zone DEFAULT now(),
  status text DEFAULT 'active', -- 'active' | 'transferred' | 'inactive'
  UNIQUE(therapist_id, patient_id)
);

-- Create crisis plan table
CREATE TABLE IF NOT EXISTS public.crisis_plan (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id uuid NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,
  warning_signs jsonb,
  coping_strategies jsonb,
  emergency_contacts jsonb,
  created_at timestamp with time zone DEFAULT now(),
  updated_at timestamp with time zone DEFAULT now()
);

-- Create clinical notes table
CREATE TABLE IF NOT EXISTS public.clinical_notes (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  patient_id uuid NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,
  therapist_id uuid NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,
  note_text text NOT NULL,
  session_date timestamp with time zone NOT NULL,
  created_at timestamp with time zone DEFAULT now(),
  updated_at timestamp with time zone DEFAULT now()
);

-- Create indexes
CREATE INDEX IF NOT EXISTS idx_therapist_patients_therapist 
  ON public.therapist_patients(therapist_id);

CREATE INDEX IF NOT EXISTS idx_therapist_patients_patient 
  ON public.therapist_patients(patient_id);

CREATE INDEX IF NOT EXISTS idx_crisis_plan_user 
  ON public.crisis_plan(user_id);

CREATE INDEX IF NOT EXISTS idx_clinical_notes_patient 
  ON public.clinical_notes(patient_id);

CREATE INDEX IF NOT EXISTS idx_clinical_notes_therapist 
  ON public.clinical_notes(therapist_id);

-- Add helpful comments
COMMENT ON TABLE public.therapist_patients IS 'Relationship table linking therapists to their patients';
COMMENT ON TABLE public.crisis_plan IS 'Crisis intervention plans for users';
COMMENT ON TABLE public.clinical_notes IS 'Clinical notes from therapy sessions';
