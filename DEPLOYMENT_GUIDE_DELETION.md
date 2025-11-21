# Account Deletion Implementation - Quick Start Guide

## Overview

This implementation adds a complete account deletion system with:
- ✅ Soft-delete with 14-day grace period
- ✅ Data export (GDPR/LGPD compliant)
- ✅ Audit logging
- ✅ Role-based access control
- ✅ Therapist-patient relationship validation

## Quick Deployment

### Step 1: Run Database Migrations

Execute migrations in order using Supabase SQL Editor:

```bash
# 1. Add soft delete fields to profiles
migrations/001_add_soft_delete_to_profiles.sql

# 2. Create audit log table
migrations/002_create_audit_log_table.sql

# 3. Create relationship tables
migrations/003_create_missing_tables.sql
```

**Verification:**
```sql
-- Check new columns exist
\d profiles;

-- Should show: deletion_scheduled_at, deleted_at, deletion_token

-- Verify indexes
SELECT indexname FROM pg_indexes WHERE tablename = 'profiles';
```

### Step 2: Deploy API Changes

The API changes are already integrated:
- ✅ New router `api/account.py` included in `main.py`
- ✅ Soft-delete filtering added to profile endpoint
- ✅ Admin endpoint for manual job trigger

**No additional deployment steps needed for the API.**

### Step 3: Schedule Deletion Job

Choose one option:

#### Option A: GitHub Actions (Recommended for Quick Start)
Create `.github/workflows/scheduled-deletion.yml`:

```yaml
name: Scheduled Account Deletion
on:
  schedule:
    - cron: '0 2 * * *'  # Daily at 2 AM UTC
  workflow_dispatch:  # Allow manual trigger

jobs:
  delete-accounts:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
        with:
          python-version: '3.12'
      - run: pip install -r requirements.txt
      - name: Run deletion job
        env:
          SUPABASE_URL: ${{ secrets.SUPABASE_URL }}
          SUPABASE_SERVICE_KEY: ${{ secrets.SUPABASE_SERVICE_KEY }}
        run: python -m jobs.scheduled_deletion
```

#### Option B: API Endpoint (Manual/Testing)
```bash
curl -X POST https://your-api.com/api/admin/run-deletion-job \
  -H "Authorization: Bearer <admin-jwt-token>"
```

#### Option C: pg_cron (Production)
```sql
SELECT cron.schedule(
  'hard-delete-scheduled-accounts',
  '0 2 * * *',
  $$
  SELECT net.http_post(
    url := 'https://your-api.com/api/admin/run-deletion-job',
    headers := jsonb_build_object(
      'Authorization', 'Bearer ' || current_setting('app.admin_token')
    )
  );
  $$
);
```

### Step 4: Configure Environment Variables

Add to your environment (Render, Vercel, etc.):

```bash
# Already required (existing)
SUPABASE_URL=your-supabase-url
SUPABASE_SERVICE_KEY=your-service-key

# Optional: Email service (for future)
# SENDGRID_API_KEY=your-key
# EMAIL_FROM=noreply@previso.com
```

## Testing

### Manual Testing

1. **Test Export:**
```bash
# As authenticated user
curl -X POST https://your-api.com/account/export \
  -H "Authorization: Bearer <user-jwt>" \
  -o export.zip
```

2. **Test Deletion Request:**
```bash
# As patient
curl -X POST https://your-api.com/account/delete-request \
  -H "Authorization: Bearer <patient-jwt>"

# Response includes deletion_scheduled_at and deletion_token
```

3. **Test Undo:**
```bash
# Public endpoint (no auth needed)
curl -X POST https://your-api.com/account/undo-delete \
  -H "Content-Type: application/json" \
  -d '{"token": "uuid-from-previous-step"}'
```

4. **Test Manual Job:**
```bash
# As admin
curl -X POST https://your-api.com/api/admin/run-deletion-job \
  -H "Authorization: Bearer <admin-jwt>"
```

### Automated Testing

```bash
# Run all tests
python -m pytest tests/test_account_endpoints.py -v

# Should see:
# 9 passed in 0.21s
```

## Verification Checklist

After deployment:

- [ ] Migrations applied successfully
- [ ] New columns visible in profiles table: `\d profiles`
- [ ] Audit log table created: `SELECT * FROM audit_log LIMIT 1;`
- [ ] API endpoints accessible: `GET https://your-api.com/docs`
- [ ] Export endpoint returns ZIP file
- [ ] Delete request creates scheduled deletion
- [ ] Undo works with valid token
- [ ] Therapist with patients blocked from deletion
- [ ] Job can be triggered manually (admin endpoint)
- [ ] Scheduled job configured and running

## Monitoring

Check these regularly:

```sql
-- Pending deletions
SELECT id, email, deletion_scheduled_at 
FROM profiles 
WHERE deletion_scheduled_at IS NOT NULL 
  AND deleted_at IS NULL
ORDER BY deletion_scheduled_at;

-- Recent deletions
SELECT * FROM audit_log 
WHERE action = 'hard_deleted' 
ORDER BY created_at DESC 
LIMIT 10;

-- Deletion requests
SELECT * FROM audit_log 
WHERE action IN ('delete_requested', 'delete_cancelled')
ORDER BY created_at DESC 
LIMIT 10;
```

## Troubleshooting

### Issue: "therapist_patients table does not exist"
**Solution:** Run migration 003_create_missing_tables.sql

### Issue: "deletion job fails with permission error"
**Solution:** Verify SUPABASE_SERVICE_KEY has admin privileges

### Issue: "user cannot undo deletion"
**Solution:** 
- Check token is valid UUID
- Verify deletion_scheduled_at is in future
- Check token matches in database

### Issue: "soft-delete filter not working"
**Solution:** Update query to include:
```python
.is_('deleted_at', 'null')
```

## Next Steps

1. **Email Integration** (optional):
   - Set up SendGrid or AWS SES
   - Update TODOs in `api/account.py` lines 370, 383
   - Add email templates

2. **Frontend Integration**:
   - Add "Delete Account" button in settings
   - Add "Export Data" button
   - Create `/undo-delete` page

3. **Additional Features**:
   - Patient transfer wizard for therapists
   - Bulk deletion admin tool
   - Deletion analytics dashboard

## Support

- **Documentation:** `ACCOUNT_DELETION_ROADMAP.md`
- **Code:** `api/account.py`, `jobs/scheduled_deletion.py`
- **Tests:** `tests/test_account_endpoints.py`
- **Migrations:** `migrations/`

## Summary

✅ **Ready for Production**
- All code implemented and tested
- Migrations ready to run
- Multiple deployment options
- Comprehensive documentation

⏳ **Optional Enhancements**
- Email service integration
- Frontend UI
- Advanced admin tools
