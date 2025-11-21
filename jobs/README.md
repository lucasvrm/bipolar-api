# Scheduled Jobs

This directory contains scheduled jobs for background processing tasks.

## Jobs

### scheduled_deletion.py

Daily job that processes hard deletions for accounts that have passed their 14-day grace period.

**What it does:**
1. Finds all profiles where `deletion_scheduled_at <= now()` and `deleted_at IS NULL`
2. For each user, performs cascading hard delete in this order:
   - check_ins
   - crisis_plan
   - clinical_notes (both as patient and therapist)
   - therapist_patients (both as patient and therapist)
   - user_consent
   - profiles
3. Logs audit event with action='hard_deleted'
4. Returns statistics about the job execution

**Running the job:**

```bash
# Set environment variables
export SUPABASE_URL="your-supabase-url"
export SUPABASE_SERVICE_KEY="your-service-key"

# Run the job manually
python -m jobs.scheduled_deletion
```

**Scheduling Options:**

### Option 1: pg_cron (PostgreSQL)
```sql
-- Create the cron job (runs daily at 2 AM UTC)
SELECT cron.schedule(
  'hard-delete-scheduled-accounts',
  '0 2 * * *',
  $$
  -- Call your Supabase Edge Function or API endpoint that runs the job
  SELECT net.http_post(
    url := 'https://your-api.com/api/admin/run-deletion-job',
    headers := '{"Authorization": "Bearer your-service-key"}'::jsonb
  );
  $$
);
```

### Option 2: Supabase Edge Function
Deploy as a Supabase Edge Function and invoke via cron:

```typescript
// supabase/functions/scheduled-deletion/index.ts
import { serve } from "https://deno.land/std@0.168.0/http/server.ts"

serve(async (req) => {
  // Call your Python API endpoint
  const response = await fetch('https://your-api.com/api/admin/run-deletion-job', {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${Deno.env.get('SERVICE_KEY')}`
    }
  });
  
  const data = await response.json();
  return new Response(JSON.stringify(data), {
    headers: { 'Content-Type': 'application/json' }
  });
});
```

### Option 3: External Cron Service
Use services like:
- GitHub Actions (scheduled workflow)
- Vercel Cron
- AWS CloudWatch Events
- Google Cloud Scheduler

Example GitHub Actions workflow:
```yaml
name: Scheduled Account Deletion
on:
  schedule:
    - cron: '0 2 * * *'  # Daily at 2 AM UTC
  workflow_dispatch:  # Allow manual trigger

jobs:
  delete-accounts:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
        with:
          python-version: '3.12'
      - name: Install dependencies
        run: pip install -r requirements.txt
      - name: Run deletion job
        env:
          SUPABASE_URL: ${{ secrets.SUPABASE_URL }}
          SUPABASE_SERVICE_KEY: ${{ secrets.SUPABASE_SERVICE_KEY }}
        run: python -m jobs.scheduled_deletion
```

## Monitoring

Monitor job execution through:
1. Job output logs (stdout/stderr)
2. audit_log table entries with action='hard_deleted'
3. Application logs
4. Alert on errors in the stats['errors'] array

## Testing

Test the job locally before scheduling:

```python
import asyncio
from jobs.scheduled_deletion import process_scheduled_deletions

async def test():
    stats = await process_scheduled_deletions()
    print(f"Test results: {stats}")

asyncio.run(test())
```
