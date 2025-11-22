# Database Migrations

This directory contains SQL migration files for the account deletion and data management features.

## Migration Order

These migrations must be executed in the following order:

1. **001_add_soft_delete_to_profiles.sql** - Adds soft delete fields to profiles table
2. **002_create_audit_log_table.sql** - Creates audit log table for tracking operations
3. **003_create_missing_tables.sql** - Creates therapist_patients, crisis_plan, and clinical_notes tables
4. **004_add_is_test_patient_column.sql** - Adds is_test_patient column
5. **005_ensure_check_ins_fk_cascade.sql** - Ensures foreign key cascade for check_ins
6. **006_security_hardening.sql** - Enables RLS on audit_log and fixes function search_path security

## Running Migrations

### Option 1: Supabase Dashboard
1. Go to your Supabase project dashboard
2. Navigate to SQL Editor
3. Copy and paste each migration file in order
4. Execute each migration

### Option 2: Supabase CLI
```bash
# Apply migrations in order
supabase db push

# Or manually execute each file
psql $DATABASE_URL -f migrations/001_add_soft_delete_to_profiles.sql
psql $DATABASE_URL -f migrations/002_create_audit_log_table.sql
psql $DATABASE_URL -f migrations/003_create_missing_tables.sql
psql $DATABASE_URL -f migrations/004_add_is_test_patient_column.sql
psql $DATABASE_URL -f migrations/005_ensure_check_ins_fk_cascade.sql
psql $DATABASE_URL -f migrations/006_security_hardening.sql
```

## Verification

After running migrations, verify the schema:

```sql
-- Check profiles table structure
\d profiles

-- Check audit_log table
\d audit_log

-- Verify indexes
SELECT indexname, tablename FROM pg_indexes 
WHERE tablename IN ('profiles', 'audit_log', 'therapist_patients', 'crisis_plan', 'clinical_notes');

-- Test query with filters
EXPLAIN ANALYZE 
SELECT * FROM profiles 
WHERE deleted_at IS NULL 
  AND (deletion_scheduled_at IS NULL OR deletion_scheduled_at > now());
```

## Notes

- All migrations use `IF NOT EXISTS` clauses to be idempotent
- Indexes are created for optimal query performance
- Foreign key constraints ensure referential integrity
- Cascading deletes are configured for cleanup
