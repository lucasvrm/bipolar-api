#!/bin/bash
# Script to verify if the Supabase database has the infinite recursion fix applied
# Usage: ./verify_rls_fix.sh

set -e

echo "🔍 Verifying Supabase RLS Infinite Recursion Fix"
echo "================================================"
echo ""

# Check if SUPABASE_URL and SUPABASE_SERVICE_KEY are set
if [ -z "$SUPABASE_URL" ]; then
    echo "❌ Error: SUPABASE_URL environment variable not set"
    echo "   Please set it to your Supabase project URL"
    exit 1
fi

if [ -z "$SUPABASE_SERVICE_KEY" ]; then
    echo "❌ Error: SUPABASE_SERVICE_KEY environment variable not set"
    echo "   Please set it to your Supabase service role key"
    exit 1
fi

echo "✅ Environment variables found"
echo ""

# Extract database connection details
PROJECT_REF=$(echo $SUPABASE_URL | sed -n 's/.*https:\/\/\([^.]*\).*/\1/p')
echo "📍 Project Reference: $PROJECT_REF"
echo ""

# Function to run SQL query via Supabase REST API
run_query() {
    local query=$1
    curl -s \
        -X POST \
        "$SUPABASE_URL/rest/v1/rpc/exec_sql" \
        -H "apikey: $SUPABASE_SERVICE_KEY" \
        -H "Authorization: Bearer $SUPABASE_SERVICE_KEY" \
        -H "Content-Type: application/json" \
        -d "{\"query\": \"$query\"}"
}

echo "🔍 Checking for is_admin() function..."
IS_ADMIN_EXISTS=$(psql "$DATABASE_URL" -tAc "SELECT EXISTS (SELECT 1 FROM pg_proc WHERE proname = 'is_admin');" 2>/dev/null || echo "")

if [ "$IS_ADMIN_EXISTS" = "t" ]; then
    echo "✅ is_admin() function exists"
    
    # Check if it's SECURITY DEFINER
    SECURITY_DEFINER=$(psql "$DATABASE_URL" -tAc "SELECT prosecdef FROM pg_proc WHERE proname = 'is_admin';" 2>/dev/null || echo "")
    if [ "$SECURITY_DEFINER" = "t" ]; then
        echo "✅ is_admin() is SECURITY DEFINER (correct)"
    else
        echo "⚠️  is_admin() exists but is NOT SECURITY DEFINER (incorrect)"
        echo "   Migration 010 may need to be re-applied"
    fi
else
    echo "❌ is_admin() function NOT found"
    echo "   Migration 010 needs to be applied"
    echo ""
    echo "📝 ACTION REQUIRED:"
    echo "   1. Go to Supabase SQL Editor"
    echo "   2. Run migrations/010_admin_security_definer_function.sql"
    echo "   3. Re-run this script to verify"
    exit 1
fi

echo ""
echo "🔍 Checking admin RLS policies..."

# Check if policies use the is_admin() function
POLICY_CHECK=$(psql "$DATABASE_URL" -tAc "
SELECT COUNT(*) 
FROM pg_policies 
WHERE tablename = 'profiles' 
  AND policyname = 'admin_full_access_profiles'
  AND (
    pg_get_expr(qual, 'public.profiles'::regclass) LIKE '%is_admin%'
    OR pg_get_expr(with_check, 'public.profiles'::regclass) LIKE '%is_admin%'
  );
" 2>/dev/null || echo "0")

if [ "$POLICY_CHECK" -gt "0" ]; then
    echo "✅ Profiles policy uses is_admin() function (correct)"
else
    echo "⚠️  Profiles policy may not be using is_admin() function"
    echo "   This could cause infinite recursion"
    echo "   Migration 010 should be applied/re-applied"
fi

echo ""
echo "🔍 Testing API endpoint..."

# Test a simple API endpoint
API_RESPONSE=$(curl -s -w "\n%{http_code}" "$SUPABASE_URL/rest/v1/profiles?limit=1" \
    -H "apikey: $SUPABASE_SERVICE_KEY" \
    -H "Authorization: Bearer $SUPABASE_SERVICE_KEY")

HTTP_CODE=$(echo "$API_RESPONSE" | tail -n1)
RESPONSE_BODY=$(echo "$API_RESPONSE" | sed '$d')

if [ "$HTTP_CODE" = "200" ]; then
    echo "✅ API responding correctly (HTTP 200)"
elif [ "$HTTP_CODE" = "500" ]; then
    echo "❌ API returning 500 error"
    if echo "$RESPONSE_BODY" | grep -q "infinite recursion"; then
        echo "   Error message indicates INFINITE RECURSION"
        echo ""
        echo "📝 URGENT ACTION REQUIRED:"
        echo "   Run migrations/010_admin_security_definer_function.sql in Supabase SQL Editor"
    else
        echo "   Error: $RESPONSE_BODY"
    fi
else
    echo "⚠️  API returned HTTP $HTTP_CODE"
    echo "   Response: $RESPONSE_BODY"
fi

echo ""
echo "================================================"
if [ "$IS_ADMIN_EXISTS" = "t" ] && [ "$SECURITY_DEFINER" = "t" ] && [ "$HTTP_CODE" = "200" ]; then
    echo "✅ All checks passed! Database is correctly configured."
else
    echo "⚠️  Some checks failed. Review the output above."
    echo "   See URGENT_FIX_INFINITE_RECURSION.md for instructions."
fi
