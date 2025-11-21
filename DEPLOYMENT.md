# DEPLOYMENT.md

## Deployment Configuration for Model Serving Isolation

This document describes the optimal configuration for deploying the Bipolar API with model serving isolation features.

### Environment Variables

#### Required
- `SUPABASE_URL` - Supabase project URL
- `SUPABASE_SERVICE_KEY` - Supabase service role key

#### Optional - Performance & Caching
- `REDIS_URL` - Redis connection URL for caching (format: `redis://host:port`)
  - **Default**: None (caching disabled)
  - **Example**: `redis://localhost:6379` or `redis://red-xxxx.redis.us-east-1.amazonaws.com:6379`
  - **Recommendation**: Use Redis for production to reduce latency and database load

- `CACHE_TTL_SECONDS` - Time-to-live for cached predictions in seconds
  - **Default**: `300` (5 minutes)
  - **Recommended**: `300-1800` (5-30 minutes depending on data freshness requirements)
  
- `INFERENCE_TIMEOUT_SECONDS` - Maximum time allowed for a single prediction
  - **Default**: `30`
  - **Recommended**: `20-60` seconds

- `USE_BACKGROUND_INFERENCE` - Enable background processing for predictions
  - **Default**: `false`
  - **Values**: `true` or `false`
  - **Note**: Currently not implemented, reserved for future use

### Uvicorn/Gunicorn Configuration

#### Development (Local)
```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

#### Production (Single Worker)
For smaller deployments or when you want to maximize memory efficiency:
```bash
uvicorn main:app \
  --host 0.0.0.0 \
  --port 8000 \
  --workers 1 \
  --timeout-keep-alive 65 \
  --timeout-graceful-shutdown 10
```

#### Production (Multi-Worker with Gunicorn)
For higher concurrency and better resource utilization:
```bash
gunicorn main:app \
  --workers 2 \
  --worker-class uvicorn.workers.UvicornWorker \
  --bind 0.0.0.0:8000 \
  --timeout 120 \
  --graceful-timeout 10 \
  --keep-alive 65 \
  --max-requests 1000 \
  --max-requests-jitter 50
```

**Worker Configuration Guidelines:**
- **Workers**: Use `(2 × CPU cores) + 1` for CPU-bound workloads, but start with 2-4 workers
- **Timeout**: 120 seconds allows time for inference + database queries
- **Max Requests**: Restart workers after 1000 requests to prevent memory leaks
- **Keep-Alive**: 65 seconds to match most load balancer timeouts

### Render.com Specific Configuration

#### render.yaml Example
```yaml
services:
  - type: web
    name: bipolar-api
    env: python
    region: oregon
    plan: starter  # or higher for production
    buildCommand: pip install -r requirements.txt
    startCommand: gunicorn main:app --workers 2 --worker-class uvicorn.workers.UvicornWorker --bind 0.0.0.0:$PORT --timeout 120 --graceful-timeout 10
    envVars:
      - key: PYTHON_VERSION
        value: 3.12
      - key: SUPABASE_URL
        sync: false  # Set in dashboard
      - key: SUPABASE_SERVICE_KEY
        sync: false  # Set in dashboard
      - key: REDIS_URL
        fromService:
          name: bipolar-redis
          type: redis
          property: connectionString
      - key: CACHE_TTL_SECONDS
        value: 600  # 10 minutes
      - key: INFERENCE_TIMEOUT_SECONDS
        value: 30
```

#### Redis Add-on on Render
1. Go to your Render Dashboard
2. Click "New +" → "Redis"
3. Name it `bipolar-redis`
4. Choose the appropriate plan (free tier available for testing)
5. Link to your web service via environment variable

### Memory Optimization

The model serving isolation architecture helps prevent OOM errors:

1. **Startup Loading**: Models are loaded once at startup, not per-request
2. **Shared Memory**: All workers share the same model instances
3. **Request Limits**: `MAX_LIMIT_CHECKINS = 10` prevents excessive per-request processing
4. **Timeouts**: Prevent runaway inference from consuming resources indefinitely
5. **Caching**: Reduces redundant model inference

#### Memory Recommendations by Plan
- **Starter (512 MB)**: 1-2 workers, aggressive caching (TTL: 30 min)
- **Standard (2 GB)**: 2-4 workers, moderate caching (TTL: 10 min)
- **Pro (4+ GB)**: 4-8 workers, optional shorter cache (TTL: 5 min)

### Performance Targets

With proper configuration, the API should achieve:

- **Latency (cached)**: < 50ms
- **Latency (uncached, single user)**: < 800ms
- **Latency (uncached, 5 predictions)**: < 2s
- **Concurrency**: 20+ concurrent requests without OOM
- **Cache Hit Rate**: 60-80% for typical usage patterns

### Monitoring Recommendations

Monitor these metrics in your logs:

1. **Request Latency**: `Request completed in X.XXXs`
2. **Inference Latency**: `Prediction {type} completed in X.XXXs`
3. **Cache Performance**: `Cache HIT/MISS for user {user_id}`
4. **Model Loading**: `Model registry initialized with N models`
5. **Timeouts**: Watch for `Prediction timeout after Xs`

### Troubleshooting

#### High Memory Usage
- Reduce number of workers
- Increase `CACHE_TTL_SECONDS` to reduce redundant computation
- Check for memory leaks (workers should restart via `--max-requests`)

#### Slow Response Times
- Verify Redis is connected (check logs for "Redis connection established")
- Increase `CACHE_TTL_SECONDS`
- Consider adding more workers (if CPU is not saturated)

#### Timeouts
- Increase `INFERENCE_TIMEOUT_SECONDS`
- Increase Gunicorn `--timeout`
- Check database query performance

#### Cache Not Working
- Verify `REDIS_URL` is set correctly
- Check Redis service status
- Look for "Redis caching disabled" or connection errors in logs

### Security Considerations

1. **Never commit secrets**: Use environment variables for all sensitive data
2. **Redis Security**: Use TLS connections for Redis in production (`rediss://`)
3. **Rate Limiting**: Consider adding rate limiting middleware for production
4. **CORS**: Update allowed origins in `main.py` for your frontend domains

### Rollback Plan

If issues occur after deployment:

1. Set `REDIS_URL` to empty to disable caching
2. Reduce workers to 1
3. Increase timeout values
4. Monitor logs for specific errors

Models will still load at startup and the API will function with graceful degradation.
