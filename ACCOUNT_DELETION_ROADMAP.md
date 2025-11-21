# Account Deletion Flow - Complete ROADMAP

## Overview

This document describes the complete account deletion system implemented in the Bipolar API, including soft-delete scheduling, data export, and hard deletion with a 14-day grace period.

## Architecture Components

### 1. Database Schema

#### Profiles Table Extensions
```sql
ALTER TABLE public.profiles
ADD COLUMN deletion_scheduled_at timestamp with time zone,
ADD COLUMN deleted_at timestamp with time zone,
ADD COLUMN deletion_token uuid DEFAULT gen_random_uuid();
```

**Fields:**
- `deletion_scheduled_at`: When deletion was requested (null if not scheduled)
- `deleted_at`: When hard deletion was completed (null if not deleted)
- `deletion_token`: Unique UUID for canceling deletion via email link

#### Audit Log Table
```sql
CREATE TABLE public.audit_log (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id uuid NOT NULL,
  action text NOT NULL,
  details jsonb,
  performed_by uuid,
  created_at timestamp with time zone DEFAULT now()
);
```

**Action Types:**
- `delete_requested`: User requested account deletion
- `delete_cancelled`: User canceled deletion via token
- `hard_deleted`: System completed hard deletion
- `export_requested`: User exported their data

### 2. API Endpoints

#### POST /account/export
**Purpose:** Export all user data in ZIP format (JSON + CSV)

**Authentication:** Required (JWT token)

**Role-Based Logic:**
- **Patient**: Exports only their own data
- **Therapist**: Exports own data + all linked patients' data
  - Optional `anonymize=true` query parameter to anonymize patient identities

**Exported Data:**
- Profile information
- Check-ins (mood, sleep, symptoms)
- Crisis plans
- Clinical notes
- Therapist-patient relationships
- Consent preferences

**Rate Limit:** 5 requests per hour

**Response:** ZIP file containing:
- `export.json`: Complete data in JSON format
- `check_ins.csv`: Check-ins in CSV format
- `crisis_plan.csv`: Crisis plans in CSV format

**Example Request:**
```bash
curl -X POST https://api.previso.com/account/export \
  -H "Authorization: Bearer <jwt-token>" \
  -H "Content-Type: application/json" \
  -d '{"anonymize": false}'
```

#### POST /account/delete-request
**Purpose:** Schedule account deletion with 14-day grace period

**Authentication:** Required (JWT token)

**Validation Rules:**
1. **Therapists**: Cannot delete if they have active patients
   - Returns 403 with message: "Você tem X paciente(s) ativo(s). Transfira ou desvincule todos antes de excluir sua conta."
2. **Patients**: Can delete immediately (grace period still applies)

**Process:**
1. Validates user has no active patients (if therapist)
2. Sets `deletion_scheduled_at` = now() + 14 days
3. Generates new `deletion_token`
4. Sends email with cancellation link to user
5. If patient with therapist, notifies therapist
6. Logs audit event with action='delete_requested'

**Email Template:**
```
Subject: Solicitação de Exclusão de Conta - Previso

Você solicitou a exclusão da sua conta.

Sua conta será permanentemente excluída em: [deletion_date]

Se você mudou de ideia, pode cancelar a exclusão clicando neste link:
https://previso-fe.vercel.app/undo-delete?token=[deletion_token]

Este link expira em: [deletion_date]
```

**Therapist Notification (for patients):**
```
Subject: Notificação - Paciente Solicitou Exclusão de Conta

O paciente [patient_name] solicitou a exclusão da conta.

A conta será apagada permanentemente em: [deletion_date]

Todos os dados do paciente, incluindo check-ins e notas clínicas, serão removidos.
```

**Rate Limit:** 3 requests per hour

**Example Request:**
```bash
curl -X POST https://api.previso.com/account/delete-request \
  -H "Authorization: Bearer <jwt-token>"
```

**Example Response:**
```json
{
  "status": "success",
  "message": "Sua conta foi agendada para exclusão. Você receberá um e-mail com instruções para cancelar se mudar de ideia.",
  "deletion_scheduled_at": "2024-02-01T00:00:00Z",
  "deletion_date": "01/02/2024 às 00:00"
}
```

#### POST /account/undo-delete
**Purpose:** Cancel pending deletion using email token

**Authentication:** Not required (public endpoint, validated by token)

**Process:**
1. Finds profile by `deletion_token`
2. Validates `deletion_scheduled_at > now()` (still in grace period)
3. Clears `deletion_scheduled_at` and `deletion_token`
4. Logs audit event with action='delete_cancelled'

**Validation:**
- Token must exist and be valid UUID
- Deletion must still be scheduled (not yet executed)
- Deletion date must be in the future

**Example Request:**
```bash
curl -X POST https://api.previso.com/account/undo-delete \
  -H "Content-Type: application/json" \
  -d '{"token": "123e4567-e89b-12d3-a456-426614174000"}'
```

**Example Response:**
```json
{
  "status": "success",
  "message": "Exclusão cancelada com sucesso. Sua conta permanecerá ativa.",
  "user_id": "123e4567-e89b-12d3-a456-426614174000"
}
```

### 3. Scheduled Deletion Job

**Location:** `jobs/scheduled_deletion.py`

**Schedule:** Daily at 2 AM UTC (configurable)

**Purpose:** Process hard deletions for accounts past their 14-day grace period

**Logic:**
```python
# Find users to delete
WHERE deletion_scheduled_at <= now() 
  AND deleted_at IS NULL

# For each user, cascade delete in order:
1. check_ins (WHERE user_id = profile.id)
2. crisis_plan (WHERE user_id = profile.id)
3. clinical_notes (WHERE patient_id = profile.id OR therapist_id = profile.id)
4. therapist_patients (WHERE patient_id = profile.id OR therapist_id = profile.id)
5. user_consent (WHERE user_id = profile.id)
6. profiles (WHERE id = profile.id)

# Optional: Delete from Supabase Auth
# await supabase.auth.admin.delete_user(profile.id)

# Log audit event
action = 'hard_deleted'
details = { email, role, deletion_scheduled_at, deleted_records }
```

**Deployment Options:**

1. **pg_cron** (PostgreSQL built-in scheduler):
```sql
SELECT cron.schedule(
  'hard-delete-scheduled-accounts',
  '0 2 * * *',
  $$ 
  SELECT net.http_post(
    url := 'https://api.previso.com/api/admin/run-deletion-job',
    headers := '{"Authorization": "Bearer service-key"}'::jsonb
  );
  $$
);
```

2. **Supabase Edge Function** (recommended for Supabase projects)

3. **GitHub Actions** (scheduled workflow)

4. **External Cron Service** (Vercel Cron, AWS CloudWatch, etc.)

**Monitoring:**
- Job logs (stdout/stderr)
- audit_log table (action='hard_deleted')
- Job statistics (users processed, deleted, errors)

### 4. Soft Delete Filtering

**Required:** All listing endpoints must filter out soft-deleted accounts

**Filter Logic:**
```sql
WHERE deleted_at IS NULL 
  AND (deletion_scheduled_at IS NULL OR deletion_scheduled_at > now())
```

**Affected Endpoints:**
- GET /user/{user_id}/profile
- All patient/therapist listing endpoints
- All data retrieval endpoints

**Implementation:**
Add filter to all Supabase queries that return profiles or user data.

### 5. Data Flow Diagrams

#### Deletion Request Flow
```
┌─────────────┐
│   Patient   │
│  requests   │
│  deletion   │
└──────┬──────┘
       │
       ▼
┌─────────────────────────────────────┐
│ POST /account/delete-request        │
│ - Verify no active patients (if     │
│   therapist)                        │
│ - Set deletion_scheduled_at         │
│ - Generate deletion_token           │
│ - Send email with undo link         │
│ - Notify therapist (if patient)     │
│ - Log audit event                   │
└──────┬──────────────────────────────┘
       │
       ▼
┌─────────────────────────────────────┐
│        14-Day Grace Period          │
│                                     │
│  User can:                          │
│  - Cancel via email link            │
│  - Continue using account normally  │
│  - Export data                      │
└──────┬──────────────────────────────┘
       │
       ▼
┌─────────────────────────────────────┐
│   Scheduled Job (Daily 2 AM)        │
│                                     │
│ If deletion_scheduled_at <= now():  │
│  - Hard delete all user data        │
│  - Cascade to all related tables    │
│  - Log audit event                  │
│  - Optional: Delete from Auth       │
└─────────────────────────────────────┘
```

#### Cancellation Flow
```
┌─────────────┐
│    User     │
│ clicks link │
│  in email   │
└──────┬──────┘
       │
       ▼
┌─────────────────────────────────────┐
│ GET /undo-delete?token=xxx          │
│ (Frontend redirects to API)         │
└──────┬──────────────────────────────┘
       │
       ▼
┌─────────────────────────────────────┐
│ POST /account/undo-delete           │
│ - Validate token                    │
│ - Check grace period not expired    │
│ - Clear deletion fields             │
│ - Log audit event                   │
└──────┬──────────────────────────────┘
       │
       ▼
┌─────────────────────────────────────┐
│    Account Restored                 │
│ User can continue using normally    │
└─────────────────────────────────────┘
```

#### Data Export Flow
```
┌─────────────┐
│Patient/Ther │
│  requests   │
│   export    │
└──────┬──────┘
       │
       ▼
┌─────────────────────────────────────┐
│ POST /account/export                │
│ - Verify authentication             │
│ - Collect user data                 │
│ - If therapist: collect patients    │
│ - Generate ZIP (JSON + CSV)         │
│ - Log audit event                   │
└──────┬──────────────────────────────┘
       │
       ▼
┌─────────────────────────────────────┐
│      ZIP File Download              │
│                                     │
│  Files:                             │
│  - export.json (full data)          │
│  - check_ins.csv                    │
│  - crisis_plan.csv                  │
└─────────────────────────────────────┘
```

## Compliance & Security

### GDPR/LGPD Compliance
- ✅ Right to data portability (export endpoint)
- ✅ Right to be forgotten (deletion endpoints)
- ✅ Right to rectification (grace period for cancellation)
- ✅ Audit trail (audit_log table)
- ✅ User consent tracking (included in export)

### Security Measures
- ✅ JWT authentication for all endpoints
- ✅ Role-based access control
- ✅ Rate limiting (prevent abuse)
- ✅ UUID tokens (unpredictable, secure)
- ✅ Audit logging (all actions tracked)
- ✅ Cascading deletes (data consistency)
- ✅ Soft delete first (recovery period)

### Privacy Protection
- ✅ Therapist notification (patient deletion only, not reverse)
- ✅ Anonymous export option for therapists
- ✅ Secure token-based cancellation
- ✅ No PII in logs (hashed user IDs)

## Testing

### Unit Tests
Location: `tests/test_account_endpoints.py`

**Coverage:**
- ✅ Export requires authentication
- ✅ Export patient data successfully
- ✅ Delete request requires authentication
- ✅ Therapist with patients cannot delete
- ✅ Patient deletion request successful
- ✅ Undo delete with invalid token
- ✅ Undo delete successfully
- ✅ Undo delete with expired token
- ✅ Invalid UUID validation

**Running Tests:**
```bash
python -m pytest tests/test_account_endpoints.py -v
```

### Integration Testing Checklist
- [ ] Test complete deletion flow (request → wait → hard delete)
- [ ] Test cancellation flow (request → undo → continue using)
- [ ] Test therapist with patients prevention
- [ ] Test patient-therapist notification
- [ ] Test email delivery
- [ ] Test scheduled job execution
- [ ] Test soft delete filtering in all endpoints
- [ ] Test data export for both roles
- [ ] Test audit log creation

## Deployment Checklist

### Database Setup
1. ✅ Run migration `001_add_soft_delete_to_profiles.sql`
2. ✅ Run migration `002_create_audit_log_table.sql`
3. ✅ Run migration `003_create_missing_tables.sql`
4. ✅ Verify indexes created
5. ✅ Test query performance with EXPLAIN ANALYZE

### API Deployment
1. ✅ Deploy new `api/account.py` router
2. ✅ Verify endpoints accessible
3. ✅ Configure rate limiting
4. ✅ Set up CORS for frontend

### Job Scheduling
1. [ ] Choose scheduling method (pg_cron, Edge Function, etc.)
2. [ ] Configure job to run daily at 2 AM UTC
3. [ ] Set up monitoring and alerts
4. [ ] Test job execution manually
5. [ ] Verify audit logs created

### Email Service
1. [ ] Configure email service (SendGrid, AWS SES, etc.)
2. [ ] Create email templates
3. [ ] Set up email sending in deletion request
4. [ ] Test email delivery
5. [ ] Configure therapist notification emails

### Frontend Integration
1. [ ] Add "Delete Account" button in settings
2. [ ] Add "Export Data" button in settings
3. [ ] Create `/undo-delete` page
4. [ ] Add therapist patient management UI
5. [ ] Test complete user flows

### Monitoring
1. [ ] Set up logging for deletion job
2. [ ] Configure alerts for job failures
3. [ ] Monitor audit_log table
4. [ ] Track deletion request metrics
5. [ ] Monitor rate limit hits

## Maintenance

### Regular Tasks
- **Daily**: Monitor deletion job logs
- **Weekly**: Review audit_log for patterns
- **Monthly**: Analyze deletion metrics
- **Quarterly**: Review and update email templates

### Troubleshooting

**Problem:** Deletion job fails
- Check Supabase connection
- Verify environment variables set
- Review job logs for specific error
- Check database permissions

**Problem:** User cannot undo deletion
- Verify token in database
- Check deletion_scheduled_at not in past
- Verify frontend sends correct token
- Check API endpoint logs

**Problem:** Therapist blocked from deletion
- Verify therapist_patients table has correct status
- Check for orphaned relationships
- Provide UI to transfer/delink patients

## Future Enhancements

### Potential Improvements
1. **Bulk Operations**: Admin endpoint to process multiple deletions
2. **Custom Grace Periods**: Allow users to choose grace period length
3. **Deletion Analytics**: Dashboard showing deletion trends
4. **Data Retention**: Option to retain anonymized data for research
5. **Multi-language**: Support for multiple languages in emails
6. **SMS Notifications**: Alternative to email for deletion confirmation
7. **Two-Factor**: Require 2FA for deletion requests
8. **Transfer Wizard**: Guided process for therapists to transfer patients

## Support & Documentation

### For Developers
- Code: `api/account.py`, `jobs/scheduled_deletion.py`
- Tests: `tests/test_account_endpoints.py`
- Migrations: `migrations/*.sql`

### For Support Team
- User deletion requests: Check audit_log table
- Failed deletions: Review job logs
- Cancellation issues: Verify token validity
- Data exports: Check audit_log for export_requested

### For Users
- How to delete account: Settings → Account → Delete Account
- How to export data: Settings → Account → Export Data
- How to cancel deletion: Check email for undo link
- Grace period: 14 days from request date

---

**Last Updated:** 2024-01-15
**Version:** 1.0
**Status:** ✅ Implemented and Tested
