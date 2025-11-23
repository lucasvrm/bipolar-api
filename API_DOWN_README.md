# 🚨 ATTENTION: Your API is Currently Down

## The Problem
Your Bipolar API is returning **500 Internal Server Error** on all endpoints because of an infinite recursion bug in your Supabase database.

## The Solution
**Migration 010 needs to be applied to your Supabase database.**

This is a database issue, NOT a code issue. The fix already exists in this repository.

---

## ⚡ QUICK FIX (2 minutes)

### Step 1: Open Supabase
1. Go to [https://app.supabase.com](https://app.supabase.com)
2. Select your project
3. Click **SQL Editor** in the left sidebar

### Step 2: Apply the Fix
1. Open this file: [`migrations/010_admin_security_definer_function.sql`](migrations/010_admin_security_definer_function.sql)
2. **Copy ALL 148 lines**
3. **Paste** into Supabase SQL Editor
4. Click **RUN** (or press Ctrl+Enter)

### Step 3: Verify
Your API should work immediately. Test with:
```bash
curl https://bipolar-engine.onrender.com/api/profile
```

Or use our diagnostic tool:
```bash
export SUPABASE_URL="https://gtjthmovvfpaekjtlxov.supabase.co"
export SUPABASE_SERVICE_KEY="your-service-key"
python tools/diagnose_rls_issue.py
```

---

## 📚 Documentation

We've created comprehensive documentation to help you:

| Document | Purpose |
|----------|---------|
| **[QUICKFIX.md](QUICKFIX.md)** | Step-by-step fix guide (2 minutes) |
| **[URGENT_FIX_INFINITE_RECURSION.md](URGENT_FIX_INFINITE_RECURSION.md)** | Detailed explanation and troubleshooting |
| **[FIX_SUMMARY.md](FIX_SUMMARY.md)** | Complete technical analysis |
| **[migrations/README.md](migrations/README.md)** | Migration order and details |

## 🔧 Diagnostic Tools

We've created tools to help diagnose and verify the fix:

| Tool | Purpose |
|------|---------|
| **[tools/diagnose_rls_issue.py](tools/diagnose_rls_issue.py)** | Python script to detect the issue |
| **[tools/verify_rls_fix.sh](tools/verify_rls_fix.sh)** | Bash script to verify the fix |

---

## 🤔 What Caused This?

**Migration 009** created database policies that caused infinite recursion:
```sql
-- BROKEN CODE (Migration 009)
CREATE POLICY "admin_full_access_profiles" ON profiles
  USING (
    EXISTS (
      SELECT 1 FROM profiles  -- ❌ Queries profiles from within profiles policy
      WHERE id = auth.uid() AND role = 'admin'
    )
  );
```

**Migration 010** fixes it with a SECURITY DEFINER function:
```sql
-- FIXED CODE (Migration 010)
CREATE FUNCTION is_admin(user_id uuid) 
RETURNS boolean
SECURITY DEFINER  -- ✅ Bypasses RLS, no recursion
AS $$
BEGIN
  RETURN EXISTS (
    SELECT 1 FROM profiles WHERE id = user_id AND role = 'admin'
  );
END;
$$;

-- New policy uses the function
CREATE POLICY "admin_full_access_profiles" ON profiles
  USING (is_admin(auth.uid()));  -- ✅ Works correctly
```

---

## 📊 Current Status

### Before Applying Migration 010
- ❌ All API endpoints return 500 errors
- ❌ Error: "infinite recursion detected in policy for relation 'profiles'"
- ❌ Frontend cannot load any data
- ❌ Application completely non-functional

### After Applying Migration 010
- ✅ All API endpoints work correctly
- ✅ No more recursion errors
- ✅ Frontend loads data normally
- ✅ Application fully functional

---

## ⏱️ Timeline

- **Nov 23, 2024** - Migration 009 applied (introduced bug)
- **Nov 23, 2024** - Migration 010 created (contains fix)
- **Nov 23, 2024 21:20 UTC** - You reported API failures
- **Now** - Apply migration 010 to fix immediately

---

## 🆘 Need Help?

### Still seeing errors after applying the fix?
1. Check that the function was created:
   ```sql
   SELECT proname, prosecdef FROM pg_proc WHERE proname = 'is_admin';
   ```
   Should return one row with `prosecdef = t`

2. Check Supabase logs (Dashboard → Logs → API)

3. Try the diagnostic script:
   ```bash
   python tools/diagnose_rls_issue.py
   ```

### Can't access Supabase?
Contact your team member who has access to the Supabase dashboard.

### Error applying the migration?
See [URGENT_FIX_INFINITE_RECURSION.md](URGENT_FIX_INFINITE_RECURSION.md) troubleshooting section.

---

## 🎯 Summary

**Problem:** Database RLS policies have infinite recursion  
**Solution:** Apply migration 010  
**Time:** 2 minutes  
**Impact:** Immediate recovery  

**GO TO:** [migrations/010_admin_security_definer_function.sql](migrations/010_admin_security_definer_function.sql)

---

*This issue is a deployment/database configuration issue, not a code bug. The fix already exists in the repository and just needs to be applied to your Supabase database.*
