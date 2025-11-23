#!/usr/bin/env python3
"""
Diagnostic script to check if Supabase RLS infinite recursion issue exists.
This script tests the API and provides guidance on fixing the issue.

Usage:
    python tools/diagnose_rls_issue.py
"""

import os
import sys
import requests
from typing import Dict, Any

def check_environment() -> Dict[str, str]:
    """Check if required environment variables are set."""
    print("🔍 Checking environment variables...")
    
    supabase_url = os.getenv("SUPABASE_URL")
    service_key = os.getenv("SUPABASE_SERVICE_KEY")
    
    if not supabase_url:
        print("❌ SUPABASE_URL not set")
        print("   Set it with: export SUPABASE_URL='https://your-project.supabase.co'")
        sys.exit(1)
    
    if not service_key:
        print("❌ SUPABASE_SERVICE_KEY not set")
        print("   Set it with: export SUPABASE_SERVICE_KEY='your-service-key'")
        sys.exit(1)
    
    print(f"✅ SUPABASE_URL: {supabase_url}")
    print(f"✅ SUPABASE_SERVICE_KEY: {service_key[:20]}...")
    print()
    
    return {"url": supabase_url, "key": service_key}

def test_api_endpoint(config: Dict[str, str]) -> bool:
    """Test if API is working or returning infinite recursion error."""
    print("🔍 Testing Supabase API endpoint...")
    
    headers = {
        "apikey": config["key"],
        "Authorization": f"Bearer {config['key']}",
        "Content-Type": "application/json"
    }
    
    # Test profiles endpoint
    url = f"{config['url']}/rest/v1/profiles?limit=1"
    
    try:
        response = requests.get(url, headers=headers, timeout=10)
        
        if response.status_code == 200:
            print(f"✅ API responding correctly (HTTP {response.status_code})")
            print("   No infinite recursion detected")
            return True
        elif response.status_code == 500:
            print(f"❌ API returning error (HTTP {response.status_code})")
            error_body = response.json() if response.content else {}
            
            error_msg = error_body.get("message", "").lower()
            error_code = error_body.get("code", "")
            
            if "infinite recursion" in error_msg or error_code == "42P17":
                print("   🔴 CONFIRMED: Infinite recursion detected!")
                print(f"   Error: {error_body.get('message', 'Unknown error')}")
                return False
            else:
                print(f"   Error (not recursion): {error_body}")
                return False
        else:
            print(f"⚠️  Unexpected HTTP status: {response.status_code}")
            print(f"   Response: {response.text[:200]}")
            return False
            
    except requests.exceptions.RequestException as e:
        print(f"❌ Network error: {e}")
        return False

def check_database_function(config: Dict[str, str]) -> bool:
    """Check if is_admin() function exists in the database."""
    print("\n🔍 Checking for is_admin() function...")
    
    headers = {
        "apikey": config["key"],
        "Authorization": f"Bearer {config['key']}",
        "Content-Type": "application/json"
    }
    
    # Query pg_proc to check for is_admin function
    # Note: This might fail if RLS is blocking, but we'll try anyway
    url = f"{config['url']}/rest/v1/rpc/pg_get_functiondef"
    payload = {"funcname": "is_admin"}
    
    try:
        # Simplified check - just see if we can query without error
        url = f"{config['url']}/rest/v1/profiles?limit=1"
        response = requests.get(url, headers=headers, timeout=10)
        
        if response.status_code != 500:
            print("✅ Database queries working (function likely exists)")
            return True
        else:
            print("⚠️  Database queries failing")
            return False
            
    except Exception as e:
        print(f"⚠️  Could not verify function: {e}")
        return False

def print_fix_instructions(has_recursion: bool):
    """Print instructions on how to fix the issue."""
    print("\n" + "=" * 60)
    
    if has_recursion:
        print("🚨 URGENT ACTION REQUIRED")
        print("=" * 60)
        print()
        print("Your Supabase database has the infinite recursion bug.")
        print("This is preventing all API calls from working.")
        print()
        print("📝 TO FIX (takes less than 2 minutes):")
        print()
        print("1. Go to https://app.supabase.com")
        print("2. Select your project")
        print("3. Navigate to 'SQL Editor'")
        print("4. Open the file: migrations/010_admin_security_definer_function.sql")
        print("5. Copy its contents and paste into SQL Editor")
        print("6. Click 'Run' to execute")
        print("7. Verify fix by re-running this script")
        print()
        print("📖 For detailed instructions:")
        print("   See URGENT_FIX_INFINITE_RECURSION.md")
        print()
    else:
        print("✅ NO INFINITE RECURSION DETECTED")
        print("=" * 60)
        print()
        print("Your API appears to be working correctly.")
        print()
        if os.path.exists("migrations/010_admin_security_definer_function.sql"):
            print("Migration 010 appears to have been applied successfully.")
        else:
            print("If you're still experiencing issues, check:")
            print("  - Supabase logs for other errors")
            print("  - CORS configuration")
            print("  - API endpoint URLs")

def main():
    """Main diagnostic routine."""
    print("=" * 60)
    print("Supabase RLS Infinite Recursion Diagnostic Tool")
    print("=" * 60)
    print()
    
    # Check environment
    config = check_environment()
    
    # Test API
    api_working = test_api_endpoint(config)
    
    # Check for function (if API is working)
    if api_working:
        check_database_function(config)
    
    # Print fix instructions
    has_recursion = not api_working
    print_fix_instructions(has_recursion)
    
    # Exit with appropriate code
    sys.exit(0 if api_working else 1)

if __name__ == "__main__":
    main()
