# Query Changes - Fix for full_name Column Error

## Summary
This document compares the previous queries vs. the new queries that fix the `column profiles.full_name does not exist` error.

## Root Cause
The `profiles` table in the database does not have a `full_name` column. The data generator (`data_generator.py`) only creates profiles with:
- `id`
- `email`
- `updated_at`

## Changes Made

### 1. api/admin.py - get_admin_users() function

**Before (Line 223):**
```python
response = await supabase.table('profiles').select('id, email, full_name').order('created_at', desc=True).limit(50).execute()
```

**After:**
```python
response = await supabase.table('profiles').select('id, email').order('created_at', desc=True).limit(50).execute()
```

**Impact:**
- Endpoint `/api/admin/users` now returns 200 instead of 500
- Response includes `id` and `email` only
- Removed `full_name` from docstring as well

---

### 2. api/privacy.py - get_user_profile() function

**Before (Line 112):**
```python
response = await supabase.table('profiles')\
    .select('id, email, full_name, is_admin, created_at')\
    .eq('id', user_id)\
    .execute()
```

**After:**
```python
response = await supabase.table('profiles')\
    .select('id, email, is_admin, created_at')\
    .eq('id', user_id)\
    .execute()
```

**Impact:**
- Endpoint `/user/{user_id}/profile` now returns 200 instead of 500
- Response includes `id`, `email`, `is_admin`, `created_at` (no `full_name`)
- Updated docstring to reflect the change

---

## Test Updates

### 3. tests/test_admin_endpoints.py

**Before:**
```python
users_data = [
    {"id": "user-1", "email": "user1@example.com", "full_name": "User One"},
    {"id": "user-2", "email": "user2@example.com", "full_name": "User Two"},
    {"id": "user-3", "email": "user3@example.com", "full_name": None},
]
```

**After:**
```python
users_data = [
    {"id": "user-1", "email": "user1@example.com"},
    {"id": "user-2", "email": "user2@example.com"},
    {"id": "user-3", "email": "user3@example.com"},
]
```

**Also removed assertions:**
```python
# Before
assert "full_name" in data[0]
assert data[0]["full_name"] == "User One"
assert data[2]["full_name"] is None

# After - removed these assertions
```

---

### 4. tests/test_profile_endpoint.py

**Before:**
```python
mock_profile = [{
    "id": test_user_id,
    "email": "test@example.com",
    "full_name": "Test User",
    "is_admin": True,
    "created_at": "2023-01-01T00:00:00Z"
}]
```

**After:**
```python
mock_profile = [{
    "id": test_user_id,
    "email": "test@example.com",
    "is_admin": True,
    "created_at": "2023-01-01T00:00:00Z"
}]
```

**Also updated expected fields:**
```python
# Before
expected_fields = ["id", "email", "full_name", "is_admin", "created_at"]

# After
expected_fields = ["id", "email", "is_admin", "created_at"]
```

---

## Validation Results

### Before Fix:
- `/api/admin/users` → HTTP 500 (Column not found error)
- `/user/{user_id}/profile` → HTTP 500 (Column not found error)

### After Fix:
- `/api/admin/users` → HTTP 200 (Returns list of users with id and email)
- `/user/{user_id}/profile` → HTTP 200 (Returns profile with id, email, is_admin, created_at)
- All 101 tests pass successfully

## Files Modified
1. `api/admin.py` - Query and docstring updates
2. `api/privacy.py` - Query and docstring updates
3. `tests/test_admin_endpoints.py` - Mock data and assertions
4. `tests/test_profile_endpoint.py` - Mock data and expected fields

## Future Considerations
If a `full_name` column is added to the database schema in the future:
1. Update the data generator to include it when creating profiles
2. Update these queries to select it again
3. Update tests to expect it in responses
