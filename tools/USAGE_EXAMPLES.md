# Admin Endpoint Production Testing - Usage Examples

This document provides detailed usage examples for the `test_admin_endpoints_production.py` script.

> **📖 Need help with the admin token?** See **[BIPOLAR_ADMIN_TOKEN_GUIDE.md](BIPOLAR_ADMIN_TOKEN_GUIDE.md)** for a complete guide on obtaining and using the admin token.

## Quick Start

### Basic Usage

1. **Set the admin token:**
   
   See **[BIPOLAR_ADMIN_TOKEN_GUIDE.md](BIPOLAR_ADMIN_TOKEN_GUIDE.md)** for detailed instructions.
   
   ```bash
   # Quick method - login and extract token
   export BIPOLAR_ADMIN_TOKEN=$(curl -s -X POST https://bipolar-api.onrender.com/api/auth/login \
     -H "Content-Type: application/json" \
     -d '{"email":"admin@example.com","password":"your-password"}' \
     | jq -r '.access_token')
   
   # Or use existing token
   export BIPOLAR_ADMIN_TOKEN="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
   ```

2. **Run the tests:**
   ```bash
   python tools/test_admin_endpoints_production.py
   ```

3. **Check the results:**
   - Console output shows real-time test progress
   - `report_admin_endpoints.json` contains detailed JSON report
   - `ROADMAP_ADMIN_ENDPOINT_TESTS.md` contains comprehensive analysis

## Advanced Usage

### Testing Against Different Environments

**Production (default):**
```bash
export BIPOLAR_ADMIN_TOKEN="your-token"
python tools/test_admin_endpoints_production.py
```

**Staging:**
```bash
export BIPOLAR_ADMIN_TOKEN="your-staging-token"
export BIPOLAR_API_URL="https://staging-bipolar-api.example.com"
python tools/test_admin_endpoints_production.py
```

**Local Development:**
```bash
export BIPOLAR_ADMIN_TOKEN="your-dev-token"
export BIPOLAR_API_URL="http://localhost:8000"
python tools/test_admin_endpoints_production.py
```

## Interpreting Results

### Exit Codes

The script uses exit codes to indicate overall test status:

| Exit Code | Status | Meaning |
|-----------|--------|---------|
| 0 | OK | All tests passed successfully |
| 1 | WARN | Tests passed but warnings found (inconsistencies, structural issues) |
| 2 | FAIL | Critical failures detected (security issues, server errors) |
| 3 | ERROR | Unexpected error during execution |
| 130 | INTERRUPTED | User interrupted execution (Ctrl+C) |

### Console Output

#### Successful Test Example
```
🔐 [Test 1] Authorization Positive - Smoke Test
  ✅ Status: 200, Latency: 245.32ms
  📊 total_users=123, total_checkins=456
```

#### Failed Test Example
```
👥 [Test 3] List Users (limit=50)
  ❌ Failed: HTTP 500
```

#### Warning Example
```
🔍 [Test 4] Cross-Validation: Stats vs Users
  📊 /api/admin/stats: total_users = 125
  📊 /api/admin/users: total = 123
  📊 Difference: 2 (tolerance: 2)
  ✅ Consistent (within tolerance)
```

### JSON Report Structure

The `report_admin_endpoints.json` file contains:

```json
{
  "correlation_id": "123e4567-e89b-12d3-a456-426614174000-1700000000",
  "start_time_utc": "2024-01-15T10:30:00.000000+00:00",
  "end_time_utc": "2024-01-15T10:30:15.000000+00:00",
  "endpoints_tested": [
    {
      "endpoint": "/api/admin/stats",
      "method": "GET",
      "status_code": 200,
      "latency_ms": 245.32,
      "success": true,
      "timestamp": "2024-01-15T10:30:05.000000+00:00"
    }
  ],
  "latencies": {
    "meanMs": 215.34,
    "p95Ms": 245.32,
    "maxMs": 245.32,
    "minMs": 189.67,
    "stdDevMs": 20.45,
    "sampleSize": 7
  },
  "authorization_negative_result": {
    "expected": [401, 403],
    "obtained": 401,
    "status": "PASS"
  },
  "structural_issues": [],
  "inconsistencies": [],
  "overall_status": "OK"
}
```

### ROADMAP Document

The `ROADMAP_ADMIN_ENDPOINT_TESTS.md` file contains:

- **Execution Summary:** Correlation ID, date, overall status
- **What Was Requested:** Checklist of requirements
- **What Was Executed:** Detailed test results for each endpoint
- **Latency Analysis:** Statistical breakdown
- **Authorization Test:** Security validation results
- **Issues Found:** Structural and consistency issues (if any)
- **What Could NOT Be Tested:** Endpoints excluded for safety
- **Suggested Next Steps:** Recommendations for improvement
- **Comparison Table:** Requested vs Executed features

## Use Cases

### 1. Continuous Monitoring

Run the script on a schedule (e.g., via cron) to monitor endpoint health:

```bash
#!/bin/bash
# monitor_endpoints.sh

# Load credentials from secure vault
export BIPOLAR_ADMIN_TOKEN=$(get-secret bipolar-admin-token)

# Run tests
python tools/test_admin_endpoints_production.py

# Check exit code
if [ $? -eq 0 ]; then
    echo "✅ All tests passed"
else
    echo "⚠️ Tests failed - check logs"
    # Send alert to monitoring system
    send-alert "Admin endpoints test failed"
fi
```

### 2. Pre-Deployment Validation

Validate endpoints before deploying changes:

```bash
#!/bin/bash
# pre_deploy_check.sh

echo "Testing staging environment..."
export BIPOLAR_API_URL="https://staging-bipolar-api.example.com"
export BIPOLAR_ADMIN_TOKEN=$(get-secret staging-admin-token)

python tools/test_admin_endpoints_production.py

if [ $? -eq 0 ]; then
    echo "✅ Staging tests passed - proceeding with deployment"
    exit 0
else
    echo "❌ Staging tests failed - blocking deployment"
    exit 1
fi
```

### 3. Performance Baseline

Establish performance baselines by running tests multiple times:

```bash
#!/bin/bash
# baseline_performance.sh

export BIPOLAR_ADMIN_TOKEN=$(get-secret bipolar-admin-token)

for i in {1..10}; do
    echo "Run $i/10"
    python tools/test_admin_endpoints_production.py > /dev/null 2>&1
    
    # Extract mean latency from report
    mean_latency=$(jq -r '.latencies.meanMs' report_admin_endpoints.json)
    echo "$i,$mean_latency" >> latency_baseline.csv
    
    sleep 60  # Wait 1 minute between runs
done

echo "Baseline data saved to latency_baseline.csv"
```

### 4. CI/CD Integration

Integrate into your CI/CD pipeline:

```yaml
# .github/workflows/test-admin-endpoints.yml
name: Admin Endpoint Tests

on:
  schedule:
    - cron: '0 */6 * * *'  # Every 6 hours
  workflow_dispatch:  # Manual trigger

jobs:
  test-endpoints:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      
      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.12'
      
      - name: Install dependencies
        run: pip install requests
      
      - name: Run admin endpoint tests
        env:
          BIPOLAR_ADMIN_TOKEN: ${{ secrets.ADMIN_TOKEN }}
          BIPOLAR_API_URL: ${{ secrets.API_URL }}
        run: python tools/test_admin_endpoints_production.py
      
      - name: Upload test results
        if: always()
        uses: actions/upload-artifact@v3
        with:
          name: test-results
          path: |
            report_admin_endpoints.json
            ROADMAP_ADMIN_ENDPOINT_TESTS.md
      
      - name: Notify on failure
        if: failure()
        uses: 8398a7/action-slack@v3
        with:
          status: ${{ job.status }}
          text: 'Admin endpoint tests failed!'
          webhook_url: ${{ secrets.SLACK_WEBHOOK }}
```

## Troubleshooting

### Issue: "BIPOLAR_ADMIN_TOKEN environment variable not found"

**Solution:**

See the complete guide: **[BIPOLAR_ADMIN_TOKEN_GUIDE.md](BIPOLAR_ADMIN_TOKEN_GUIDE.md)**

**Quick fix:**
```bash
# Get token via login
export BIPOLAR_ADMIN_TOKEN=$(curl -s -X POST https://bipolar-api.onrender.com/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@example.com","password":"your-password"}' \
  | jq -r '.access_token')

# Or set manually
export BIPOLAR_ADMIN_TOKEN='your-admin-jwt-token'
```

Make sure the token is a valid JWT token for an admin user. The token should:
- Start with `eyJ` (Base64 encoded JWT)
- Be obtained from a user with admin privileges
- Not be expired (JWT tokens have expiration timestamps)

To verify your admin status, check:
1. Your email is listed in the `ADMIN_EMAILS` environment variable on the server
2. You can successfully call admin endpoints manually with the token:
   ```bash
   curl -H "Authorization: Bearer $BIPOLAR_ADMIN_TOKEN" \
     https://bipolar-api.onrender.com/api/admin/stats
   ```

### Issue: Connection timeouts

**Symptoms:**
```
❌ Failed: Request timeout
```

**Possible Causes:**
1. Network connectivity issues
2. API server is down or slow
3. Firewall blocking the connection

**Solutions:**
- Check network connectivity: `ping bipolar-api.onrender.com`
- Verify API is responding: `curl https://bipolar-api.onrender.com/health`
- Check firewall rules

### Issue: "Correctly rejected with 200" (Security Issue)

**Symptoms:**
```
❌ CRITICAL: Accepted invalid token (returned 200)
```

**This is a serious security vulnerability!**

**Actions:**
1. Immediately investigate the admin authorization middleware
2. Check `api/dependencies.py` - `verify_admin_authorization` function
3. Verify token validation is working correctly
4. Review recent changes to auth code

### Issue: Inconsistent user counts

**Symptoms:**
```
⚠️ User count mismatch: stats.total_users=125 vs users.total=123 (diff=3, tolerance=2)
```

**Possible Causes:**
1. Database replication lag
2. Users being created/deleted during test execution
3. Caching issues in stats endpoint

**Solutions:**
- Re-run the test to see if inconsistency persists
- Check database replication status
- Review cache invalidation logic

### Issue: High latencies

**Symptoms:**
```
📊 Mean latency: 5234.56ms
📊 P95 latency: 8901.23ms
```

**Possible Causes:**
1. Database performance issues
2. Cold start (serverless platforms)
3. Network latency
4. Heavy load on the server

**Solutions:**
- Check database query performance
- Review server logs for slow queries
- Consider implementing caching
- Scale up server resources if needed

## Best Practices

### 1. Security

- **Never commit tokens:** Don't hardcode `BIPOLAR_ADMIN_TOKEN` in scripts
- **Use secret management:** Store tokens in secure vaults (AWS Secrets Manager, HashiCorp Vault, etc.)
- **Rotate tokens regularly:** Change admin tokens periodically
- **Limit token scope:** Use tokens with minimal required permissions

### 2. Automation

- **Schedule regular runs:** Set up cron jobs or CI/CD pipelines
- **Monitor trends:** Track latency and success rates over time
- **Alert on failures:** Integrate with monitoring systems (Slack, PagerDuty, etc.)
- **Archive reports:** Keep historical data for trend analysis

### 3. Analysis

- **Establish baselines:** Know what "normal" looks like
- **Investigate anomalies:** Don't ignore warnings
- **Track correlation IDs:** Use them to correlate issues across systems
- **Review ROADMAPs:** The ROADMAP document contains valuable insights

### 4. Continuous Improvement

- **Act on suggestions:** The ROADMAP includes "Suggested Next Steps"
- **Expand coverage:** Add more endpoint tests as needed
- **Refine thresholds:** Adjust tolerances based on observed patterns
- **Update documentation:** Keep this guide current

## Metrics Reference

### Latency Metrics

- **Mean (meanMs):** Average latency across all successful requests
- **P95 (p95Ms):** 95th percentile - 95% of requests are faster than this
- **Max (maxMs):** Slowest request
- **Min (minMs):** Fastest request
- **Std Dev (stdDevMs):** Variability in latency (lower is better)

**Interpretation:**
- Mean < 500ms: Good
- Mean 500-1000ms: Acceptable
- Mean > 1000ms: Needs optimization

- P95 < 1000ms: Good
- P95 1000-2000ms: Acceptable
- P95 > 2000ms: Needs attention

### Success Rates

- **100%:** All tests passed - excellent
- **90-99%:** Some failures - investigate
- **< 90%:** Significant issues - urgent action required

### Consistency Tolerance

The script uses a tolerance of ±2 for user count comparisons between endpoints. This accounts for:
- Database replication lag
- Concurrent user creation/deletion
- Caching delays

If inconsistencies exceed tolerance consistently, investigate:
- Replication configuration
- Cache invalidation logic
- Transaction isolation levels

## Examples of Real Issues Found

### Example 1: Missing Field in Response

```
⚠️ /api/admin/stats: Missing fields: real_patients_count
```

**Action:** Update the endpoint to include the missing field.

### Example 2: Authorization Bypass

```
❌ CRITICAL: Accepted invalid token (returned 200)
```

**Action:** Fix the `verify_admin_authorization` dependency immediately.

### Example 3: Performance Degradation

```
📊 Mean latency: 3456.78ms (previously: 234.56ms)
```

**Action:** 
1. Check database query performance
2. Review recent code changes
3. Check server resource utilization
4. Consider adding indexes or caching

## Support

For issues or questions:
1. Check this documentation first
2. Review the ROADMAP document generated by the script
3. Open an issue in the repository with:
   - The correlation ID from the test run
   - The `report_admin_endpoints.json` file
   - The console output
   - Your environment details (API URL, Python version, etc.)
