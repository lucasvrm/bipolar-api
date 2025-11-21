# Load Testing

This directory contains load testing scripts for the Bipolar API.

## Prerequisites

Install k6:
- **macOS**: `brew install k6`
- **Linux**: See https://k6.io/docs/getting-started/installation/
- **Windows**: `choco install k6`

## Running Tests

### Basic Test
```bash
k6 run load_tests/predictions_load_test.js
```

### Custom Configuration
```bash
# Test with 20 virtual users for 60 seconds
BASE_URL=http://localhost:8000 VUS=20 DURATION=60s k6 run load_tests/predictions_load_test.js

# Test against production
BASE_URL=https://your-api.onrender.com VUS=10 DURATION=30s k6 run load_tests/predictions_load_test.js
```

## Interpreting Results

### Key Metrics
- **http_req_duration**: Request latency (aim for p95 < 1s, ideally < 500ms)
- **http_req_failed**: Failed requests (should be < 10%)
- **request_duration**: Custom metric tracking actual processing time
- **cache_hits**: Percentage of fast responses (likely from cache)
- **errors**: Custom error rate

### Expected Performance
With caching enabled:
- **First request**: 500-800ms (cache miss, runs inference)
- **Cached requests**: < 100ms (cache hit)
- **Cache hit rate**: 60-80% under normal usage
- **Concurrency**: Should handle 20+ concurrent users without errors

### Signs of Issues
- **High error rate** (> 10%): Check logs for OOM or timeout errors
- **p95 > 1s**: Possible database slowness or heavy load
- **Low cache hit rate**: Redis might not be working
- **Timeouts**: Increase INFERENCE_TIMEOUT_SECONDS or worker timeout

## Test Scenarios

### Smoke Test (Quick sanity check)
```bash
VUS=1 DURATION=10s k6 run load_tests/predictions_load_test.js
```

### Stress Test (Find breaking point)
```bash
# Gradually increase load
VUS=50 DURATION=60s k6 run load_tests/predictions_load_test.js
```

### Spike Test (Sudden traffic)
```bash
# Modify options.stages in the script for sudden spikes
```

## Monitoring During Tests

Watch the application logs for:
- Cache hit/miss ratios
- Inference latencies
- Timeout errors
- Memory usage

Monitor system resources:
```bash
# Memory usage
docker stats  # if using Docker
htop          # if running locally
```

## Troubleshooting

### Test fails to start
- Verify API is running: `curl http://localhost:8000/`
- Check BASE_URL is correct

### High error rate
- Check API logs for errors
- Reduce VUS to see if it's a capacity issue
- Verify database/Supabase connectivity

### All requests are slow (no cache hits)
- Verify Redis is connected (check API logs)
- Ensure REDIS_URL is set correctly
- Check Redis service status
