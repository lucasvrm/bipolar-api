-- Migration: Ensure check_ins table has proper FK constraint with CASCADE delete
-- Description: Updates the foreign key constraint on check_ins.user_id to ensure
--              CASCADE delete behavior, so when a profile is deleted, all associated
--              check-ins are automatically removed.
-- 
-- This migration is idempotent and can be run multiple times safely.

-- Drop existing constraint if it exists (idempotent)
DO $$ 
BEGIN 
    IF EXISTS(
        SELECT 1 
        FROM pg_constraint 
        WHERE conname='check_ins_user_id_fkey'
    ) THEN 
        ALTER TABLE public.check_ins 
        DROP CONSTRAINT check_ins_user_id_fkey;
        
        RAISE NOTICE 'Dropped existing check_ins_user_id_fkey constraint';
    ELSE
        RAISE NOTICE 'Constraint check_ins_user_id_fkey does not exist, skipping drop';
    END IF;
END $$;

-- Add FK constraint with CASCADE delete
ALTER TABLE public.check_ins 
ADD CONSTRAINT check_ins_user_id_fkey 
FOREIGN KEY (user_id) 
REFERENCES public.profiles(id) 
ON DELETE CASCADE;

-- Verify constraint was created
DO $$
BEGIN
    IF EXISTS(
        SELECT 1 
        FROM pg_constraint 
        WHERE conname='check_ins_user_id_fkey'
    ) THEN
        RAISE NOTICE 'Successfully created check_ins_user_id_fkey constraint with CASCADE';
    ELSE
        RAISE EXCEPTION 'Failed to create check_ins_user_id_fkey constraint';
    END IF;
END $$;
