# ROADMAP: Data Generator Role Constraint Fix & API Refactoring

## Executive Summary

This document outlines the changes made to fix the `profiles_role_check` constraint violation and refactor the data generation endpoint to support parametrized creation of patient and therapist profiles.

---

## 1. Check Constraint Analysis

### Constraint Name
`profiles_role_check`

### Allowed Values
The `role` column in the `profiles` table accepts the following values:
- `patient` - Patient users with check-in data
- `therapist` - Therapist users (no check-ins)
- `admin` - Administrative users

### Previous Error
The data generator was attempting to create profiles **without** a `role` field, or with invalid values like `'user'`, causing the constraint violation:
```
ERROR: check constraint "profiles_role_check" violated
```

### Fix Applied
All profile creation now explicitly includes a valid `role` field:
```python
profile_data = {
    "id": user_id,
    "email": email,
    "role": "patient",  # or "therapist"
    "updated_at": datetime.now(timezone.utc).isoformat()
}
```

---

## 2. New API Contract

### Endpoint
`POST /api/admin/generate-data`

### Request Body Schema

```json
{
  "patients_count": 5,
  "therapists_count": 2,
  "checkins_per_user": 30,
  "mood_pattern": "stable",
  "clear_db": false
}
```

### Field Specifications

| Field | Type | Default | Range | Description |
|-------|------|---------|-------|-------------|
| `patients_count` | integer | 2 | 0-100 | Number of patient profiles to generate. Patients will have check-ins. |
| `therapists_count` | integer | 1 | 0-50 | Number of therapist profiles to generate. Therapists won't have check-ins. |
| `checkins_per_user` | integer | 30 | 1-365 | Number of check-ins to generate per patient. |
| `mood_pattern` | string | "stable" | - | Mood pattern: "stable", "cycling", or "random" |
| `clear_db` | boolean | false | - | If true, clears all synthetic data before generating new data |

### Legacy Support

The endpoint still supports the legacy `num_users` parameter for backward compatibility:

```json
{
  "num_users": 10,
  "checkins_per_user": 30,
  "mood_pattern": "stable"
}
```

When `num_users` is provided, all users are created as **patients**.

### Response Schema

```json
{
  "status": "success",
  "message": "Generated 5 patients and 2 therapists with 150 check-ins",
  "statistics": {
    "users_created": 7,
    "patients_created": 5,
    "therapists_created": 2,
    "user_ids": ["uuid1", "uuid2", ...],
    "checkins_per_user": 30,
    "total_checkins": 150,
    "mood_pattern": "stable",
    "generated_at": "2024-01-15T10:30:00Z"
  }
}
```

### Validation Rules

1. **At least one user type required**: Either `patients_count > 0` or `therapists_count > 0`
2. **Valid mood pattern**: Must be one of `["stable", "cycling", "random"]`
3. **Parameter ranges enforced**: Via Pydantic field validators
4. **Admin authentication required**: Via JWT token with admin role

### Example Requests

**Create 5 patients and 2 therapists:**
```bash
curl -X POST https://api.example.com/api/admin/generate-data \
  -H "Authorization: Bearer <jwt-token>" \
  -H "Content-Type: application/json" \
  -d '{
    "patients_count": 5,
    "therapists_count": 2,
    "checkins_per_user": 30,
    "mood_pattern": "stable",
    "clear_db": false
  }'
```

**Clear database and create new data:**
```bash
curl -X POST https://api.example.com/api/admin/generate-data \
  -H "Authorization: Bearer <jwt-token>" \
  -H "Content-Type: application/json" \
  -d '{
    "patients_count": 3,
    "therapists_count": 1,
    "checkins_per_user": 15,
    "clear_db": true
  }'
```

**Only therapists (no check-ins):**
```bash
curl -X POST https://api.example.com/api/admin/generate-data \
  -H "Authorization: Bearer <jwt-token>" \
  -H "Content-Type: application/json" \
  -d '{
    "patients_count": 0,
    "therapists_count": 5
  }'
```

---

## 3. Logic Comparison: Before vs After

### Before (Previous Implementation)

```python
# Single loop, no role specification
for i in range(num_users):
    profile_data = {
        "id": user_id,
        "email": email,
        "updated_at": datetime.now(timezone.utc).isoformat()
        # ❌ NO ROLE FIELD - causes constraint violation
    }
    await supabase.table('profiles').insert(profile_data).execute()
    
    # All users get check-ins
    checkins = generate_user_checkin_history(...)
    all_checkins.extend(checkins)
```

**Issues:**
- ❌ Missing `role` field → constraint violation
- ❌ No distinction between patient and therapist
- ❌ No control over user types
- ❌ All users get check-ins (even if they shouldn't)

### After (New Implementation)

```python
# Separate loops for patients and therapists

# Create patients with check-ins
for i in range(patients_count):
    profile_data = {
        "id": user_id,
        "email": email,
        "role": "patient",  # ✅ Valid role
        "updated_at": datetime.now(timezone.utc).isoformat()
    }
    await supabase.table('profiles').insert(profile_data).execute()
    
    # Only patients get check-ins
    checkins = generate_user_checkin_history(...)
    all_checkins.extend(checkins)

# Create therapists without check-ins
for i in range(therapists_count):
    profile_data = {
        "id": user_id,
        "email": email,
        "role": "therapist",  # ✅ Valid role
        "updated_at": datetime.now(timezone.utc).isoformat()
    }
    await supabase.table('profiles').insert(profile_data).execute()
    # Therapists don't have check-ins
```

**Improvements:**
- ✅ Explicit `role` field → no constraint violation
- ✅ Separation between patients and therapists
- ✅ Controlled generation of specific user types
- ✅ Check-ins only for patients (realistic model)
- ✅ Precise count control: "I want exactly 5 patients and 2 therapists"

---

## 4. Validation Requirements

### Before Fix
- ❌ Endpoint fails with 500 error
- ❌ Database constraint violation
- ❌ No control over user types
- ❌ Random data generation

### After Fix
- ✅ Endpoint returns 200 OK
- ✅ No constraint violations
- ✅ Exact count control: if you request 5 patients and 2 therapists, you get exactly that
- ✅ Parametrized data generation
- ✅ Optional database cleanup before generation
- ✅ Backward compatibility with legacy `num_users` parameter

### Measurement Validation

To verify the fix:

1. **Test the endpoint returns 200 OK:**
   ```bash
   curl -X POST /api/admin/generate-data \
     -H "Authorization: Bearer <token>" \
     -d '{"patients_count": 5, "therapists_count": 2}'
   ```
   Expected: HTTP 200, no errors

2. **Verify exact counts in database:**
   ```sql
   SELECT role, COUNT(*) FROM profiles 
   WHERE email LIKE '%@example.%' 
   GROUP BY role;
   ```
   Expected for request above:
   - `patient`: 5
   - `therapist`: 2

3. **Verify check-ins only for patients:**
   ```sql
   SELECT p.role, COUNT(c.id) as checkin_count
   FROM profiles p
   LEFT JOIN check_ins c ON p.id = c.user_id
   WHERE p.email LIKE '%@example.%'
   GROUP BY p.role;
   ```
   Expected:
   - `patient`: 30 check-ins each (or specified count)
   - `therapist`: 0 check-ins

---

## 5. Database Schema Compliance

### Profiles Table Expected Schema

```sql
CREATE TABLE profiles (
  id UUID PRIMARY KEY,
  email TEXT UNIQUE NOT NULL,
  role TEXT NOT NULL CHECK (role IN ('patient', 'therapist', 'admin')),
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
```

### Constraint: `profiles_role_check`
```sql
CHECK (role IN ('patient', 'therapist', 'admin'))
```

All profile insertions now comply with this constraint.

---

## 6. Migration Path

### For Existing Users

1. **Backward Compatible**: The `num_users` parameter still works
2. **Gradual Migration**: Update to new parameters at your convenience
3. **No Breaking Changes**: Existing scripts continue to function

### Recommended Updates

Update your scripts from:
```json
{"num_users": 10}
```

To the more explicit:
```json
{"patients_count": 10, "therapists_count": 0}
```

This makes the intent clearer and unlocks new capabilities.

---

## 7. Future Enhancements

Potential improvements for future iterations:

- [ ] Add `admin` role generation capability
- [ ] Support custom check-in date ranges per patient
- [ ] Allow different mood patterns per patient
- [ ] Bulk import from CSV/JSON files
- [ ] Progress tracking for large generations
- [ ] Async task queue for very large datasets
- [ ] Validation report generation post-creation

---

## 8. Technical Details

### Files Modified

1. **`data_generator.py`**
   - Added `role` field to all profile creations
   - Refactored `generate_and_populate_data()` to accept `patients_count` and `therapists_count`
   - Implemented separate generation loops for patients and therapists
   - Added backward compatibility for `num_users` parameter

2. **`api/admin.py`**
   - Updated `GenerateDataRequest` model with new fields
   - Added `clear_db` functionality
   - Enhanced endpoint documentation
   - Improved error handling and validation

3. **`ROADMAP.md`** (this file)
   - Comprehensive documentation of changes

### Code Quality Improvements

- Better separation of concerns (patients vs therapists)
- More explicit parameter names
- Enhanced logging for debugging
- Improved error messages
- Maintained backward compatibility

---

## Conclusion

The data generator now:
1. ✅ Complies with database constraints
2. ✅ Provides granular control over user type creation
3. ✅ Maintains backward compatibility
4. ✅ Offers optional database cleanup
5. ✅ Returns precise statistics

This implementation resolves the constraint violation bug while significantly improving the developer experience through parametrized, controlled data generation.
