# Tools Directory

This directory contains utility scripts for managing and testing the Bipolar API database.

## Prerequisites

Before running any tools, ensure you have:

1. Python 3.7 or higher installed
2. Required dependencies installed:
   ```bash
   pip install supabase
   ```

3. Environment variables configured:
   - `SUPABASE_URL`: Your Supabase project URL (e.g., `https://your-project.supabase.co`)
   - `SUPABASE_SERVICE_KEY`: Your Supabase service role key (admin access)

## Available Tools

### 1. List Users with Check-ins

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

### 2. Seed Test Check-ins

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
**Solution:** Install the supabase library:
```bash
pip install supabase
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

## Contributing

When adding new tools to this directory:
1. Follow the same structure as existing tools
2. Include clear docstrings and usage examples
3. Add confirmation prompts for destructive operations
4. Update this README with documentation for the new tool
