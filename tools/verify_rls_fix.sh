#!/bin/bash
# Script to verify if the Supabase database has the infinite recursion fix applied
# Usage: ./verify_rls_fix.sh
# 
# Note: This script uses the Supabase REST API to verify the fix.
# It does NOT require direct database access.

set -e

echo "🔍 Verifying Supabase RLS Infinite Recursion Fix"
echo "================================================"
echo ""

# Check if SUPABASE_URL and SUPABASE_SERVICE_KEY are set
if [ -z "$SUPABASE_URL" ]; then
    echo "❌ Error: SUPABASE_URL environment variable not set"
    echo "   Please set it to your Supabase project URL"
    echo "   Example: export SUPABASE_URL='https://your-project.supabase.co'"
    exit 1
fi

if [ -z "$SUPABASE_SERVICE_KEY" ]; then
    echo "❌ Error: SUPABASE_SERVICE_KEY environment variable not set"
    echo "   Please set it to your Supabase service role key"
    echo "   Example: export SUPABASE_SERVICE_KEY='your-service-key'"
    exit 1
fi

echo "✅ Environment variables found"
echo ""

# Extract database connection details
PROJECT_REF=$(echo $SUPABASE_URL | sed -n 's/.*https:\/\/\([^.]*\).*/\1/p')
echo "📍 Project Reference: $PROJECT_REF"
echo ""

echo "🔍 Testing API endpoint for infinite recursion error..."



# Test the profiles endpoint
API_RESPONSE=$(curl -s -w "\n%{http_code}" "$SUPABASE_URL/rest/v1/profiles?limit=1" \
    -H "apikey: $SUPABASE_SERVICE_KEY" \
    -H "Authorization: Bearer $SUPABASE_SERVICE_KEY" 2>/dev/null)

HTTP_CODE=$(echo "$API_RESPONSE" | tail -n1)
RESPONSE_BODY=$(echo "$API_RESPONSE" | sed '$d')

echo ""
if [ "$HTTP_CODE" = "200" ]; then
    echo "✅ API responding correctly (HTTP 200)"
    echo "   No infinite recursion detected"
    HAS_ERROR=false
elif [ "$HTTP_CODE" = "500" ]; then
    echo "❌ API returning 500 error (HTTP 500)"
    if echo "$RESPONSE_BODY" | grep -qi "infinite recursion"; then
        echo "   🔴 Error message indicates INFINITE RECURSION"
        echo ""
        echo "📝 URGENT ACTION REQUIRED:"
        echo "   1. Go to Supabase SQL Editor (https://app.supabase.com)"
        echo "   2. Run migrations/010_admin_security_definer_function.sql"
        echo "   3. Re-run this script to verify the fix"
        HAS_ERROR=true
    else
        echo "   Error (not recursion): $RESPONSE_BODY"
        HAS_ERROR=true
    fi
else
    echo "⚠️  API returned HTTP $HTTP_CODE (unexpected)"
    if [ -n "$RESPONSE_BODY" ]; then
        echo "   Response: ${RESPONSE_BODY:0:200}"
    fi
    HAS_ERROR=true
fi

echo ""
echo "================================================"
if [ "$HAS_ERROR" = false ] && [ "$HTTP_CODE" = "200" ]; then
    echo "✅ VERIFICATION PASSED"
    echo "   Your database is correctly configured."
    echo "   The RLS infinite recursion fix has been applied."
    exit 0
else
    echo "⚠️  VERIFICATION FAILED"
    echo "   Some checks indicate issues with the database."
    echo "   See URGENT_FIX_INFINITE_RECURSION.md for fix instructions."
    echo "   Or run: python tools/diagnose_rls_issue.py"
    exit 1
fi
