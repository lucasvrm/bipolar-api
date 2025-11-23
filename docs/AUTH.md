# Authentication Flow Documentation

## Overview

This document explains the authentication and authorization flow used in the Bipolar API, with a focus on admin endpoint protection and the fallback mechanism implemented to ensure reliability.

## Authentication Architecture

### Token Verification Flow

```
1. Request arrives with Bearer token
2. Extract token from Authorization header
3. Verify token with Supabase auth service
4. Extract user email from verified token
5. Check if email is in ADMIN_EMAILS list
6. Grant or deny access based on authorization
```

### Client Types

**ANON Client**
- Purpose: User authentication and RLS-protected queries
- Key: `SUPABASE_ANON_KEY`
- Used for: `auth.get_user()` calls
- Access: Respects Row-Level Security (RLS) policies

**SERVICE ROLE Client**
- Purpose: Administrative operations bypassing RLS
- Key: `SUPABASE_SERVICE_KEY`
- Used for: Admin endpoints that need full database access
- Access: Bypasses all RLS policies
- **IMPORTANT**: NOT used for `auth.get_user()` - only ANON client should verify user tokens

## HTTP Fallback Mechanism

### Why a Fallback?

The async Supabase Python client has shown intermittent reliability issues:
- "Invalid API key" errors with valid configuration
- "bad_jwt" errors despite properly formatted tokens
- Potential race conditions in header handling

### Fallback Implementation

When the Supabase library's `auth.get_user()` fails with known error patterns, we fall back to a direct HTTP call:

```python
# api/auth_fallback.py
def supabase_get_user_http(token: str) -> dict:
    """Direct HTTP call to Supabase auth endpoint"""
    endpoint = f"{SUPABASE_URL}/auth/v1/user"
    headers = {
        "apikey": SUPABASE_ANON_KEY,
        "Authorization": f"Bearer {token}"
    }
    # Make HTTP request and return user data
```

### When Fallback is Used

The fallback is triggered only when:
1. The primary Supabase client throws an exception
2. The exception contains "Invalid API key" or similar configuration errors
3. The error is not related to the token itself being invalid

### Status Codes

The authentication system returns consistent HTTP status codes:

- **401 Unauthorized**: Token is missing, malformed, expired, or invalid
- **403 Forbidden**: Token is valid but user is not in the admin list
- **500 Internal Server Error**: Server configuration error (should trigger fallback)

## Security Considerations

### Token Safety

- Tokens are NEVER logged in full
- Only token length or short prefix is logged for debugging
- All logs sanitize sensitive information

### Key Validation

At startup, we validate:
- SUPABASE_URL is set
- SUPABASE_ANON_KEY meets minimum length (100 chars)
- SUPABASE_SERVICE_KEY meets minimum length (180 chars)
- First 16 characters of each key are logged (masked) for verification

### Admin Email List

- Stored in `ADMIN_EMAILS` environment variable
- Comma-separated list of email addresses
- Case-insensitive comparison
- Cached after first load for performance

## Temporary Nature of Fallback

The HTTP fallback is marked as **TEMPORARY** because:

1. It adds latency (extra network call on library failure)
2. It duplicates functionality that should work in the library
3. It's a workaround, not a proper solution

### Removal Criteria

The fallback should be removed when:
- Supabase Python client version demonstrates stability
- No "Invalid API key" errors occur for 30+ days in production
- Load testing confirms consistent behavior under concurrency

### Monitoring

To determine when fallback can be removed, we log:
- Each time fallback is activated (WARNING level)
- Token validation duration
- Primary vs fallback success rates

## Usage in Code

### Admin Endpoint Protection

```python
@router.get("/api/admin/stats")
async def get_stats(
    is_admin: bool = Depends(verify_admin_authorization)
):
    # Only admins reach this code
    pass
```

### Manual Verification

```python
from api.dependencies import verify_admin_authorization

# In any endpoint
is_admin = await verify_admin_authorization(authorization=auth_header)
```

## Troubleshooting

### "Invalid API key" Errors

If you see these errors:
1. Check environment variables are properly set
2. Verify keys are not truncated (check startup logs for key length)
3. Ensure no whitespace in key values
4. Check if fallback is being activated (appears in logs)

### "Missing bearer token" (401)

- Authorization header is missing or doesn't start with "Bearer "
- Check client is sending the header correctly

### "Not authorized as admin" (403)

- Token is valid but email not in ADMIN_EMAILS
- Check user's email against the configured admin list

### Rate Limiting

Admin endpoints are rate-limited separately from user endpoints. If you hit rate limits:
- Wait for the time window to reset
- Check `RATE_LIMIT_DEFAULT` configuration
- Consider if the request pattern is correct

## Related Documentation

- [DEPENDENCIES.md](./DEPENDENCIES.md) - Supabase client version information
- [../SECURITY.md](../SECURITY.md) - Overall security practices
- [../ROADMAP_AUTH_VALIDATION_FIX.md](../ROADMAP_AUTH_VALIDATION_FIX.md) - Historical context

## Last Updated
2025-11-22
