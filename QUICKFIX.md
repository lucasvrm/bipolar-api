# Quick Fix Guide - API Infinite Recursion Error

## 🚨 Your API is down with "infinite recursion" errors

**Time to fix:** Less than 2 minutes  
**Difficulty:** Copy and paste into Supabase

---

## Step 1: Open Supabase SQL Editor

1. Go to [https://app.supabase.com](https://app.supabase.com)
2. Select your project (the one with URL matching your `SUPABASE_URL`)
3. Click on **SQL Editor** in the left sidebar (looks like `<>`)

---

## Step 2: Run Migration 010

1. Open the file `migrations/010_admin_security_definer_function.sql` in this repository
2. **Copy ALL its contents** (148 lines of SQL code)
3. **Paste** into the Supabase SQL Editor
4. Click the **RUN** button (or press Ctrl+Enter)

You should see success messages like:
```
NOTICE: ✓ Migration 010 completed successfully
NOTICE: ✓ SECURITY DEFINER function public.is_admin(uuid) created
...
```

---

## Step 3: Verify the Fix

### Option A: Test your API immediately
```bash
# Replace with your actual API URL
curl https://bipolar-engine.onrender.com/api/profile
```

Should return data instead of 500 error.

### Option B: Use the diagnostic script
```bash
# Set environment variables
export SUPABASE_URL="https://gtjthmovvfpaekjtlxov.supabase.co"
export SUPABASE_SERVICE_KEY="your-service-key-here"

# Run diagnostic
python tools/diagnose_rls_issue.py
```

---

## Step 4: Restart Your Backend (if needed)

If you're running the backend on Render:
1. Go to [https://dashboard.render.com](https://dashboard.render.com)
2. Find your service
3. Click **Manual Deploy** → **Deploy latest commit**

Or just wait - it should auto-recover within a minute once the database is fixed.

---

## What This Fix Does

Creates a special function `is_admin(user_id)` that:
- Safely checks if a user has admin role
- Uses `SECURITY DEFINER` to bypass RLS (preventing infinite loops)
- Replaces broken policies that caused the recursion

**Before (Broken):**
```sql
-- This caused infinite recursion
EXISTS (SELECT 1 FROM profiles WHERE id = auth.uid() AND role = 'admin')
```

**After (Fixed):**
```sql
-- This works correctly
public.is_admin(auth.uid())
```

---

## Troubleshooting

### Still seeing errors after running migration?

1. **Check Supabase logs:** Go to Logs → API in Supabase Dashboard
2. **Verify function exists:**
   ```sql
   SELECT proname, prosecdef FROM pg_proc WHERE proname = 'is_admin';
   ```
   Should return one row with `prosecdef = t`

3. **Check policies:**
   ```sql
   SELECT policyname, tablename 
   FROM pg_policies 
   WHERE policyname LIKE 'admin_full_access%';
   ```
   Should return 5 policies

### Error running the migration?

If you see "function already exists" or similar:
- This means migration 010 was already partially applied
- The policies might still be broken
- **Solution:** Delete the old policies first:
  ```sql
  DROP POLICY IF EXISTS "admin_full_access_profiles" ON public.profiles;
  DROP POLICY IF EXISTS "admin_full_access_check_ins" ON public.check_ins;
  DROP POLICY IF EXISTS "admin_full_access_clinical_notes" ON public.clinical_notes;
  DROP POLICY IF EXISTS "admin_full_access_crisis_plan" ON public.crisis_plan;
  DROP POLICY IF EXISTS "admin_full_access_therapist_patients" ON public.therapist_patients;
  ```
- Then re-run migration 010

---

## Need More Help?

- **Full documentation:** See [URGENT_FIX_INFINITE_RECURSION.md](URGENT_FIX_INFINITE_RECURSION.md)
- **Migration details:** See [migrations/README.md](migrations/README.md)
- **Check migration file:** [migrations/010_admin_security_definer_function.sql](migrations/010_admin_security_definer_function.sql)

---

## Prevention

To prevent this in the future:
- Always test migrations in a development/staging environment first
- Never query the same table from within its own RLS policies
- Use `SECURITY DEFINER` functions for role checks in RLS policies
