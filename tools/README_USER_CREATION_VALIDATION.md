# Test User Creation Validation Tool

## Overview

A comprehensive validation script that tests the backend's ability to create exactly N test users as requested, ensuring uniqueness, traceability via prefix, and correct count post-creation.

## Features

- **Parameter Validation**: Validates requested count and prefix against safety limits
- **Baseline Capture**: Records existing user count before creation
- **User Creation**: Creates users via admin API (with fallback for missing bulk endpoint)
- **Post-Creation Verification**: Confirms users were actually persisted in database
- **Discrepancy Detection**: Identifies missing users, duplicates, and mismatches
- **Performance Metrics**: Tracks latency (mean, max, p95, p99) and error rates
- **Invariant Validation**: Ensures mathematical invariants are maintained
- **Comprehensive Reporting**: Generates JSON report and ROADMAP markdown

## Usage

### Basic Usage

```bash
# Create 5 test users with default prefix (zz-test)
python tools/test_user_creation_validation.py --count 5

# Create 10 test users with custom prefix
python tools/test_user_creation_validation.py --count 10 --prefix my-test
```

### Advanced Usage

```bash
# Specify custom output locations
python tools/test_user_creation_validation.py \
    --count 5 \
    --prefix zz-test \
    --output /tmp/report.json \
    --roadmap-output /tmp/ROADMAP.md

# Use custom API URL and admin token
python tools/test_user_creation_validation.py \
    --count 3 \
    --api-url https://myapi.example.com \
    --admin-token "your-jwt-token"

# Enable verbose logging
python tools/test_user_creation_validation.py \
    --count 5 \
    --verbose
```

## Requirements

### Environment Variables

```bash
# Required
export SUPABASE_URL="https://your-project.supabase.co"
export SUPABASE_SERVICE_KEY="your-service-role-key"

# Optional
export APP_ENV="development"  # or "production" (limits count to 10)
```

### Dependencies

All dependencies are already in `requirements.txt`:
- `supabase` - Database client
- `httpx` - Async HTTP client
- `pytest` - For tests

## Output

### JSON Report

The script generates a comprehensive JSON report (`report_user_creation.json`) with:

```json
{
  "correlation_id": "test-20241123-131700",
  "timestamp": "2024-11-23T13:17:00Z",
  "duration_seconds": 5.23,
  "parameters": {
    "requested_count": 5,
    "prefix": "zz-test",
    "app_env": "development"
  },
  "baseline": {
    "count_before": 0,
    "count_after": 5,
    "baseline_timestamp": "2024-11-23T13:17:00Z"
  },
  "creation": {
    "method": "loop",
    "created_user_ids": ["id1", "id2", "id3", "id4", "id5"],
    "total_created": 5
  },
  "discrepancy": {
    "has_discrepancy": false,
    "requested_count": 5,
    "actual_created": 5,
    "difference": 0
  },
  "latencies": {
    "mean_ms": 145.3,
    "max_ms": 234.5,
    "p95_ms": 201.2
  },
  "error_summary": {
    "total_errors": 0,
    "network_timeouts": 0,
    "server_errors": 0,
    "validation_errors": 0
  },
  "invariant_violations": [],
  "overall_status": "OK"
}
```

### ROADMAP Markdown

The script also generates a ROADMAP document (`ROADMAP_USER_CREATION.md`) with:

- Test parameters and configuration
- Execution summary
- Performance metrics
- Discrepancy analysis
- Invariant validation results
- Next steps and recommendations

## Status Codes

The script exits with different codes based on results:

- `0` - OK: All validations passed
- `1` - FAIL: Critical issues (e.g., count mismatch, creation failed)
- `2` - WARN: Non-critical issues (e.g., some users failed but majority succeeded)

## Safety Features

### Production Limits

In production environment (when `APP_ENV=production`):
- Maximum user creation limited to 10 users
- Prevents accidental mass creation in production

### Validation

- Validates count is positive integer ≤ 500
- Validates prefix is at least 2 characters
- Checks for bulk endpoint before attempting creation
- Implements proper error handling and retry logic

### Mathematical Invariants

The script validates:

1. **Unique User IDs**: No duplicate IDs in created users
2. **Baseline Count**: `(baseline_before + created) ≥ baseline_after`
3. **Prefix Matching**: All created usernames match the specified prefix

## Testing

Run the comprehensive test suite:

```bash
# Run all tests
python -m pytest tests/test_user_creation_validation.py -v

# Run specific test class
python -m pytest tests/test_user_creation_validation.py::TestParameterValidation -v

# Run with coverage
python -m pytest tests/test_user_creation_validation.py --cov=tools.test_user_creation_validation
```

## Implementation Details

### Workflow

1. **Parameter Validation**: Validate input parameters
2. **Baseline Capture**: Count existing users with prefix (last 24h)
3. **Bulk Endpoint Check**: Check for `/api/admin/users/bulk` endpoint
4. **User Creation**:
   - If bulk endpoint exists: Use bulk creation
   - Otherwise: Loop through and create individually
5. **Post-Creation Verification**: Query database for created users
6. **Analysis**: Compare requested vs actual counts
7. **Report Generation**: Create JSON and ROADMAP documents

### User Creation Pattern

Each user is created with:
- **Username**: `{prefix}-{timestamp}-{index}`
- **Email**: `{username}@example.com`
- **Full Name**: `Test Auto {index}`
- **Role**: `patient`
- **Password**: Auto-generated secure password

### Error Handling

The script tracks and categorizes errors:
- **Network Timeouts**: HTTP request timeouts
- **Server Errors**: 5xx responses from API
- **Validation Errors**: Missing required fields in response
- **Rate Limiting**: 429 responses (with exponential backoff)

## Limitations

### Current Limitations

- **No Bulk Endpoint**: Current implementation doesn't have `/api/admin/users/bulk`, so uses loop-based creation
- **No Automatic Cleanup**: Test users are not automatically deleted (requires manual cleanup)
- **No Idempotency**: Rerunning creates new users (no idempotency key support)
- **No Distributed Tracing**: Correlation ID is not propagated to backend logs

### Future Improvements

Planned enhancements (see ROADMAP):

1. Implement bulk user creation endpoint
2. Add idempotency keys to prevent duplicates
3. Implement automatic rollback on partial failure
4. Add distributed tracing with correlation IDs
5. Implement retry logic with exponential backoff
6. Create automated cleanup script
7. Add rate limit handling and backoff strategy

## Troubleshooting

### Common Issues

**Issue**: `Missing required environment variables`
```bash
# Solution: Set environment variables
export SUPABASE_URL="https://your-project.supabase.co"
export SUPABASE_SERVICE_KEY="your-key"
```

**Issue**: `Rate limit exceeded`
```bash
# Solution: Reduce count or wait between runs
python tools/test_user_creation_validation.py --count 3  # Smaller count
```

**Issue**: `Production limit exceeded`
```bash
# Solution: Use development environment or reduce count
export APP_ENV="development"
# OR
python tools/test_user_creation_validation.py --count 10  # Max for production
```

## Examples

### Example 1: Basic Validation

```bash
$ python tools/test_user_creation_validation.py --count 3
======================================================================
Test User Creation Validation
======================================================================
INFO: Starting validation: count=3, prefix=zz-test
INFO: Capturing baseline for prefix: zz-test
INFO: Baseline count: 0 users with prefix 'zz-test' (last 24h)
INFO: No bulk endpoint available, will use loop-based creation
INFO: Using loop-based creation
INFO: Verifying post-creation user count...
INFO: Post-creation count: 3 users with prefix 'zz-test'
INFO: JSON report saved to: report_user_creation.json
INFO: ROADMAP saved to: ROADMAP_USER_CREATION.md
======================================================================
Validation Status: OK
Requested: 3 | Created: 3
Errors: 0
======================================================================
```

### Example 2: With Discrepancies

```bash
$ python tools/test_user_creation_validation.py --count 5
# ... (some creations fail) ...
Validation Status: FAIL
Requested: 5 | Created: 3
Errors: 2
```

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│              test_user_creation_validation.py           │
└─────────────────────────────────────────────────────────┘
                           │
        ┌──────────────────┼──────────────────┐
        │                  │                  │
┌───────▼────────┐ ┌──────▼──────┐ ┌────────▼──────────┐
│  Parameter     │ │  Baseline   │ │  User Creation    │
│  Validation    │ │  Capture    │ │  (Loop/Bulk)      │
└────────────────┘ └─────────────┘ └───────────────────┘
                           │
        ┌──────────────────┼──────────────────┐
        │                  │                  │
┌───────▼────────┐ ┌──────▼──────┐ ┌────────▼──────────┐
│  Post-Creation │ │  Discrepancy│ │  Invariant        │
│  Verification  │ │  Analysis   │ │  Validation       │
└────────────────┘ └─────────────┘ └───────────────────┘
                           │
        ┌──────────────────┴──────────────────┐
        │                                     │
┌───────▼────────┐                   ┌───────▼──────────┐
│  JSON Report   │                   │  ROADMAP.md      │
│  Generation    │                   │  Generation      │
└────────────────┘                   └──────────────────┘
```

## Contributing

Improvements and bug fixes are welcome! Please:

1. Run the test suite before submitting
2. Add tests for new functionality
3. Update this README with new features
4. Follow existing code style

## License

This tool is part of the bipolar-api project and follows the same license.

---

**Version**: 1.0.0  
**Last Updated**: 2024-11-23
