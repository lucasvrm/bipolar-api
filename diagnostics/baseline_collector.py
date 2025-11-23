#!/usr/bin/env python3
"""
Baseline metrics collector for admin endpoints diagnostics.
Collects metrics before fixes to establish a baseline.
"""
import json
import os
import sys
import time
from datetime import datetime, timezone
from typing import Any, Dict

import requests

# Configuration
API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")
ADMIN_TOKEN = os.getenv("ADMIN_TOKEN", "")

if not ADMIN_TOKEN:
    print("ERROR: ADMIN_TOKEN environment variable required")
    print("Usage: ADMIN_TOKEN=<your-token> python diagnostics/baseline_collector.py")
    sys.exit(1)

HEADERS = {
    "Authorization": f"Bearer {ADMIN_TOKEN}",
    "Content-Type": "application/json",
}


def safe_request(method: str, url: str, **kwargs) -> Dict[str, Any]:
    """Make HTTP request and capture response safely."""
    start = time.perf_counter()
    try:
        resp = requests.request(method, url, **kwargs)
        duration = time.perf_counter() - start
        
        return {
            "status_code": resp.status_code,
            "success": resp.status_code < 400,
            "duration_ms": round(duration * 1000, 2),
            "body": resp.json() if resp.headers.get("content-type", "").startswith("application/json") else resp.text,
            "error": None,
        }
    except Exception as e:
        duration = time.perf_counter() - start
        return {
            "status_code": None,
            "success": False,
            "duration_ms": round(duration * 1000, 2),
            "body": None,
            "error": str(e),
        }


def collect_baseline() -> Dict[str, Any]:
    """Collect baseline metrics."""
    baseline = {
        "collected_at": datetime.now(timezone.utc).isoformat(),
        "api_base_url": API_BASE_URL,
        "tests": {},
    }
    
    # 1. Get stats
    print("📊 Collecting /api/admin/stats...")
    baseline["tests"]["stats"] = safe_request(
        "GET",
        f"{API_BASE_URL}/api/admin/stats",
        headers=HEADERS,
        timeout=30,
    )
    
    # 2. List users (first 5)
    print("👥 Collecting /api/admin/users?limit=5...")
    baseline["tests"]["list_users"] = safe_request(
        "GET",
        f"{API_BASE_URL}/api/admin/users?limit=5",
        headers=HEADERS,
        timeout=30,
    )
    
    # 3. Create a test user (patient)
    print("➕ Testing /api/admin/users/create (patient)...")
    test_email = f"baseline_test_patient_{int(time.time())}@example.org"
    baseline["tests"]["create_patient"] = safe_request(
        "POST",
        f"{API_BASE_URL}/api/admin/users/create",
        headers=HEADERS,
        json={
            "email": test_email,
            "password": "TestPassword123!",
            "role": "patient",
            "full_name": "Baseline Test Patient",
        },
        timeout=30,
    )
    
    # 4. Create a test user (therapist)
    print("➕ Testing /api/admin/users/create (therapist)...")
    test_email_therapist = f"baseline_test_therapist_{int(time.time())}@example.org"
    baseline["tests"]["create_therapist"] = safe_request(
        "POST",
        f"{API_BASE_URL}/api/admin/users/create",
        headers=HEADERS,
        json={
            "email": test_email_therapist,
            "password": "TestPassword123!",
            "role": "therapist",
            "full_name": "Baseline Test Therapist",
        },
        timeout=30,
    )
    
    # 5. Test duplicate creation (idempotence)
    print("🔄 Testing idempotence (duplicate email)...)
    baseline["tests"]["create_duplicate"] = safe_request(
        "POST",
        f"{API_BASE_URL}/api/admin/users/create",
        headers=HEADERS,
        json={
            "email": test_email,  # Same as create_patient
            "password": "DifferentPassword456!",
            "role": "patient",
        },
        timeout=30,
    )
    
    # 6. Test synthetic data generation
    print("🔬 Testing /api/admin/generate-data...")
    baseline["tests"]["generate_data"] = safe_request(
        "POST",
        f"{API_BASE_URL}/api/admin/generate-data",
        headers=HEADERS,
        json={
            "patientsCount": 2,
            "therapistsCount": 1,
            "checkinsPerUser": 3,
            "moodPattern": "stable",
            "seed": 42,
            "clearDb": False,
        },
        timeout=60,
    )
    
    # 7. Get stats again (after generation)
    print("📊 Collecting /api/admin/stats (after generation)...")
    baseline["tests"]["stats_after_generation"] = safe_request(
        "GET",
        f"{API_BASE_URL}/api/admin/stats",
        headers=HEADERS,
        timeout=30,
    )
    
    # 8. Test cleanup (dry run)
    print("🧹 Testing /api/admin/cleanup (dry run)...")
    baseline["tests"]["cleanup_dryrun"] = safe_request(
        "POST",
        f"{API_BASE_URL}/api/admin/cleanup?dryRun=true",
        headers=HEADERS,
        timeout=30,
    )
    
    return baseline


def main():
    """Main entry point."""
    print("=" * 60)
    print("BASELINE METRICS COLLECTION")
    print("=" * 60)
    print()
    
    baseline = collect_baseline()
    
    # Save to file
    output_file = "diagnostics/before.json"
    with open(output_file, "w") as f:
        json.dump(baseline, f, indent=2)
    
    print()
    print("=" * 60)
    print(f"✅ Baseline saved to {output_file}")
    print("=" * 60)
    print()
    
    # Print summary
    print("SUMMARY:")
    for test_name, result in baseline["tests"].items():
        status = "✅" if result["success"] else "❌"
        print(f"  {status} {test_name}: {result['status_code']} ({result['duration_ms']}ms)")
    
    # Return exit code based on critical failures
    critical_tests = ["stats", "create_patient"]
    critical_failures = [
        name for name in critical_tests
        if not baseline["tests"].get(name, {}).get("success", False)
    ]
    
    if critical_failures:
        print()
        print(f"⚠️  Critical tests failed: {', '.join(critical_failures)}")
        return 1
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
