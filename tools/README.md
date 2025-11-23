# Tools Directory

This directory contains utility scripts for managing and testing the Bipolar API database.

## Prerequisites

Before running any tools, ensure you have:

1. Python 3.7 or higher installed
2. Required dependencies installed:
   ```bash
   pip install 'supabase>=2.0.0,<3.0.0'
   ```

3. Environment variables configured:
   - `SUPABASE_URL`: Your Supabase project URL (e.g., `https://your-project.supabase.co`)
   - `SUPABASE_SERVICE_KEY`: Your Supabase service role key (admin access)

## Available Tools

### 1. Admin Endpoint Production Testing

**Script:** `test_admin_endpoints_production.py`

Executes a controlled battery of validations on administrative endpoints in PRODUCTION to confirm availability, proper authorization, basic consistency, and latencies, without modifying critical data.

**Features:**
- ✅ Generates unique correlation ID (UUID + timestamp)
- ✅ Tests positive authorization (smoke test)
- ✅ Tests negative authorization (security validation)
- ✅ Lists and validates users endpoint
- ✅ Cross-validates statistics between endpoints
- ✅ Tests filter robustness
- ✅ Measures and analyzes latencies (mean, P95, max, min, std dev)
- ✅ Validates response structures
- ✅ Generates detailed JSON report
- ✅ Generates comprehensive ROADMAP in Markdown

**Prerequisites:**
```bash
pip install requests
```

**Usage:**
```bash
export BIPOLAR_ADMIN_TOKEN="your-admin-jwt-token"
export BIPOLAR_API_URL="https://bipolar-api.onrender.com"  # Optional, defaults to production
python tools/test_admin_endpoints_production.py
```

**Output Files:**
- `report_admin_endpoints.json`: Detailed JSON report with all test results
- `ROADMAP_ADMIN_ENDPOINT_TESTS.md`: Comprehensive analysis and roadmap

**Output Example:**
```
======================================================================
🚀 ADMIN ENDPOINTS PRODUCTION TEST SUITE
======================================================================
Correlation ID: 123e4567-e89b-12d3-a456-426614174000-1700000000
Start Time: 2024-01-15T10:30:00.000000+00:00
Base URL: https://bipolar-api.onrender.com
======================================================================

🔐 [Test 1] Authorization Positive - Smoke Test
  ✅ Status: 200, Latency: 245.32ms
  📊 total_users=123, total_checkins=456

🔒 [Test 2] Authorization Negative - Security Test
  ✅ Correctly rejected with 401

👥 [Test 3] List Users (limit=50)
  ✅ Status: 200, Latency: 198.45ms
  📋 Users returned: 50, Total: 123

🔍 [Test 4] Cross-Validation: Stats vs Users
  📊 /api/admin/stats: total_users = 123
  📊 /api/admin/users: total = 123
  📊 Difference: 0 (tolerance: 2)
  ✅ Consistent (within tolerance)

🧪 [Test 5] Filter Robustness Tests
  5a. Filter by role=patient
    ✅ Returned 95 patients, Latency: 210.12ms
  5b. Filter by role=therapist
    ✅ Returned 28 therapists, Latency: 189.67ms
  5c. Invalid role filter (expect 400)
    ✅ Correctly rejected with 400

📈 [Test 6] Latency Statistics
  📊 Successful requests: 7
  📊 Mean latency: 215.34ms
  📊 P95 latency: 245.32ms
  📊 Max latency: 245.32ms
  📊 Min latency: 189.67ms
  📊 Std deviation: 20.45ms

======================================================================
📋 TEST SUMMARY
======================================================================
Total tests: 8
Successful: 7
Failed: 0
Overall Status: OK
Structural Issues: 0
Inconsistencies: 0
======================================================================

💾 Report saved to: report_admin_endpoints.json
📄 ROADMAP saved to: ROADMAP_ADMIN_ENDPOINT_TESTS.md
```

**Exit Codes:**
- `0`: All tests passed (OK)
- `1`: Some warnings found (WARN)
- `2`: Critical failures (FAIL)
- `3`: Unexpected error during execution
- `130`: Interrupted by user (Ctrl+C)

**Methodology:**
- **Mathematical:** All comparisons cite exact numbers
- **Engineering:** Organized logs and clear result structure
- **Data Engineering:** Consistency validation between metrics

**Safety:**
- ⚠️ Does NOT create, modify, or delete any data
- ⚠️ Read-only operations only
- ⚠️ Safe for production use

### 2. List Users with Check-ins

**Script:** `list_users_with_checkins.py`

Lists the top 5 user_ids that have check-ins in the database, along with their check-in counts.

**Usage:**
```bash
export SUPABASE_URL="https://your-project.supabase.co"
export SUPABASE_SERVICE_KEY="your-service-role-key"
python tools/list_users_with_checkins.py
```

**Output Example:**
```
Connecting to Supabase...
Querying check_ins table...

Total unique users with check-ins: 42
Total check-ins: 1,234

Top 5 user_ids by check-in count:
------------------------------------------------------------
User ID                                  Check-ins
------------------------------------------------------------
user-abc-123-def                                45
user-xyz-789-ghi                                38
user-mno-456-pqr                                32
user-stu-012-vwx                                28
user-yza-345-bcd                                25
------------------------------------------------------------
```

### 3. Seed Test Check-ins

**Script:** `seed_checkins.py`

Inserts N test check-ins for a specific user_id. The script generates realistic randomized data and prompts for confirmation before inserting into the database.

**Usage:**
```bash
export SUPABASE_URL="https://your-project.supabase.co"
export SUPABASE_SERVICE_KEY="your-service-role-key"
python tools/seed_checkins.py <user_id> <num_checkins>
```

**Example:**
```bash
python tools/seed_checkins.py test-user-123 10
```

**Interactive Flow:**
```
Preparing to seed 10 check-ins for user: test-user-123
------------------------------------------------------------

Preview of first check-in:
  Date: 2024-01-15T10:30:00+00:00
  Hours slept: 7.2
  Sleep quality: 7
  Energy level: 6
  Depressed mood: 3
  Anxiety/Stress: 4
------------------------------------------------------------

Insert 10 check-ins into the database? (yes/no): yes

Connecting to Supabase...
Inserting 10 check-ins...

✓ Successfully inserted 10 check-ins for user test-user-123
```

**Generated Check-in Fields:**
- `user_id`: Provided user ID
- `checkin_date`: Timestamp (spread across recent days)
- `hoursSlept`: Random value between 4.0 and 10.0
- `sleepQuality`: Random integer 1-10
- `energyLevel`: Random integer 1-10
- `depressedMood`: Random integer 0-10
- `anxietyStress`: Random integer 0-10
- `medicationAdherence`: Random integer 0-1
- `medicationTiming`: Random integer 0-1
- `compulsionIntensity`: Random integer 0-5
- `activation`: Random integer 0-10
- `elevation`: Random integer 0-10

## Security Notes

⚠️ **Important Security Considerations:**

1. **Never commit credentials**: Do not commit your `SUPABASE_SERVICE_KEY` to version control
2. **Service role key**: The service role key bypasses Row Level Security (RLS) - use with caution
3. **Production use**: Be extremely careful when using these tools against production databases
4. **Test environment**: It's recommended to use these tools against a development/staging database first

## Environment Setup

You can create a `.env` file in the project root (add it to `.gitignore`):

```bash
# .env file (DO NOT COMMIT)
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_SERVICE_KEY=your-service-role-key
```

Then load it before running tools:

```bash
# On Linux/macOS
export $(cat .env | xargs)
python tools/list_users_with_checkins.py

# Or use a tool like python-dotenv
```

## Troubleshooting

### Missing Dependencies
```
ERROR: No module named 'supabase'
```
**Solution:** Install the supabase library with the correct version:
```bash
pip install 'supabase>=2.0.0,<3.0.0'
```

### Missing Environment Variables
```
ERROR: Missing required environment variables
Please set SUPABASE_URL and SUPABASE_SERVICE_KEY
```
**Solution:** Export the required environment variables before running the script.

### Connection Errors
If you encounter connection errors, verify:
1. Your `SUPABASE_URL` is correct and accessible
2. Your `SUPABASE_SERVICE_KEY` is valid and has the necessary permissions
3. Your network allows connections to Supabase

## Architecture Notes

These CLI tools use the **synchronous** Supabase client (`create_client`, `Client`) instead of the async client (`acreate_client`, `AsyncClient`) used in the main API. This is an intentional design decision:

- **CLI tools**: Simple, one-off operations that don't benefit from async/await overhead
- **Main API**: Web service handling concurrent requests where async operations improve performance

Both approaches use the same underlying Supabase REST API with the service role key for admin-level access.

## Contributing

When adding new tools to this directory:
1. Follow the same structure as existing tools
2. Use synchronous Supabase client for simplicity in CLI tools
3. Include clear docstrings and usage examples
4. Add confirmation prompts for destructive operations
5. Update this README with documentation for the new tool
