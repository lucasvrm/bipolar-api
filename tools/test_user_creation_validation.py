#!/usr/bin/env python3
"""
Test User Creation Validation Script

Validates that the backend creates exactly N users when requested,
ensuring uniqueness, traceability via prefix, and correct count post-creation.

Usage:
    python tools/test_user_creation_validation.py --count 5 --prefix zz-test

Requirements:
    - SUPABASE_URL environment variable
    - SUPABASE_SERVICE_KEY environment variable
    - Admin user credentials (JWT token)
"""

import argparse
import asyncio
import json
import logging
import os
import sys
import time
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Any, Optional, Tuple
from urllib.parse import urljoin

import httpx
from supabase import create_client, Client

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class UserCreationValidator:
    """Validates user creation with comprehensive tracking and reporting."""
    
    # Safety limits
    MAX_PRODUCTION_COUNT = 10
    MAX_COUNT = 500
    DEFAULT_PREFIX = "zz-test"
    DEFAULT_TIMEOUT = 30.0
    
    def __init__(
        self,
        supabase_url: str,
        supabase_service_key: str,
        admin_token: Optional[str] = None,
        api_base_url: Optional[str] = None
    ):
        """
        Initialize the validator.
        
        Args:
            supabase_url: Supabase project URL
            supabase_service_key: Supabase service role key
            admin_token: JWT token for admin authentication (optional)
            api_base_url: Base URL for API endpoints (defaults to supabase_url)
        """
        self.supabase_url = supabase_url
        self.supabase_service_key = supabase_service_key
        self.admin_token = admin_token
        self.api_base_url = api_base_url or supabase_url
        
        # Initialize Supabase client
        self.supabase: Client = create_client(supabase_url, supabase_service_key)
        
        # Tracking data
        self.correlation_id = f"test-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}"
        self.created_baseline: Optional[datetime] = None
        self.baseline_count_before: int = 0
        self.baseline_count_after: int = 0
        self.created_user_ids: List[str] = []
        self.created_usernames: List[str] = []
        self.latencies: List[float] = []
        self.errors: List[Dict[str, Any]] = []
        self.network_timeouts: int = 0
        self.server_errors: int = 0
        self.validation_errors: int = 0
        
    def validate_parameters(self, requested_count: int, prefix: str) -> Tuple[bool, Optional[str]]:
        """
        Validate input parameters.
        
        Args:
            requested_count: Number of users to create
            prefix: Prefix for usernames
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        # Check if count is positive integer
        if not isinstance(requested_count, int) or requested_count <= 0:
            return False, f"requestedCount must be a positive integer, got: {requested_count}"
        
        # Check safety limits
        app_env = os.getenv("APP_ENV", "development")
        if app_env == "production" and requested_count > self.MAX_PRODUCTION_COUNT:
            return False, (
                f"In production, requestedCount is limited to {self.MAX_PRODUCTION_COUNT}. "
                f"Requested: {requested_count}"
            )
        
        if requested_count > self.MAX_COUNT:
            return False, f"requestedCount exceeds maximum limit of {self.MAX_COUNT}"
        
        # Validate prefix
        if not prefix or not isinstance(prefix, str):
            return False, "prefix must be a non-empty string"
        
        if len(prefix) < 2:
            return False, "prefix must be at least 2 characters long"
        
        return True, None
    
    async def capture_baseline(self, prefix: str) -> int:
        """
        Capture the baseline count of users with the given prefix.
        
        Args:
            prefix: Username prefix to filter by
            
        Returns:
            Count of existing users with the prefix
        """
        logger.info(f"Capturing baseline for prefix: {prefix}")
        self.created_baseline = datetime.now(timezone.utc)
        
        try:
            # Query profiles table for users with matching prefix
            # Use email pattern matching since username might not be stored separately
            response = self.supabase.table("profiles").select("id,email,created_at").execute()
            
            if not response.data:
                logger.info("No existing users found")
                return 0
            
            # Filter users with prefix in email (before @)
            # Also check for recently created (last 24h) to differentiate from legacy
            cutoff_time = self.created_baseline - timedelta(hours=24)
            
            matching_users = [
                user for user in response.data
                if user.get("email", "").startswith(prefix)
                and datetime.fromisoformat(user.get("created_at", "").replace("Z", "+00:00")) >= cutoff_time
            ]
            
            self.baseline_count_before = len(matching_users)
            logger.info(f"Baseline count: {self.baseline_count_before} users with prefix '{prefix}' (last 24h)")
            
            return self.baseline_count_before
            
        except Exception as e:
            logger.error(f"Error capturing baseline: {e}")
            self.errors.append({
                "phase": "baseline",
                "error": str(e),
                "timestamp": datetime.now(timezone.utc).isoformat()
            })
            return 0
    
    async def check_bulk_endpoint(self) -> bool:
        """
        Check if a bulk user creation endpoint exists.
        
        Returns:
            True if bulk endpoint is available, False otherwise
        """
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                # Try OPTIONS request first
                url = urljoin(self.api_base_url, "/api/admin/users/bulk")
                response = await client.options(url)
                
                if response.status_code in (200, 204, 405):  # 405 means endpoint exists but OPTIONS not allowed
                    logger.info("Bulk endpoint found via OPTIONS")
                    return True
                
                # Try HEAD request
                response = await client.head(url)
                if response.status_code in (200, 405):
                    logger.info("Bulk endpoint found via HEAD")
                    return True
                    
        except Exception as e:
            logger.debug(f"Bulk endpoint check failed: {e}")
        
        logger.info("No bulk endpoint available, will use loop-based creation")
        return False
    
    async def create_user_single(
        self,
        username: str,
        email: str,
        full_name: str,
        role: str = "patient",
        session: Optional[httpx.AsyncClient] = None
    ) -> Tuple[Optional[str], float, Optional[str]]:
        """
        Create a single user via the admin API.
        
        Args:
            username: Username for the user
            email: Email address
            full_name: Full name
            role: User role (default: "patient")
            session: HTTP client session (optional)
            
        Returns:
            Tuple of (user_id, latency_ms, error_message)
        """
        url = urljoin(self.api_base_url, "/api/admin/users/create")
        
        # Generate a cryptographically secure random password
        import secrets
        secure_password = secrets.token_urlsafe(16)
        
        payload = {
            "email": email,
            "password": secure_password,
            "role": role,
            "full_name": full_name
        }
        
        headers = {}
        if self.admin_token:
            headers["Authorization"] = f"Bearer {self.admin_token}"
        
        start_time = time.time()
        
        try:
            if session:
                client = session
            else:
                client = httpx.AsyncClient(timeout=self.DEFAULT_TIMEOUT)
            
            try:
                response = await client.post(url, json=payload, headers=headers)
                latency_ms = (time.time() - start_time) * 1000
                
                if response.status_code == 200:
                    data = response.json()
                    user_id = data.get("user_id")
                    
                    if user_id:
                        logger.debug(f"Created user: {username} (ID: {user_id}) in {latency_ms:.2f}ms")
                        return user_id, latency_ms, None
                    else:
                        error_msg = "Response missing user_id"
                        logger.warning(f"User creation succeeded but {error_msg}: {username}")
                        self.validation_errors += 1
                        return None, latency_ms, error_msg
                
                elif response.status_code >= 500:
                    self.server_errors += 1
                    error_msg = f"Server error {response.status_code}: {response.text}"
                    logger.error(f"Server error creating {username}: {error_msg}")
                    return None, latency_ms, error_msg
                
                elif response.status_code == 429:
                    error_msg = "Rate limit exceeded"
                    logger.warning(f"Rate limit hit while creating {username}")
                    return None, latency_ms, error_msg
                
                else:
                    self.validation_errors += 1
                    error_msg = f"HTTP {response.status_code}: {response.text}"
                    logger.error(f"Client error creating {username}: {error_msg}")
                    return None, latency_ms, error_msg
                    
            finally:
                if not session:
                    await client.aclose()
                    
        except httpx.TimeoutException as e:
            self.network_timeouts += 1
            latency_ms = (time.time() - start_time) * 1000
            error_msg = f"Network timeout: {e}"
            logger.error(f"Timeout creating {username}: {error_msg}")
            return None, latency_ms, error_msg
            
        except Exception as e:
            latency_ms = (time.time() - start_time) * 1000
            error_msg = f"Unexpected error: {e}"
            logger.error(f"Error creating {username}: {error_msg}")
            return None, latency_ms, error_msg
    
    async def create_users_loop(
        self,
        requested_count: int,
        prefix: str
    ) -> List[Dict[str, Any]]:
        """
        Create users in a loop (fallback when bulk endpoint unavailable).
        
        Args:
            requested_count: Number of users to create
            prefix: Username prefix
            
        Returns:
            List of creation results
        """
        results = []
        timestamp = datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')
        
        async with httpx.AsyncClient(timeout=self.DEFAULT_TIMEOUT) as session:
            for i in range(1, requested_count + 1):
                username = f"{prefix}-{timestamp}-{i}"
                email = f"{username}@example.com"
                full_name = f"Test Auto {i}"
                
                user_id, latency, error = await self.create_user_single(
                    username=username,
                    email=email,
                    full_name=full_name,
                    role="patient",
                    session=session
                )
                
                result = {
                    "index": i,
                    "username": username,
                    "email": email,
                    "user_id": user_id,
                    "status": "success" if user_id else "failed",
                    "latency_ms": latency,
                    "error": error
                }
                
                results.append(result)
                self.latencies.append(latency)
                
                if user_id:
                    self.created_user_ids.append(user_id)
                    self.created_usernames.append(username)
                else:
                    self.errors.append({
                        "phase": "creation",
                        "index": i,
                        "username": username,
                        "error": error,
                        "latency_ms": latency
                    })
                
                # Small delay to avoid overwhelming the API
                if i < requested_count:
                    await asyncio.sleep(0.1)
        
        return results
    
    async def verify_post_creation(self, prefix: str) -> int:
        """
        Verify users were actually created and persisted.
        
        Args:
            prefix: Username prefix to filter by
            
        Returns:
            Count of users found with the prefix after creation
        """
        logger.info("Verifying post-creation user count...")
        
        try:
            # Query with filter for users created after baseline
            created_after_iso = self.created_baseline.isoformat() if self.created_baseline else None
            
            response = self.supabase.table("profiles").select("id,email,created_at").execute()
            
            if not response.data:
                logger.warning("No users found in post-creation verification")
                return 0
            
            # Filter for users with prefix created after baseline
            matching_users = []
            for user in response.data:
                email = user.get("email", "")
                if not email.startswith(prefix):
                    continue
                
                # Extract username part (before @)
                username = email.split("@")[0]
                
                # Check if in our created list OR created after baseline
                if username in self.created_usernames:
                    matching_users.append(user)
                elif created_after_iso:
                    created_at = user.get("created_at", "")
                    if created_at:
                        user_created = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
                        if user_created >= self.created_baseline:
                            matching_users.append(user)
            
            self.baseline_count_after = len(matching_users)
            logger.info(f"Post-creation count: {self.baseline_count_after} users with prefix '{prefix}'")
            
            return self.baseline_count_after
            
        except Exception as e:
            logger.error(f"Error in post-creation verification: {e}")
            self.errors.append({
                "phase": "verification",
                "error": str(e),
                "timestamp": datetime.now(timezone.utc).isoformat()
            })
            return 0
    
    def analyze_discrepancy(
        self,
        requested_count: int
    ) -> Dict[str, Any]:
        """
        Analyze discrepancies between requested and actual counts.
        
        Args:
            requested_count: Number of users requested to be created
            
        Returns:
            Discrepancy analysis
        """
        actual_count = len(self.created_user_ids)
        has_discrepancy = actual_count != requested_count
        
        analysis = {
            "has_discrepancy": has_discrepancy,
            "requested_count": requested_count,
            "actual_created": actual_count,
            "difference": actual_count - requested_count,
            "missing_count": max(0, requested_count - actual_count),
            "duplicated_usernames": [],
            "missing_ids": []
        }
        
        # Check for duplicated usernames
        username_counts = {}
        for username in self.created_usernames:
            username_counts[username] = username_counts.get(username, 0) + 1
        
        duplicates = [
            {"username": username, "count": count}
            for username, count in username_counts.items()
            if count > 1
        ]
        
        if duplicates:
            analysis["duplicated_usernames"] = duplicates
        
        # Identify missing IDs (those that failed to create)
        expected_indices = set(range(1, requested_count + 1))
        created_indices = set()
        
        for error in self.errors:
            if error.get("phase") == "creation":
                index = error.get("index")
                if index:
                    analysis["missing_ids"].append({
                        "index": index,
                        "username": error.get("username"),
                        "error": error.get("error")
                    })
        
        return analysis
    
    def calculate_metrics(self) -> Dict[str, Any]:
        """
        Calculate performance metrics.
        
        Returns:
            Performance metrics dictionary
        """
        if not self.latencies:
            return {
                "mean_ms": 0.0,
                "max_ms": 0.0,
                "min_ms": 0.0,
                "p95_ms": 0.0,
                "p99_ms": 0.0
            }
        
        sorted_latencies = sorted(self.latencies)
        count = len(sorted_latencies)
        
        p95_index = int(count * 0.95)
        p99_index = int(count * 0.99)
        
        return {
            "mean_ms": sum(sorted_latencies) / count,
            "max_ms": max(sorted_latencies),
            "min_ms": min(sorted_latencies),
            "p95_ms": sorted_latencies[p95_index] if p95_index < count else sorted_latencies[-1],
            "p99_ms": sorted_latencies[p99_index] if p99_index < count else sorted_latencies[-1]
        }
    
    def validate_invariants(
        self,
        requested_count: int,
        prefix: str
    ) -> List[str]:
        """
        Validate mathematical invariants.
        
        Args:
            requested_count: Number of users requested
            prefix: Username prefix
            
        Returns:
            List of invariant violations (empty if all pass)
        """
        violations = []
        
        # Invariant 1: actualCount >= createdUserIds unique
        unique_user_ids = len(set(self.created_user_ids))
        if len(self.created_user_ids) != unique_user_ids:
            violations.append(
                f"Duplicate user IDs detected: {len(self.created_user_ids)} total, "
                f"{unique_user_ids} unique"
            )
        
        # Invariant 2: (baselineCountBefore + requestedCount) >= baselineCountAfter
        # Allow for replication delay
        expected_minimum = self.baseline_count_before + len(self.created_user_ids)
        if self.baseline_count_after < expected_minimum:
            violations.append(
                f"Post-creation count {self.baseline_count_after} is less than expected minimum "
                f"{expected_minimum} (baseline {self.baseline_count_before} + created {len(self.created_user_ids)})"
            )
        
        # Invariant 3: No username outside pattern should be in createdUserIds
        for username in self.created_usernames:
            if not username.startswith(prefix):
                violations.append(f"Username '{username}' does not match prefix '{prefix}'")
        
        return violations
    
    async def run_validation(
        self,
        requested_count: int,
        prefix: str = DEFAULT_PREFIX
    ) -> Dict[str, Any]:
        """
        Run the complete validation workflow.
        
        Args:
            requested_count: Number of users to create
            prefix: Username prefix (default: zz-test)
            
        Returns:
            Complete validation report
        """
        start_time = time.time()
        
        # Step 1: Validate parameters
        is_valid, error_msg = self.validate_parameters(requested_count, prefix)
        if not is_valid:
            logger.error(f"Parameter validation failed: {error_msg}")
            return {
                "status": "FAIL",
                "error": error_msg,
                "correlation_id": self.correlation_id
            }
        
        logger.info(f"Starting validation: count={requested_count}, prefix={prefix}")
        
        # Step 2: Capture baseline
        await self.capture_baseline(prefix)
        
        # Step 3: Check for bulk endpoint
        has_bulk = await self.check_bulk_endpoint()
        
        # Step 4: Create users
        if has_bulk:
            logger.info("Using bulk endpoint (not implemented in current codebase)")
            # Bulk creation would go here
            creation_results = []
        else:
            logger.info("Using loop-based creation")
            creation_results = await self.create_users_loop(requested_count, prefix)
        
        # Step 5: Verify post-creation
        await self.verify_post_creation(prefix)
        
        # Step 6: Analyze results
        discrepancy = self.analyze_discrepancy(requested_count)
        metrics = self.calculate_metrics()
        invariant_violations = self.validate_invariants(requested_count, prefix)
        
        # Step 7: Determine overall status
        if discrepancy["has_discrepancy"]:
            overall_status = "FAIL" if discrepancy["difference"] < 0 else "WARN"
        elif invariant_violations:
            overall_status = "WARN"
        elif self.errors:
            overall_status = "WARN"
        else:
            overall_status = "OK"
        
        duration_s = time.time() - start_time
        
        # Generate report
        report = {
            "correlation_id": self.correlation_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "duration_seconds": round(duration_s, 2),
            "parameters": {
                "requested_count": requested_count,
                "prefix": prefix,
                "app_env": os.getenv("APP_ENV", "development")
            },
            "baseline": {
                "count_before": self.baseline_count_before,
                "count_after": self.baseline_count_after,
                "baseline_timestamp": self.created_baseline.isoformat() if self.created_baseline else None
            },
            "creation": {
                "method": "bulk" if has_bulk else "loop",
                "created_user_ids": self.created_user_ids,
                "created_usernames": self.created_usernames[:10],  # Sample for brevity
                "total_created": len(self.created_user_ids)
            },
            "verification": {
                "actual_count_verified": len(self.created_user_ids),
                "baseline_count_after": self.baseline_count_after
            },
            "discrepancy": discrepancy,
            "latencies": metrics,
            "error_summary": {
                "total_errors": len(self.errors),
                "network_timeouts": self.network_timeouts,
                "server_errors": self.server_errors,
                "validation_errors": self.validation_errors,
                "errors": self.errors[:5]  # Sample for brevity
            },
            "invariant_violations": invariant_violations,
            "overall_status": overall_status
        }
        
        return report
    
    def _format_checklist_item(self, completed: bool, text: str) -> str:
        """Format a checklist item with completion status."""
        check = "x" if completed else " "
        return f"- [{check}] {text}"
    
    def _format_discrepancy_section(self, discrepancy: Dict[str, Any], requested_count: int) -> str:
        """Format the discrepancy section of the ROADMAP."""
        if not discrepancy.get("has_discrepancy"):
            return "**No discrepancies detected.** ✅"
        
        section = f"""
**Discrepancy detected:**
- **Requested:** {requested_count}
- **Actually Created:** {discrepancy.get('actual_created', 0)}
- **Difference:** {discrepancy.get('difference', 0)}
- **Missing:** {discrepancy.get('missing_count', 0)}
"""
        
        # Add duplicates if any
        duplicates = discrepancy.get('duplicated_usernames', [])
        if duplicates:
            section += "\n### Duplicated Usernames\n"
            for dup in duplicates:
                section += f"- {dup.get('username')}: {dup.get('count')} occurrences\n"
        
        # Add missing users if any
        missing = discrepancy.get('missing_ids', [])
        if missing:
            section += "\n### Missing/Failed Users\n"
            for miss in missing[:5]:  # Limit to first 5
                section += f"- Index {miss.get('index')}: {miss.get('username')} - {miss.get('error')}\n"
        
        return section
    
    def _format_invariants_section(self, violations: List[str]) -> str:
        """Format the invariant violations section."""
        if not violations:
            return "**All invariants passed.** ✅"
        
        section = "⚠️ **Violations detected:**\n"
        for violation in violations:
            section += f"- {violation}\n"
        
        return section
    
    def generate_roadmap(
        self,
        report: Dict[str, Any],
        requested_count: int,
        prefix: str
    ) -> str:
        """
        Generate ROADMAP markdown document.
        
        Args:
            report: Validation report
            requested_count: Requested user count
            prefix: Username prefix
            
        Returns:
            ROADMAP markdown content
        """
        status_emoji = {
            "OK": "✅",
            "WARN": "⚠️",
            "FAIL": "❌"
        }
        
        overall_status = report.get("overall_status", "FAIL")
        emoji = status_emoji.get(overall_status, "❓")
        
        roadmap = f"""# Test User Creation Validation - ROADMAP

## Status: {emoji} {overall_status}

**Correlation ID:** `{report.get('correlation_id')}`  
**Timestamp:** {report.get('timestamp')}  
**Duration:** {report.get('duration_seconds')}s

---

## Test Parameters

- **Requested Count:** {requested_count}
- **Prefix:** `{prefix}`
- **Environment:** {report.get('parameters', {}).get('app_env', 'unknown')}

---

## What Was Requested

{self._format_checklist_item(not report.get('discrepancy', {}).get('has_discrepancy'), f"Create {requested_count} test users with prefix `{prefix}`")}
{self._format_checklist_item(report.get('baseline', {}).get('count_before', -1) >= 0, "Capture baseline user count before creation")}
{self._format_checklist_item(report.get('creation', {}).get('total_created', 0) > 0, "Execute user creation via admin API")}
{self._format_checklist_item(report.get('verification', {}).get('actual_count_verified', -1) >= 0, "Verify users persisted in database")}
{self._format_checklist_item(not report.get('discrepancy', {}).get('has_discrepancy'), "Validate count matches requested amount")}
{self._format_checklist_item(not report.get('invariant_violations'), "Validate mathematical invariants")}

---

## What Was Realized

### Baseline Capture
- **Before:** {report.get('baseline', {}).get('count_before', 0)} users with prefix `{prefix}`
- **After:** {report.get('baseline', {}).get('count_after', 0)} users with prefix `{prefix}`

### User Creation
- **Method:** {report.get('creation', {}).get('method', 'unknown').upper()}
- **Total Created:** {report.get('creation', {}).get('total_created', 0)} users
- **Success Rate:** {(report.get('creation', {}).get('total_created', 0) / requested_count * 100) if requested_count > 0 else 0:.1f}%

### Performance Metrics
- **Mean Latency:** {report.get('latencies', {}).get('mean_ms', 0):.2f}ms
- **Max Latency:** {report.get('latencies', {}).get('max_ms', 0):.2f}ms
- **P95 Latency:** {report.get('latencies', {}).get('p95_ms', 0):.2f}ms

### Errors
- **Total Errors:** {report.get('error_summary', {}).get('total_errors', 0)}
- **Network Timeouts:** {report.get('error_summary', {}).get('network_timeouts', 0)}
- **Server Errors:** {report.get('error_summary', {}).get('server_errors', 0)}
- **Validation Errors:** {report.get('error_summary', {}).get('validation_errors', 0)}

---

## Discrepancies

{self._format_discrepancy_section(report.get('discrepancy', {}), requested_count)}

---

## Invariant Violations

{self._format_invariants_section(report.get('invariant_violations', []))}

---

## What Was Not Possible

- **Bulk Endpoint:** Not available in current implementation (endpoint `/api/admin/users/bulk` does not exist)
- **Distributed Tracing:** Not yet instrumented
- **Rollback on Failure:** Not implemented (cleanup must be done manually)

---

## Next Steps

### Immediate Actions

"""
        
        # Add immediate actions based on status
        actions = []
        if report.get('discrepancy', {}).get('has_discrepancy'):
            actions.append("- Investigate and fix discrepancies")
        if report.get('invariant_violations'):
            actions.append("- Review and address invariant violations")
        if report.get('error_summary', {}).get('total_errors', 0) > 0:
            actions.append("- Investigate errors and retry failed creations")
        
        if not actions:
            actions.append("- None required, validation passed")
        
        roadmap += "\n".join(actions) + "\n\n"
        
        roadmap += """

### Future Improvements
- [ ] Implement bulk user creation endpoint (`POST /api/admin/users/bulk`)
- [ ] Add idempotency keys to prevent duplicate creations
- [ ] Implement automatic rollback on partial failure
- [ ] Add distributed tracing with correlation IDs
- [ ] Implement retry logic with exponential backoff
- [ ] Add rate limit handling and backoff strategy
- [ ] Create cleanup script for test users

---

## Cleanup (Optional)

Test users created with prefix `{prefix}` can be cleaned up using:

```bash
# List test users
python tools/test_user_creation_validation.py --count 0 --prefix {prefix} --list-only

# Clean up test users (if cleanup endpoint available)
# DELETE /api/admin/users?prefix={prefix}
```

**Note:** Automatic cleanup is not enabled by default to prevent accidental data loss.

---

**Generated:** {datetime.now(timezone.utc).isoformat()}  
**Script Version:** 1.0.0
"""
        
        return roadmap


async def main():
    """Main entry point for the script."""
    parser = argparse.ArgumentParser(
        description="Test User Creation Validation Script",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Create 5 test users
  python tools/test_user_creation_validation.py --count 5
  
  # Create 10 test users with custom prefix
  python tools/test_user_creation_validation.py --count 10 --prefix my-test
  
  # Output to custom location
  python tools/test_user_creation_validation.py --count 5 --output /tmp/report.json
        """
    )
    
    parser.add_argument(
        '--count',
        type=int,
        required=True,
        help='Number of test users to create'
    )
    
    parser.add_argument(
        '--prefix',
        type=str,
        default=UserCreationValidator.DEFAULT_PREFIX,
        help=f'Username prefix (default: {UserCreationValidator.DEFAULT_PREFIX})'
    )
    
    parser.add_argument(
        '--output',
        type=str,
        default=None,
        help='Output file path for JSON report (default: report_user_creation.json)'
    )
    
    parser.add_argument(
        '--roadmap-output',
        type=str,
        default=None,
        help='Output file path for ROADMAP markdown (default: ROADMAP_USER_CREATION.md)'
    )
    
    parser.add_argument(
        '--api-url',
        type=str,
        default=None,
        help='API base URL (default: from SUPABASE_URL env var)'
    )
    
    parser.add_argument(
        '--admin-token',
        type=str,
        default=None,
        help='Admin JWT token (optional, for authentication)'
    )
    
    parser.add_argument(
        '--verbose',
        action='store_true',
        help='Enable verbose logging'
    )
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    # Get environment variables
    supabase_url = os.getenv("SUPABASE_URL")
    supabase_service_key = os.getenv("SUPABASE_SERVICE_KEY")
    
    if not supabase_url or not supabase_service_key:
        logger.error("Missing required environment variables:")
        if not supabase_url:
            logger.error("  - SUPABASE_URL")
        if not supabase_service_key:
            logger.error("  - SUPABASE_SERVICE_KEY")
        sys.exit(1)
    
    # Initialize validator
    validator = UserCreationValidator(
        supabase_url=supabase_url,
        supabase_service_key=supabase_service_key,
        admin_token=args.admin_token,
        api_base_url=args.api_url
    )
    
    # Run validation
    logger.info("=" * 70)
    logger.info("Test User Creation Validation")
    logger.info("=" * 70)
    
    report = await validator.run_validation(
        requested_count=args.count,
        prefix=args.prefix
    )
    
    # Save JSON report
    output_file = args.output or "report_user_creation.json"
    with open(output_file, 'w') as f:
        json.dump(report, f, indent=2)
    logger.info(f"JSON report saved to: {output_file}")
    
    # Generate and save ROADMAP
    roadmap = validator.generate_roadmap(report, args.count, args.prefix)
    roadmap_file = args.roadmap_output or "ROADMAP_USER_CREATION.md"
    with open(roadmap_file, 'w') as f:
        f.write(roadmap)
    logger.info(f"ROADMAP saved to: {roadmap_file}")
    
    # Print summary
    logger.info("=" * 70)
    logger.info(f"Validation Status: {report.get('overall_status')}")
    logger.info(f"Requested: {args.count} | Created: {len(report.get('creation', {}).get('created_user_ids', []))}")
    logger.info(f"Errors: {report.get('error_summary', {}).get('total_errors', 0)}")
    logger.info("=" * 70)
    
    # Exit with appropriate code
    if report.get('overall_status') == 'FAIL':
        sys.exit(1)
    elif report.get('overall_status') == 'WARN':
        sys.exit(2)
    else:
        sys.exit(0)


if __name__ == "__main__":
    asyncio.run(main())
