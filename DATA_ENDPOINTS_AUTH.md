# Data Endpoints Authorization Requirements

This document describes the authorization requirements for the `/data/*` endpoints in the Bipolar API.

## Current State (as of 2025-11-22)

### Endpoints Overview

| Endpoint | Authorization Required | Reason |
|----------|----------------------|---------|
| `GET /data/latest_checkin/{user_id}` | **No** | Public data access for authenticated users via frontend |
| `GET /data/predictions/{user_id}` | **No** | Public data access for authenticated users via frontend |
| `GET /data/prediction_of_day/{user_id}` | **No** | Public data access for authenticated users via frontend |

### Security Model

The `/data/*` endpoints currently do **not** require `Authorization` headers at the API level. Security is implemented through:

1. **Frontend Authentication**: The frontend application (https://previso-fe.vercel.app) handles user authentication via Supabase Auth
2. **CORS Protection**: Only allowed origins can access the endpoints (production frontend + local development)
3. **Rate Limiting**: All endpoints are rate-limited to prevent abuse:
   - `/data/latest_checkin/*`: 3 requests/minute
   - `/data/predictions/*`: 3 requests/minute
   - `/data/prediction_of_day/*`: 3 requests/minute
4. **UUID Validation**: All user_id parameters are validated as proper UUIDs before processing
5. **Row-Level Security (RLS)**: Supabase enforces RLS policies at the database level, ensuring users can only access their own data

### Why No Direct Authorization Header?

The current architecture delegates authentication to:
1. **Frontend Layer**: Supabase Auth manages user sessions
2. **Database Layer**: RLS policies ensure data isolation
3. **API Layer**: CORS, rate limiting, and UUID validation provide protection

This approach:
- ✅ Simplifies API implementation
- ✅ Leverages Supabase's built-in security features
- ✅ Provides defense in depth (multiple security layers)
- ⚠️ Assumes frontend properly validates user sessions before making API calls
- ⚠️ Relies on CORS as primary access control mechanism

### Recommendations for Future Enhancement

If stricter API-level authorization is needed in the future, consider:

1. **Add JWT Validation**: Require `Authorization: Bearer <token>` header and validate Supabase JWT tokens server-side
2. **Add User Context Validation**: Verify that the authenticated user matches the `user_id` in the request
3. **Add Admin-Only Endpoints**: Create separate endpoints for admin access with role-based authorization

Example implementation (not currently active):
```python
from fastapi import Depends, HTTPException
from api.dependencies import verify_jwt_token

@router.get("/data/predictions/{user_id}")
async def get_predictions(
    user_id: str,
    current_user: dict = Depends(verify_jwt_token)
):
    # Verify user can only access their own data
    if current_user["sub"] != user_id:
        raise HTTPException(status_code=403, detail="Access forbidden")
    # ... rest of endpoint
```

### Testing Authorization

To test that the endpoints are accessible:

```bash
# Test without Authorization header (should work)
curl -H "Origin: https://previso-fe.vercel.app" \
     https://your-api.render.com/data/predictions/USER_UUID

# Test with non-allowed origin (should fail CORS)
curl -H "Origin: http://evil.com" \
     https://your-api.render.com/data/predictions/USER_UUID
```

### CORS Configuration

Current allowed origins:
- `https://previso-fe.vercel.app` (production)
- `http://localhost:3000` (development)
- `http://localhost:5173` (Vite development)

Allowed methods:
- `GET`, `POST`, `PUT`, `DELETE`, `OPTIONS`

Allowed headers:
- `Authorization`, `Content-Type`, `Accept`

Credentials: **Enabled** (`allow_credentials=True`)

### Rate Limits

Configured via environment variables:
- `RATE_LIMIT_DATA_ACCESS`: Default "3/minute"
- `RATE_LIMIT_PREDICTIONS`: Default "3/minute"

Storage: In-memory for development, Redis for production (via `RATE_LIMIT_STORAGE_URI`)

## Decision Log

**Date**: 2025-11-22  
**Decision**: Keep data endpoints without Authorization header requirement  
**Rationale**: 
- Frontend handles authentication via Supabase Auth
- Database RLS policies enforce data isolation
- CORS provides access control at API level
- Simpler implementation reduces attack surface
- Rate limiting prevents abuse

**Risks**:
- If CORS is misconfigured, endpoints could be accessed from unauthorized origins
- No server-side validation that user owns the requested data (relies on RLS)

**Mitigations**:
- Comprehensive CORS tests verify configuration
- Explicit origin allowlist (no wildcards)
- Rate limiting prevents enumeration attacks
- UUID validation prevents invalid requests

**Review Date**: 2025-12-22 (revisit in 1 month)
