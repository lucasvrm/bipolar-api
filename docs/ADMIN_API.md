# Admin API Endpoints Documentation

This document describes the comprehensive Admin API layer for managing users and synthetic data in the bipolar-api platform.

## Authentication

All admin endpoints require:
- Valid JWT token in `Authorization: Bearer <token>` header
- User email must be in `ADMIN_EMAILS` environment variable OR user_metadata.role must be "admin"

## Environment Variables

### Required
- `ADMIN_EMAILS` - Comma-separated list of admin emails (must include `lucasvrm@gmail.com` in production)
- `SUPABASE_URL` - Supabase project URL
- `SUPABASE_SERVICE_KEY` - Supabase service role key (backend only, never exposed to frontend)
- `SUPABASE_ANON_KEY` - Supabase anon key (for user authentication)

### Optional (Production Safety)
- `APP_ENV` - Set to "production" for production environment
- `ALLOW_SYNTHETIC_IN_PROD` - Set to "1" to allow synthetic operations in production (default: disabled)
- `SYNTHETIC_MAX_PATIENTS_PROD` - Max patients to create in production (default: 50)
- `SYNTHETIC_MAX_THERAPISTS_PROD` - Max therapists to create in production (default: 10)
- `SYNTHETIC_MAX_CHECKINS_PER_USER_PROD` - Max check-ins per user in production (default: 60)

## User Management Endpoints

### List Users
```
GET /api/admin/users
```

Query Parameters:
- `role` (optional): Filter by role ("patient" or "therapist")
- `is_test_patient` (optional): Filter by test patient status (true/false)
- `source` (optional): Filter by source ("synthetic", "admin_manual", "signup")
- `include_deleted` (optional): Include deleted users (default: false)
- `limit` (optional): Number of results (max 200, default 50)
- `offset` (optional): Pagination offset (default 0)

Response:
```json
{
  "status": "success",
  "users": [
    {
      "id": "uuid",
      "email": "user@example.com",
      "role": "patient",
      "created_at": "2024-01-01T00:00:00Z",
      "is_test_patient": false,
      "source": "admin_manual",
      "deleted_at": null
    }
  ],
  "total": 10
}
```

### Get User Detail
```
GET /api/admin/users/{user_id}
```

Response includes user profile and aggregated stats:
```json
{
  "status": "success",
  "user": {
    "id": "uuid",
    "email": "user@example.com",
    "role": "patient",
    "...": "other profile fields"
  },
  "aggregates": {
    "checkins_count": 45,
    "clinical_notes_as_patient": 5,
    "clinical_notes_as_therapist": 0,
    "has_crisis_plan": true,
    "assigned_therapist_id": "therapist-uuid",
    "assigned_patients_count": 0
  }
}
```

### Create User
```
POST /api/admin/users/create
```

Request Body:
```json
{
  "email": "newuser@example.com",
  "password": "securePassword123",
  "role": "patient",
  "full_name": "João Silva"
}
```

Response:
```json
{
  "status": "success",
  "message": "Usuário patient criado com sucesso",
  "user_id": "uuid",
  "email": "newuser@example.com",
  "role": "patient"
}
```

### Update User
```
PATCH /api/admin/users/{user_id}
```

Request Body (all fields optional):
```json
{
  "role": "therapist",
  "username": "dr_silva",
  "email": "updated@example.com",
  "is_test_patient": true,
  "source": "admin_manual"
}
```

Response:
```json
{
  "status": "success",
  "message": "User updated successfully",
  "user_id": "uuid"
}
```

### Delete User
```
DELETE /api/admin/users/{user_id}
```

Behavior:
- **Test users** (`is_test_patient = true`): **HARD DELETE** - removes all data and auth.users entry
- **Normal users** (`is_test_patient = false`): **SOFT DELETE** - sets `deleted_at` timestamp

Response:
```json
{
  "status": "success",
  "message": "User hard deleted successfully",
  "user_id": "uuid",
  "deletion_type": "hard"
}
```

## Test Data Management

### Delete All Test Users
```
POST /api/admin/test-data/delete-test-users
```

Deletes all users where `is_test_patient = true` (hard delete with cascade).

Response:
```json
{
  "status": "success",
  "message": "Deleted 25 test users",
  "users_deleted": 25,
  "checkins_deleted": 750,
  "clinical_notes_deleted": 50,
  "crisis_plans_deleted": 20,
  "therapist_assignments_deleted": 25
}
```

### Clear Database
```
POST /api/admin/test-data/clear-database
```

**DANGEROUS OPERATION** - Clears all domain data, hard deletes test users, soft deletes normal users.

Requirements:
- In production: requires `ALLOW_SYNTHETIC_IN_PROD = 1`
- Requires exact confirmation text: "DELETE ALL DATA"

Request Body:
```json
{
  "confirm_text": "DELETE ALL DATA",
  "delete_audit_logs": false
}
```

Response:
```json
{
  "status": "success",
  "message": "Database cleared successfully",
  "checkins_deleted": 1000,
  "clinical_notes_deleted": 100,
  "crisis_plans_deleted": 50,
  "therapist_assignments_deleted": 75,
  "test_users_deleted": 25,
  "normal_users_soft_deleted": 10,
  "audit_logs_deleted": 0
}
```

## Bulk Operations

### Bulk User Generation
```
POST /api/admin/synthetic/bulk-users
```

Generate multiple synthetic users at once.

Production Limits:
- Patients: max `SYNTHETIC_MAX_PATIENTS_PROD` (default 50)
- Therapists: max `SYNTHETIC_MAX_THERAPISTS_PROD` (default 10)

Request Body:
```json
{
  "role": "patient",
  "count": 10,
  "is_test_patient": true,
  "source": "synthetic",
  "auto_assign_therapists": true
}
```

Response:
```json
{
  "status": "success",
  "message": "Created 10 patient(s)",
  "users_created": 10,
  "user_ids": ["uuid1", "uuid2", "..."],
  "patients_count": 10,
  "therapists_count": 0
}
```

### Bulk Check-ins Generation
```
POST /api/admin/synthetic/bulk-checkins
```

Generate check-ins for multiple users.

Production Limits:
- Max check-ins per user: `SYNTHETIC_MAX_CHECKINS_PER_USER_PROD` (default 60)

Request Body:
```json
{
  "all_test_patients": true,
  "last_n_days": 30,
  "checkins_per_day_min": 1,
  "checkins_per_day_max": 1,
  "mood_pattern": "stable"
}
```

OR with specific users:
```json
{
  "target_users": ["uuid1", "uuid2"],
  "start_date": "2024-01-01T00:00:00Z",
  "end_date": "2024-01-31T23:59:59Z",
  "checkins_per_day_min": 1,
  "checkins_per_day_max": 3,
  "mood_pattern": "cycling"
}
```

Mood patterns:
- `stable` - Consistent euthymic mood
- `cycling` - Alternates between hypomanic and depressed
- `manic` - Manic state
- `depressive` - Depressive state
- `random` - Random mood states

Response:
```json
{
  "status": "success",
  "message": "Created 300 check-ins for 10 users",
  "checkins_created": 300,
  "users_affected": 10,
  "date_range": {
    "start": "2024-01-01T00:00:00Z",
    "end": "2024-01-30T23:59:59Z"
  }
}
```

## Audit Logging

All admin operations are logged to the `audit_log` table with:
- `action` - Operation type (e.g., "BULK_CREATE_USERS", "DELETE_TEST_USERS")
- `performed_by` - Admin user ID (when available)
- `user_id` - Affected user ID (when applicable)
- `details` - JSON with operation details:
  - Environment (production/test)
  - Counts (users, check-ins, etc.)
  - Input parameters
  - Production limits applied
  - Sample IDs

View recent audit logs:
```
GET /api/admin/audit/recent?limit=50
```

## Legacy Endpoints (Backward Compatibility)

These endpoints are maintained for backward compatibility but new code should use the new endpoints above.

### POST /api/admin/generate-data
Combined user + check-in generation. Use `/synthetic/bulk-users` + `/synthetic/bulk-checkins` instead.

### POST /api/admin/cleanup
Simple synthetic data removal. Use `/test-data/delete-test-users` instead.

### POST /api/admin/danger-zone-cleanup
Selective test patient deletion with advanced filtering. Still useful for specific cleanup scenarios.

## Error Codes

- `401 Unauthorized` - No valid authentication token
- `403 Forbidden` - User not admin OR operation not allowed in current environment
- `400 Bad Request` - Invalid input OR production limits exceeded
- `404 Not Found` - User/resource not found
- `500 Internal Server Error` - Unexpected server error

## Security Considerations

1. **SERVICE ROLE key** is only used on backend - never exposed to frontend
2. All endpoints require admin authorization
3. Production limits enforced at backend layer
4. Hard delete only for test users, soft delete for normal users
5. Sensitive operations require explicit confirmation
6. All operations logged to audit trail

## Usage Examples

### Seed test environment with synthetic data:
```bash
# 1. Create test patients
curl -X POST https://api.example.com/api/admin/synthetic/bulk-users \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "role": "patient",
    "count": 20,
    "is_test_patient": true,
    "source": "synthetic",
    "auto_assign_therapists": true
  }'

# 2. Generate check-ins for past 60 days
curl -X POST https://api.example.com/api/admin/synthetic/bulk-checkins \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "all_test_patients": true,
    "last_n_days": 60,
    "checkins_per_day_min": 1,
    "checkins_per_day_max": 2,
    "mood_pattern": "cycling"
  }'
```

### Clean up after testing:
```bash
curl -X POST https://api.example.com/api/admin/test-data/delete-test-users \
  -H "Authorization: Bearer ${TOKEN}"
```
