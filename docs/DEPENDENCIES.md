# Dependencies Documentation

## Supabase Python Client

### Current Version
**Version**: `supabase==2.24.0`

### Version Justification

The Supabase Python client is pinned to version 2.x (>=2.0.0, <3.0.0) for the following reasons:

1. **API Stability**: Version 2.x provides a stable API surface that we rely on for authentication and database operations.

2. **Sync Client Migration**: Version 2.x includes both sync (`create_client`) and async (`acreate_client`) support. We've migrated to using the sync client for better reliability and simpler code.

3. **Backward Compatibility**: Staying within the 2.x range ensures we don't encounter breaking changes that would require significant refactoring.

### Migration History

**2025-11-23**: Migrated from async to sync client
- **Reason**: Intermittent async client failures ("Invalid API key", "bad_jwt")
- **Change**: Using `create_client` (sync) instead of `acreate_client` (async)
- **Compatibility**: Added `acreate_client` shim for test compatibility
- **Impact**: Removed `await` from all Supabase table operations

### Known Issues (Historical)

As of version 2.24.0, we previously observed intermittent failures with the async client:

- **Error Pattern**: "Invalid API key" errors despite valid configuration
- **JWT Errors**: "bad_jwt" errors indicating malformed tokens
- **Root Cause**: Potential race conditions or inconsistent header handling

**Status**: ✅ Resolved by migrating to sync client

### Current Implementation

1. **Synchronous Client**: Using `create_client` for all operations
2. **HTTP Fallback**: Manual HTTP-based authentication as backup (temporary)
3. **Caching**: Client instances cached globally with lazy initialization
4. **Dependency Injection**: All endpoints receive client via `Depends(get_supabase_client)`
5. **Test Shim**: `acreate_client` wrapper allows legacy test mocking

### Future Considerations

- **Monitor for Updates**: Track supabase-py releases for new features
- **Remove Fallback**: Once sync client proven stable (3+ months), remove HTTP fallback
- **Remove Test Shim**: Migrate tests to mock `get_supabase_client` directly
- **Version Upgrade**: Consider upgrading to 3.x when available, after thorough testing

### Quarterly Review Plan

- **Frequency**: Every 3 months
- **Next Review**: 2025-02-23
- **Checklist**:
  - [ ] Check supabase-py changelog for updates
  - [ ] Review open issues in GitHub repo
  - [ ] Test new version in staging
  - [ ] Update documentation if upgrading
  - [ ] Communicate changes to team

### Last Updated
2025-11-23
