#!/usr/bin/env python3
"""
List users with check-ins from Supabase database.

This script queries the check_ins table and displays the top 5 user_ids
that have check-ins, along with the count of check-ins per user.

Requirements:
    - SUPABASE_URL environment variable
    - SUPABASE_SERVICE_KEY environment variable
    - supabase-py library (pip install supabase)

Usage:
    export SUPABASE_URL="https://your-project.supabase.co"
    export SUPABASE_SERVICE_KEY="your-service-role-key"
    python tools/list_users_with_checkins.py
"""

import os
import sys
from supabase import create_client, Client


def get_supabase_client() -> Client:
    """
    Create and return a Supabase client using environment variables.
    
    Returns:
        Client: Supabase client instance
        
    Raises:
        SystemExit: If required environment variables are not set
    """
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_KEY")
    
    if not url or not key:
        print("ERROR: Missing required environment variables", file=sys.stderr)
        print("Please set SUPABASE_URL and SUPABASE_SERVICE_KEY", file=sys.stderr)
        sys.exit(1)
    
    return create_client(url, key)


def list_users_with_checkins():
    """
    Query check_ins table and display top 5 user_ids with their check-in counts.
    """
    print("Connecting to Supabase...")
    client = get_supabase_client()
    
    try:
        # Query all check-ins
        print("Querying check_ins table...")
        response = client.table('check_ins').select('user_id').execute()
        
        if not response.data:
            print("\nNo check-ins found in the database.")
            return
        
        # Count check-ins per user
        user_counts = {}
        for record in response.data:
            user_id = record.get('user_id')
            if user_id:
                user_counts[user_id] = user_counts.get(user_id, 0) + 1
        
        # Sort by count (descending) and get top 5
        sorted_users = sorted(user_counts.items(), key=lambda x: x[1], reverse=True)
        top_5 = sorted_users[:5]
        
        # Display results
        print(f"\nTotal unique users with check-ins: {len(user_counts)}")
        print(f"Total check-ins: {len(response.data)}")
        print("\nTop 5 user_ids by check-in count:")
        print("-" * 60)
        print(f"{'User ID':<40} {'Check-ins':>10}")
        print("-" * 60)
        
        for user_id, count in top_5:
            print(f"{user_id:<40} {count:>10}")
        
        print("-" * 60)
        
    except Exception as e:
        print(f"\nERROR: Failed to query database: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    list_users_with_checkins()
