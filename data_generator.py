"""
Data generator module for creating synthetic realistic bipolar disorder check-in data.

This module provides functionality to generate synthetic patient data with realistic
patterns for bipolar disorder monitoring, mapped correctly to the database JSONB schema.
"""
import random
import json
import uuid
from datetime import datetime, timedelta, timezone
from faker import Faker
from typing import List, Dict, Any, Optional
from supabase import AsyncClient
import logging
from fastapi import HTTPException
from postgrest.exceptions import APIError
from api.schemas.checkin_jsonb import (
    SleepData,
    MoodData,
    SymptomsData,
    RiskRoutineData,
    AppetiteImpulseData,
    MedsContextData
)

# Use a specific locale for consistency
fake = Faker('pt_BR')
logger = logging.getLogger("bipolar-api.data_generator")

# Set logging level to DEBUG for granular tracking
logger.setLevel(logging.DEBUG)


def generate_realistic_checkin(
    user_id: str,
    checkin_date: datetime,
    mood_state: str = None
) -> Dict[str, Any]:
    """
    Generate a single realistic check-in with correlated features,
    structured into the specific JSONB columns of the database.
    """
    # Define mood state if not provided
    if mood_state is None:
        mood_state = random.choices(
            ['EUTHYMIC', 'DEPRESSED', 'MANIC', 'MIXED'],
            weights=[0.5, 0.25, 0.15, 0.10]
        )[0]
    
    # --- 1. Generate Raw Values based on Clinical Logic ---
    
    if mood_state == 'MANIC':
        # Manic: Low sleep, high energy, high activation/elevation, risky behavior
        sleep_hours = round(random.uniform(3.0, 6.0), 1)
        sleep_quality = random.randint(3, 7)
        energy_level = random.randint(7, 10)
        depressed_mood = random.randint(0, 3)
        anxiety_stress = random.randint(5, 10)
        activation = random.randint(7, 10)
        elevation = random.randint(7, 10)
        thought_speed = random.randint(7, 10)
        distractibility = random.randint(6, 10)
        libido = random.randint(6, 10)
        compulsion_episode = random.choice([0, 1])
        compulsion_intensity = random.randint(3, 5) if compulsion_episode else 0
        motivation = random.randint(8, 10)
        tasks_planned = random.randint(5, 15)
        tasks_completed = random.randint(1, tasks_planned) # Often starts many, finishes few or many
        
    elif mood_state == 'DEPRESSED':
        # Depressed: High sleep, low energy, low motivation, rumination
        sleep_hours = round(random.uniform(8.0, 12.0), 1)
        sleep_quality = random.randint(2, 6)
        energy_level = random.randint(1, 4)
        depressed_mood = random.randint(6, 10)
        anxiety_stress = random.randint(4, 9)
        activation = random.randint(0, 3)
        elevation = random.randint(0, 2)
        thought_speed = random.randint(1, 4)
        distractibility = random.randint(2, 6)
        libido = random.randint(0, 3)
        compulsion_episode = 0
        compulsion_intensity = 0
        motivation = random.randint(1, 4)
        tasks_planned = random.randint(1, 5)
        tasks_completed = max(0, random.randint(0, tasks_planned // 2))

    elif mood_state == 'MIXED':
        # Mixed: Erratic sleep, high energy but bad mood, high anxiety/agitation
        sleep_hours = round(random.uniform(4.0, 7.0), 1)
        sleep_quality = random.randint(2, 5)
        energy_level = random.randint(3, 7)
        depressed_mood = random.randint(6, 9)
        anxiety_stress = random.randint(7, 10)
        activation = random.randint(5, 8)
        elevation = random.randint(2, 5)
        thought_speed = random.randint(5, 8)
        distractibility = random.randint(7, 10)
        libido = random.randint(2, 6)
        compulsion_episode = random.choice([0, 1])
        compulsion_intensity = random.randint(2, 4) if compulsion_episode else 0
        motivation = random.randint(2, 6)
        tasks_planned = random.randint(3, 8)
        tasks_completed = random.randint(0, tasks_planned // 2)

    else:  # EUTHYMIC
        # Stable: Normal ranges
        sleep_hours = round(random.uniform(6.5, 8.5), 1)
        sleep_quality = random.randint(6, 9)
        energy_level = random.randint(5, 8)
        depressed_mood = random.randint(0, 4)
        anxiety_stress = random.randint(0, 5)
        activation = random.randint(4, 7)
        elevation = random.randint(3, 6)
        thought_speed = random.randint(4, 7)
        distractibility = random.randint(2, 5)
        libido = random.randint(4, 7)
        compulsion_episode = 0
        compulsion_intensity = 0
        motivation = random.randint(4, 8)
        tasks_planned = random.randint(3, 8)
        tasks_completed = random.randint(tasks_planned // 2, tasks_planned)

    # Secondary variables derived from core state
    medication_adherence = 1 if (mood_state == 'EUTHYMIC' or random.random() > 0.3) else 0
    medication_timing = random.randint(0, 1) if medication_adherence else 0
    medication_change_recent = 1 if random.random() < 0.05 else 0
    
    social_connection = max(0, min(10, 10 - anxiety_stress // 2 + random.randint(-2, 2)))
    contextual_stressors = random.randint(0, 1)
    social_rhythm_event = 1 if random.random() < 0.15 else 0 # Ex: travel, shift work
    
    # Risk factors with correlations
    suicidal_ideation = random.randint(0, 3) if mood_state == 'DEPRESSED' else 0
    suicide_risk = random.randint(0, 2) if suicidal_ideation > 0 else 0
    self_harm = random.randint(0, 1) if mood_state in ['DEPRESSED', 'MIXED'] else 0
    routine_disruption = 1 if social_rhythm_event else random.randint(0, 1)
    substance_use = random.randint(0, 2) if mood_state == 'MANIC' else 0
    risky_behavior = random.randint(0, 1) if mood_state == 'MANIC' else 0
    
    # Appetite and impulse
    appetite = random.randint(3, 7)
    impulse_control = random.randint(4, 8)
    impulse_spending = random.randint(0, 1) if mood_state == 'MANIC' else 0
    impulse_food = random.randint(0, 1) if mood_state in ['DEPRESSED', 'MANIC'] else 0
    impulse_sex = random.randint(0, 1) if mood_state == 'MANIC' else 0
    impulse_drugs = random.randint(0, 1) if mood_state == 'MANIC' else 0
    impulse_alcohol = random.randint(0, 1) if mood_state in ['DEPRESSED', 'MANIC'] else 0
    
    # --- 2. Structure Data into JSONB Columns ---
    
    # sleep_data JSONB
    sleep_data = SleepData(
        sleep_hours=sleep_hours,
        sleep_quality=sleep_quality,
        sleep_disrupted=random.randint(0, 1),
        sleep_aids_used=random.randint(0, 1)
    ).model_dump()
    
    # mood_data JSONB
    mood_data = MoodData(
        energy_level=energy_level,
        depressed_mood=depressed_mood,
        anxiety_stress=anxiety_stress,
        activation=activation,
        elevation=elevation,
        social_connection=social_connection,
        contextual_stressors=contextual_stressors,
        social_rhythm_event=social_rhythm_event
    ).model_dump()
    
    # symptoms_data JSONB
    symptoms_data = SymptomsData(
        thought_speed=thought_speed,
        distractibility=distractibility,
        libido=libido,
        compulsion_episode=compulsion_episode,
        compulsion_intensity=compulsion_intensity,
        motivation=motivation,
        tasks_planned=tasks_planned,
        tasks_completed=tasks_completed
    ).model_dump()
    
    # risk_routine_data JSONB
    risk_routine_data = RiskRoutineData(
        suicidal_ideation=suicidal_ideation,
        suicide_risk=suicide_risk,
        self_harm=self_harm,
        routine_disruption=routine_disruption,
        substance_use=substance_use,
        risky_behavior=risky_behavior
    ).model_dump()
    
    # appetite_impulse_data JSONB
    appetite_impulse_data = AppetiteImpulseData(
        appetite=appetite,
        impulse_control=impulse_control,
        impulse_spending=impulse_spending,
        impulse_food=impulse_food,
        impulse_sex=impulse_sex,
        impulse_drugs=impulse_drugs,
        impulse_alcohol=impulse_alcohol
    ).model_dump()
    
    # meds_context_data JSONB
    meds_context_data = MedsContextData(
        medication_adherence=medication_adherence,
        medication_timing=medication_timing,
        medication_change_recent=medication_change_recent
    ).model_dump()
    
    # --- 3. Assemble Full Check-in Dict ---
    return {
        "user_id": user_id,
        "checkin_date": checkin_date.isoformat(),
        "sleep_data": sleep_data,
        "mood_data": mood_data,
        "symptoms_data": symptoms_data,
        "risk_routine_data": risk_routine_data,
        "appetite_impulse_data": appetite_impulse_data,
        "meds_context_data": meds_context_data
    }


def generate_user_checkin_history(
    user_id: str,
    num_checkins: int = 30,
    mood_pattern: str = 'stable',
    start_date: datetime = None
) -> List[Dict[str, Any]]:
    """
    Generate a history of check-ins for a user with specified mood pattern.
    
    Args:
        user_id: User UUID
        num_checkins: Number of check-ins to generate
        mood_pattern: 'stable' (mostly euthymic), 'cycling' (cycles every 7-14 days), or 'random'
        start_date: Optional start date (defaults to today - num_checkins days)
        
    Returns:
        List of check-in dictionaries
    """
    if start_date is None:
        start_date = datetime.now(timezone.utc) - timedelta(days=num_checkins)
    
    checkins = []
    
    # Generate mood sequence based on pattern
    mood_sequence = []
    
    if mood_pattern == 'cycling':
        # Bipolar cycling: 7-14 day episodes
        episode_length = random.randint(7, 14)
        moods = ['EUTHYMIC', 'MANIC', 'DEPRESSED', 'MIXED']
        current_mood = random.choice(moods)
        
        for i in range(num_checkins):
            if i % episode_length == 0:
                current_mood = random.choice([m for m in moods if m != current_mood])
            mood_sequence.append(current_mood)
            
    elif mood_pattern == 'stable':
        # Mostly euthymic with occasional deviations
        for _ in range(num_checkins):
            mood_sequence.append(random.choices(
                ['EUTHYMIC', 'DEPRESSED', 'MANIC', 'MIXED'],
                weights=[0.8, 0.1, 0.05, 0.05]
            )[0])
            
    else:  # random
        for _ in range(num_checkins):
            mood_sequence.append(random.choices(
                ['EUTHYMIC', 'DEPRESSED', 'MANIC', 'MIXED'],
                weights=[0.5, 0.25, 0.15, 0.10]
            )[0])
    
    # Generate check-ins
    for i in range(num_checkins):
        checkin_date = start_date + timedelta(days=i)
        checkin = generate_realistic_checkin(
            user_id=user_id,
            checkin_date=checkin_date,
            mood_state=mood_sequence[i]
        )
        checkins.append(checkin)
    
    return checkins


async def create_user_with_retry(
    supabase: AsyncClient,
    role: str,
    max_retries: int = 3
) -> tuple[str, str, str]:
    """
    Create a user with UUID generation and retry logic for duplicates.
    
    Args:
        supabase: AsyncClient for database operations (service role client)
        role: User role (patient or therapist)
        max_retries: Maximum number of retry attempts (default: 3)
        
    Returns:
        Tuple of (user_id, email, password)
        
    Raises:
        HTTPException: If user creation fails after all retries
    """
    for attempt in range(max_retries):
        try:
            # Generate unique credentials (Auth system generates UUID)
            email = fake.unique.email()
            password = fake.password(length=20)
            
            logger.debug(f"Attempt {attempt + 1}/{max_retries}: Creating {role} user with email {email}")
            
            # Create user in Auth (Auth system generates cryptographically secure UUID)
            auth_resp = await supabase.auth.admin.create_user({
                "email": email,
                "password": password,
                "email_confirm": True
            })
            user_id = auth_resp.user.id
            
            logger.debug(f"Auth user created: {user_id}")
            
            # Create profile with is_test_patient flag
            # Using service role client ensures RLS is bypassed
            await supabase.table('profiles').insert({
                "id": user_id,
                "email": email,
                "role": role,
                "is_test_patient": True,
                "updated_at": datetime.now(timezone.utc).isoformat()
            }).execute()
            
            logger.info(f"✓ User {role} created successfully: {user_id} ({email})")
            return user_id, email, password
            
        except APIError as e:
            # Check if it's a duplicate key error
            error_msg = str(e).lower()
            if "duplicate" in error_msg or "unique" in error_msg:
                if attempt < max_retries - 1:
                    logger.warning(f"Duplicate detected on attempt {attempt + 1}, regenerating...")
                    # Reset faker to avoid email conflicts
                    fake.unique.clear()
                    continue
                else:
                    logger.error(f"✗ Failed after {max_retries} attempts due to duplicates")
                    raise HTTPException(
                        status_code=500,
                        detail=f"Failed to create user after {max_retries} attempts (duplicate error)"
                    )
            else:
                # Other API errors should be raised immediately
                logger.error(f"✗ API error creating user: {e}")
                raise HTTPException(
                    status_code=500,
                    detail=f"Error creating user: {str(e)}"
                )
        except Exception as e:
            logger.error(f"✗ Unexpected error creating user: {e}", exc_info=True)
            if attempt < max_retries - 1:
                logger.warning(f"Retrying ({attempt + 2}/{max_retries})...")
                continue
            else:
                raise HTTPException(
                    status_code=500,
                    detail=f"Unexpected error creating user: {str(e)}"
                )
    
    # Should never reach here
    raise HTTPException(
        status_code=500,
        detail="Unknown error in user creation"
    )


async def generate_checkins_for_user(
    supabase: AsyncClient,
    user_id: str,
    num_checkins: int,
    mood_pattern: str
) -> int:
    """
    Generate and insert check-ins for a single user with granular error handling.
    
    This function generates check-ins one by one with try/except per check-in
    to isolate failures and provide detailed logging.
    
    Args:
        supabase: AsyncClient with service role privileges
        user_id: UUID of the user
        num_checkins: Number of check-ins to generate
        mood_pattern: Mood pattern ('stable', 'cycling', or 'random')
        
    Returns:
        Number of successfully inserted check-ins
    """
    logger.debug(f"Generating {num_checkins} check-ins for user {user_id} with pattern '{mood_pattern}'")
    
    # Generate check-ins data
    checkins = generate_user_checkin_history(
        user_id=user_id,
        num_checkins=num_checkins,
        mood_pattern=mood_pattern
    )
    
    inserted_count = 0
    failed_count = 0
    
    # Insert check-ins one by one with granular error handling
    for i, checkin in enumerate(checkins):
        try:
            # Validate JSONB data - ensure all nested objects are proper dicts
            # Convert Pydantic models to dicts if needed
            checkin_data = {
                "user_id": checkin["user_id"],
                "checkin_date": checkin["checkin_date"],  # Already in ISO format
                "sleep_data": checkin["sleep_data"] if isinstance(checkin["sleep_data"], dict) else checkin["sleep_data"],
                "mood_data": checkin["mood_data"] if isinstance(checkin["mood_data"], dict) else checkin["mood_data"],
                "symptoms_data": checkin["symptoms_data"] if isinstance(checkin["symptoms_data"], dict) else checkin["symptoms_data"],
                "risk_routine_data": checkin["risk_routine_data"] if isinstance(checkin["risk_routine_data"], dict) else checkin["risk_routine_data"],
                "appetite_impulse_data": checkin["appetite_impulse_data"] if isinstance(checkin["appetite_impulse_data"], dict) else checkin["appetite_impulse_data"],
                "meds_context_data": checkin["meds_context_data"] if isinstance(checkin["meds_context_data"], dict) else checkin["meds_context_data"]
            }
            
            # Validate date format (should be 'YYYY-MM-DD' or ISO timestamp)
            if "T" not in checkin_data["checkin_date"]:
                logger.warning(f"Check-in {i+1}: Date missing time component, adding it")
                checkin_data["checkin_date"] = f"{checkin_data['checkin_date']}T00:00:00+00:00"
            
            # Insert check-in using service role client (bypasses RLS)
            await supabase.table('check_ins').insert(checkin_data).execute()
            
            inserted_count += 1
            
            if (i + 1) % 10 == 0:
                logger.debug(f"  Progress: {i + 1}/{num_checkins} check-ins inserted for user {user_id[:8]}...")
                
        except APIError as e:
            failed_count += 1
            error_details = str(e)
            logger.error(
                f"✗ Check-in {i+1}/{num_checkins} failed for user {user_id[:8]}: {error_details}\n"
                f"  Date: {checkin.get('checkin_date')}\n"
                f"  JSONB keys: {list(checkin_data.keys())}"
            )
            # Continue to next check-in instead of failing completely
            
        except Exception as e:
            failed_count += 1
            logger.error(
                f"✗ Unexpected error on check-in {i+1}/{num_checkins} for user {user_id[:8]}: {e}",
                exc_info=True
            )
            # Continue to next check-in
    
    if failed_count > 0:
        logger.warning(
            f"User {user_id[:8]}: Inserted {inserted_count}/{num_checkins} check-ins "
            f"({failed_count} failed)"
        )
    else:
        logger.info(f"✓ User {user_id[:8]}: All {inserted_count} check-ins inserted successfully")
    
    return inserted_count


async def generate_and_populate_data(
    supabase: AsyncClient,
    checkins_per_user: int = 30,
    mood_pattern: str = 'stable',
    num_users: Optional[int] = None,
    patients_count: Optional[int] = None,
    therapists_count: Optional[int] = None,
    days_history: Optional[int] = None
) -> Dict[str, Any]:
    """
    Generate and populate synthetic data with service role client.
    
    This function uses the provided supabase client (which should be a service role client)
    to bypass RLS for all operations including user creation and check-in insertion.
    
    Args:
        supabase: AsyncClient with service role privileges
        checkins_per_user: Number of check-ins per patient (default: 30)
        mood_pattern: Mood pattern ('stable', 'cycling', or 'random')
        num_users: Legacy parameter - number of patients to create
        patients_count: Number of patient profiles to create
        therapists_count: Number of therapist profiles to create
        days_history: Alternative to checkins_per_user (1 check-in per day for N days)
        
    Returns:
        Dict with generation statistics
    """
    # Handle parameter compatibility
    if days_history is not None:
        checkins_per_user = days_history
        logger.debug(f"Using days_history parameter: {days_history} check-ins per patient")
    
    if patients_count is not None or therapists_count is not None:
        patients_count = patients_count or 0
        therapists_count = therapists_count or 0
    else:
        patients_count = num_users or 0
        therapists_count = 0

    total_users = patients_count + therapists_count
    
    logger.info("=" * 60)
    logger.info(f"STARTING SYNTHETIC DATA GENERATION")
    logger.info(f"  Patients: {patients_count}")
    logger.info(f"  Therapists: {therapists_count}")
    logger.info(f"  Check-ins per patient: {checkins_per_user}")
    logger.info(f"  Mood pattern: {mood_pattern}")
    logger.info(f"  Using service role client: {type(supabase).__name__}")
    logger.info("=" * 60)

    user_ids: List[str] = []
    patients_created = 0
    therapists_created = 0
    total_checkins_inserted = 0

    try:
        # === CREATE PATIENTS ===
        logger.info(f"\nPhase 1: Creating {patients_count} patient(s)...")
        for i in range(patients_count):
            logger.debug(f"\nCreating patient {i+1}/{patients_count}...")
            
            # Create patient with retry logic
            user_id, email, password = await create_user_with_retry(
                supabase=supabase,
                role="patient",
                max_retries=3
            )
            
            patients_created += 1
            user_ids.append(user_id)

            # Generate and insert check-ins for this patient
            logger.debug(f"Generating check-ins for patient {i+1}...")
            checkins_inserted = await generate_checkins_for_user(
                supabase=supabase,
                user_id=user_id,
                num_checkins=checkins_per_user,
                mood_pattern=mood_pattern
            )
            
            total_checkins_inserted += checkins_inserted
            
            logger.info(
                f"Patient {i+1}/{patients_count} complete: "
                f"{checkins_inserted}/{checkins_per_user} check-ins inserted"
            )

        # === CREATE THERAPISTS ===
        if therapists_count > 0:
            logger.info(f"\nPhase 2: Creating {therapists_count} therapist(s)...")
            for i in range(therapists_count):
                logger.debug(f"\nCreating therapist {i+1}/{therapists_count}...")
                
                # Create therapist with retry logic
                user_id, email, password = await create_user_with_retry(
                    supabase=supabase,
                    role="therapist",
                    max_retries=3
                )
                
                therapists_created += 1
                user_ids.append(user_id)
                
                logger.info(f"Therapist {i+1}/{therapists_count} complete")

        logger.info("\n" + "=" * 60)
        logger.info("GENERATION COMPLETE")
        logger.info(f"  ✓ Patients created: {patients_created}")
        logger.info(f"  ✓ Therapists created: {therapists_created}")
        logger.info(f"  ✓ Total check-ins: {total_checkins_inserted}")
        logger.info(f"  Expected check-ins: {patients_count * checkins_per_user}")
        if total_checkins_inserted < patients_count * checkins_per_user:
            logger.warning(
                f"  ⚠ Missing {patients_count * checkins_per_user - total_checkins_inserted} check-ins "
                f"(check logs for failures)"
            )
        logger.info("=" * 60)

        return {
            "status": "success",
            "message": f"Generated {patients_created} patients and {therapists_created} therapists with {total_checkins_inserted} check-ins",
            "statistics": {
                "patients_created": patients_created,
                "therapists_created": therapists_created,
                "total_checkins": total_checkins_inserted,
                "expected_checkins": patients_count * checkins_per_user,
                "user_ids": user_ids,
                "users_created": total_users,
                "checkins_per_user": checkins_per_user,
                "mood_pattern": mood_pattern,
                "generated_at": datetime.now(timezone.utc).isoformat()
            }
        }

    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    except Exception as e:
        logger.exception("✗ CRITICAL FAILURE in synthetic data generation")
        raise HTTPException(
            status_code=500, 
            detail=f"Error generating synthetic data: {str(e)}"
        )
