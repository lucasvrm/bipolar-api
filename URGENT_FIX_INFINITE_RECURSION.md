# URGENT: Fix API Infinite Recursion Error

## Problem
Your API is failing with the following error:
```
infinite recursion detected in policy for relation "profiles"
```

This is causing all API endpoints to return 500 errors and preventing the application from working.

## Root Cause
The Supabase database has RLS (Row Level Security) policies that check admin status by querying the `profiles` table. However, when a policy on the `profiles` table itself queries `profiles`, it creates an infinite loop.

This bug was introduced in **migration 009** (`009_admin_rls_and_sql_functions.sql`).

## Solution
**Migration 010** (`010_admin_security_definer_function.sql`) contains the fix for this issue.

### What Migration 010 Does:
1. Creates a `SECURITY DEFINER` function called `is_admin()` that safely checks admin status without triggering RLS
2. Updates all admin RLS policies to use this function instead of direct queries
3. Prevents the infinite recursion by bypassing RLS when checking admin status

## How to Fix (URGENT - Run Immediately)

### Option 1: Supabase Dashboard (Recommended)
1. Go to your Supabase project: https://app.supabase.com
2. Navigate to **SQL Editor**
3. Copy the contents of `migrations/010_admin_security_definer_function.sql`
4. Paste into the SQL Editor
5. Click **Run** to execute the migration
6. Verify the fix by checking your API logs - errors should stop

### Option 2: Using psql
```bash
# Connect to your Supabase database
psql "postgresql://postgres:[YOUR-PASSWORD]@[YOUR-PROJECT-REF].supabase.co:5432/postgres"

# Run the migration
\i migrations/010_admin_security_definer_function.sql

# Exit
\q
```

### Option 3: Supabase CLI
```bash
# If you have the Supabase CLI installed
supabase db push
```

## Verification

After applying the migration, verify that the fix worked:

1. **Check the function exists:**
```sql
SELECT proname, prosecdef 
FROM pg_proc 
WHERE proname = 'is_admin';
```
Expected output: One row with `prosecdef = true`

2. **Test the API:**
```bash
# Replace with your actual endpoint
curl https://bipolar-engine.onrender.com/api/profile
```
Should return data instead of 500 error.

3. **Check Supabase logs:**
   - Go to Supabase Dashboard → Logs → API
   - Should no longer see "infinite recursion" errors

## What Changed

### Before (Broken):
```sql
CREATE POLICY "admin_full_access_profiles" ON public.profiles
  USING (
    EXISTS (
      SELECT 1 FROM public.profiles  -- ❌ INFINITE RECURSION
      WHERE id = auth.uid() AND role = 'admin'
    )
  );
```

### After (Fixed):
```sql
-- Function that bypasses RLS
CREATE FUNCTION public.is_admin(user_id uuid)
RETURNS boolean
SECURITY DEFINER  -- ✅ Bypasses RLS
AS $$
BEGIN
  RETURN EXISTS (
    SELECT 1 FROM public.profiles 
    WHERE id = user_id AND role = 'admin'
  );
END;
$$;

-- Policy uses the function
CREATE POLICY "admin_full_access_profiles" ON public.profiles
  USING (public.is_admin(auth.uid()));  -- ✅ NO RECURSION
```

## If You Haven't Applied Migration 009 Yet

If you have NOT applied migration 009 to your production database:
1. **SKIP migration 009** - Do not apply it
2. Apply migration 010 directly (it includes the corrected policies)
3. Your API will work correctly

## If You Have Applied Migration 009

If migration 009 is already in your database:
1. **IMMEDIATELY apply migration 010** to fix the issue
2. This will replace the broken policies with working ones
3. Your API will start working again

## Support

If you continue to see errors after applying migration 010:
1. Check the Supabase logs for the specific error
2. Verify that the `is_admin()` function exists in your database
3. Check that all policies are using `public.is_admin(auth.uid())`

## Timeline

- **Migration 009** (2024-11-23): Introduced the bug
- **Migration 010** (2025-11-23): Fixed the bug
- **This document**: Created to help you fix production issues ASAP

---

**TL;DR: Run migration 010 in your Supabase SQL Editor right now to fix the API.**
