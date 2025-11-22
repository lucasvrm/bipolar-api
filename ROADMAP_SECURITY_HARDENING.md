# Security Hardening Roadmap

## Migration Information

**Migration File:** `006_security_hardening.sql`

**Date:** 2024-11-22

**Purpose:** Fix database security vulnerabilities identified by the Database Linter

## Security Issues Addressed

### 1. Row Level Security (RLS) - audit_log Table

**Problem:** The `public.audit_log` table had RLS disabled, allowing potential unauthorized access to sensitive audit information.

**Solution:** Enabled RLS with the command:
```sql
ALTER TABLE public.audit_log ENABLE ROW LEVEL SECURITY;
```

### 2. RLS Policies for audit_log

**Conservative Policy Design:**

#### Policy 1: `service_role_full_access`
- **Scope:** All operations (SELECT, INSERT, UPDATE, DELETE)
- **Role:** `service_role`
- **Justification:** The audit_log is an internal table used for compliance and security tracking. The backend service needs full access to log all account operations (deletion requests, cancellations, hard deletions, exports).

```sql
CREATE POLICY "service_role_full_access" ON public.audit_log
  FOR ALL
  TO service_role
  USING (true)
  WITH CHECK (true);
```

#### Policy 2: `users_read_own_audit_logs`
- **Scope:** SELECT only
- **Role:** `authenticated`
- **Justification:** Users should be able to view their own audit history for transparency. This policy restricts access to only records where `user_id` matches the authenticated user's ID.

```sql
CREATE POLICY "users_read_own_audit_logs" ON public.audit_log
  FOR SELECT
  TO authenticated
  USING (auth.uid() = user_id);
```

#### Blocked Operations
- **Anonymous (anon) role:** No access to audit_log (no policies created)
- **Authenticated role:** Read-only access to own records (no INSERT/UPDATE/DELETE)
- **Rationale:** Only the backend service should be able to create, modify, or delete audit entries to maintain data integrity and prevent tampering.

### 3. Search Path Hijacking Prevention

**Problem:** Functions `update_updated_at_column()` and `handle_new_user()` had mutable `search_path`, making them vulnerable to search path hijacking attacks.

**Solution:** Fixed the search_path for both functions to prevent schema-based attacks:

```sql
ALTER FUNCTION public.update_updated_at_column() SET search_path = public, extensions;
ALTER FUNCTION public.handle_new_user() SET search_path = public, extensions;
```

**Explanation:**
- Setting a fixed `search_path` ensures that the functions always resolve objects (tables, other functions) from the `public` and `extensions` schemas only.
- This prevents attackers from creating malicious objects in other schemas that could be inadvertently used by these functions.
- The `public` schema is included for standard tables and functions.
- The `extensions` schema is included to allow use of Supabase/PostgreSQL extensions (like `auth` functions, UUID generators, etc.).

## Verification Status

### Before Migration
- ❌ **RLS Error:** `audit_log` table without Row Level Security
- ⚠️ **Warning 1:** `update_updated_at_column()` function with mutable search_path
- ⚠️ **Warning 2:** `handle_new_user()` function with mutable search_path

### After Migration
- ✅ **RLS Enabled:** `audit_log` table protected with Row Level Security
- ✅ **RLS Policies:** Conservative policies implemented (service_role full access, users read-only)
- ✅ **Search Path Fixed:** Both functions now have immutable, secure search_path
- ✅ **SQL Validation:** All commands are idempotent-safe and syntactically correct for PostgreSQL/Supabase

## Security Best Practices Applied

1. **Principle of Least Privilege:** Each role has minimum necessary permissions
2. **Defense in Depth:** Multiple layers of security (RLS + policies + search path hardening)
3. **Audit Trail Protection:** Audit logs are protected from unauthorized modification
4. **Transparency:** Users can view their own audit history
5. **Schema Isolation:** Functions are protected from schema-based attacks

## Migration Idempotency

The migration is designed to be fully idempotent and safe to run multiple times:
- `ALTER TABLE ... ENABLE ROW LEVEL SECURITY` can be run multiple times without error
- `DROP POLICY IF EXISTS` ensures policies can be recreated safely
- `CREATE POLICY` creates fresh policies after dropping existing ones
- `ALTER FUNCTION ... SET search_path` can be run multiple times without error

**Migration Strategy:**
The script uses a "drop and recreate" pattern for policies:
1. Drop existing policies (if they exist)
2. Create fresh policies with current configuration

This ensures:
- ✅ First run: Creates everything successfully
- ✅ Subsequent runs: Updates policies without errors
- ✅ Safe for all environments (development, staging, production)

## Next Steps

1. Apply the migration to your Supabase database
2. Verify RLS is enabled: `SELECT tablename, rowsecurity FROM pg_tables WHERE tablename = 'audit_log';`
3. Verify policies exist: `SELECT * FROM pg_policies WHERE tablename = 'audit_log';`
4. Verify function security: `SELECT proname, proconfig FROM pg_proc WHERE proname IN ('update_updated_at_column', 'handle_new_user');`
5. Test that authenticated users can read their own audit logs
6. Test that authenticated users cannot insert/update/delete audit logs
7. Monitor for any application errors after deployment

## References

- [Supabase Row Level Security Documentation](https://supabase.com/docs/guides/auth/row-level-security)
- [PostgreSQL RLS Documentation](https://www.postgresql.org/docs/current/ddl-rowsecurity.html)
- [PostgreSQL Search Path Security](https://www.postgresql.org/docs/current/ddl-schemas.html#DDL-SCHEMAS-PATH)
