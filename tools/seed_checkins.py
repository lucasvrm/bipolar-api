#!/usr/bin/env python3
"""
Seed test check-ins for a specific user in Supabase database.

This script inserts N test check-ins for a given user_id with randomized
but realistic data values. It prompts for confirmation before inserting.

Requirements:
    - SUPABASE_URL environment variable
    - SUPABASE_SERVICE_KEY environment variable
    - supabase-py library (pip install supabase)

Usage:
    export SUPABASE_URL="https://your-project.supabase.co"
    export SUPABASE_SERVICE_KEY="your-service-role-key"
    python tools/seed_checkins.py <user_id> <num_checkins>
    
Example:
    python tools/seed_checkins.py user-123-456 10
"""

import os
import sys
import random
from datetime import datetime, timedelta, timezone
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


def generate_test_checkin(user_id: str, days_ago: int) -> dict:
    """
    Generate a test check-in with randomized but realistic data.
    
    Args:
        user_id: The user ID for the check-in
        days_ago: How many days ago this check-in occurred
        
    Returns:
        dict: Check-in data dictionary
    """
    checkin_date = datetime.now(timezone.utc) - timedelta(days=days_ago)
    
    # Generate realistic random values based on the schema from test_predictions_endpoint.py
    return {
        "user_id": user_id,
        "checkin_date": checkin_date.isoformat(),
        "hoursSlept": round(random.uniform(4.0, 10.0), 1),
        "sleepQuality": random.randint(1, 10),
        "energyLevel": random.randint(1, 10),
        "depressedMood": random.randint(0, 10),
        "anxietyStress": random.randint(0, 10),
        "medicationAdherence": random.randint(0, 1),
        "medicationTiming": random.randint(0, 1),
        "compulsionIntensity": random.randint(0, 5),
        "activation": random.randint(0, 10),
        "elevation": random.randint(0, 10),
    }


def confirm_action(message: str) -> bool:
    """
    Prompt user for yes/no confirmation.
    
    Args:
        message: Confirmation message to display
        
    Returns:
        bool: True if user confirms, False otherwise
    """
    while True:
        response = input(f"{message} (yes/no): ").strip().lower()
        if response in ['yes', 'y']:
            return True
        elif response in ['no', 'n']:
            return False
        else:
            print("Please answer 'yes' or 'no'")


def seed_checkins(user_id: str, num_checkins: int):
    """
    Insert N test check-ins for a user after confirmation.
    
    Args:
        user_id: The user ID to create check-ins for
        num_checkins: Number of check-ins to create
    """
    print(f"\nPreparing to seed {num_checkins} check-ins for user: {user_id}")
    print("-" * 60)
    
    # Generate sample check-ins
    checkins = []
    for i in range(num_checkins):
        checkin = generate_test_checkin(user_id, days_ago=i)
        checkins.append(checkin)
    
    # Show a preview
    print("\nPreview of first check-in:")
    print(f"  Date: {checkins[0]['checkin_date']}")
    print(f"  Hours slept: {checkins[0]['hoursSlept']}")
    print(f"  Sleep quality: {checkins[0]['sleepQuality']}")
    print(f"  Energy level: {checkins[0]['energyLevel']}")
    print(f"  Depressed mood: {checkins[0]['depressedMood']}")
    print(f"  Anxiety/Stress: {checkins[0]['anxietyStress']}")
    print("-" * 60)
    
    # Confirm before inserting
    if not confirm_action(f"\nInsert {num_checkins} check-ins into the database?"):
        print("Operation cancelled.")
        return
    
    # Connect to Supabase
    print("\nConnecting to Supabase...")
    client = get_supabase_client()
    
    try:
        print(f"Inserting {num_checkins} check-ins...")
        response = client.table('check_ins').insert(checkins).execute()
        
        inserted_count = len(response.data) if response.data else 0
        print(f"\n✓ Successfully inserted {inserted_count} check-ins for user {user_id}")
        
    except Exception as e:
        print(f"\nERROR: Failed to insert check-ins: {e}", file=sys.stderr)
        sys.exit(1)


def main():
    """Main entry point for the script."""
    if len(sys.argv) != 3:
        print("Usage: python tools/seed_checkins.py <user_id> <num_checkins>", file=sys.stderr)
        print("\nExample:", file=sys.stderr)
        print("  python tools/seed_checkins.py user-123-456 10", file=sys.stderr)
        sys.exit(1)
    
    user_id = sys.argv[1]
    
    try:
        num_checkins = int(sys.argv[2])
        if num_checkins <= 0:
            raise ValueError("Number of check-ins must be positive")
    except ValueError as e:
        print(f"ERROR: Invalid number of check-ins: {e}", file=sys.stderr)
        sys.exit(1)
    
    seed_checkins(user_id, num_checkins)


if __name__ == "__main__":
    main()
