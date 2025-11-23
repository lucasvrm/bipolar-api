# Dependencies Documentation

## Supabase Python Client

### Current Version
**Version**: `supabase==2.24.0`

### Version Justification

The Supabase Python client is pinned to version 2.x (>=2.0.0, <3.0.0) for the following reasons:

1. **API Stability**: Version 2.x provides a stable API surface that we rely on for authentication and database operations.

2. **Async Support**: Version 2.x includes async client support through `acreate_client`, though we've encountered intermittent reliability issues with this implementation.

3. **Backward Compatibility**: Staying within the 2.x range ensures we don't encounter breaking changes that would require significant refactoring.

### Known Issues with Async Client

As of version 2.24.0, we've observed intermittent failures with the async client implementation:

- **Error Pattern**: "Invalid API key" errors despite valid configuration
- **JWT Errors**: "bad_jwt" errors indicating malformed tokens
- **Root Cause**: Potential race conditions or inconsistent header handling in the async client

### Mitigation Strategy

To address these issues while maintaining async FastAPI compatibility, we've implemented:

1. **Synchronous Client for Auth**: Using `create_client` (sync) instead of `acreate_client` for authentication operations
2. **HTTP Fallback**: Manual HTTP-based authentication verification using `urllib.request` as a backup
3. **Caching**: Client instances are cached to avoid recreation overhead

### Future Considerations

- **Monitor for Updates**: Track supabase-py releases for async client stability improvements
- **Remove Fallback**: Once async client is proven stable, remove HTTP fallback mechanism
- **Version Upgrade**: Consider upgrading to 3.x when available, after thorough testing

### Last Updated
2025-11-22
