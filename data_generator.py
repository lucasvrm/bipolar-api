"""
Data generator module for creating synthetic realistic bipolar disorder check-in data.

This module provides functionality to generate synthetic patient data with realistic
patterns for bipolar disorder monitoring, mapped correctly to the database JSONB schema.
"""
import random
from datetime import datetime, timedelta, timezone
from faker import Faker
from typing import List, Dict, Any, Optional
from supabase import AsyncClient
import logging

# Use a specific locale for consistency
fake = Faker('pt_BR')
logger = logging.getLogger("bipolar-api.data_generator")


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
    social_rhythm_event = 1 if random.random() < 0.15 else 0 # Ex: travel, shift change
    
    # Exercise logic
    exercise_duration = 0
    exercise_feeling = 0
    if energy_level >= 4 and random.random() < 0.4:
        exercise_duration = random.randint(15, 90)
        exercise_feeling = random.randint(5, 10)

    # Substance use logic
    substance_usage = 0
    substance_units = 0
    caffeine_doses = random.randint(0, 4)
    if mood_state in ['MANIC', 'MIXED'] and random.random() < 0.3:
        substance_usage = 1
        substance_units = random.randint(1, 5)

    # Sleep details
    sleep_hygiene = random.randint(4, 9) if sleep_quality > 5 else random.randint(1, 5)
    perceived_sleep_need = round(random.uniform(7.0, 9.0), 1)
    has_napped = 1 if (energy_level < 5 and random.random() < 0.4) else 0
    napping_duration = random.randint(20, 90) if has_napped else 0

    # Diet / Cognitive
    general_appetite = max(0, min(10, energy_level + random.randint(-2, 2)))
    skip_meals = 1 if (mood_state == 'DEPRESSED' and random.random() < 0.4) else 0
    diet_tracking = random.choice([0, 1])
    memory_concentration = max(0, min(10, 10 - distractibility))
    rumination_axis = max(0, min(10, depressed_mood + random.randint(-1, 2)))
    sexual_risk = 1 if (mood_state == 'MANIC' and random.random() < 0.25) else 0

    # --- 2. Map Raw Values to JSONB Schema Structure ---
    
    sleep_data = {
        "hoursSlept": sleep_hours,
        "sleepQuality": sleep_quality,
        "perceivedSleepNeed": perceived_sleep_need,
        "sleepHygiene": sleep_hygiene,
        "hasNapped": has_napped,
        "nappingDurationMin": napping_duration
    }

    mood_data = {
        "energyLevel": energy_level,
        "depressedMood": depressed_mood,
        "anxietyStress": anxiety_stress,
        "elevation": elevation,
        "activation": activation,
        "motivationToStart": motivation
    }

    symptoms_data = {
        "thoughtSpeed": thought_speed,
        "distractibility": distractibility,
        "memoryConcentration": memory_concentration,
        "ruminationAxis": rumination_axis
    }

    risk_routine_data = {
        "socialConnection": social_connection,
        "socialRhythmEvent": social_rhythm_event,
        "exerciseDurationMin": exercise_duration,
        "exerciseFeeling": exercise_feeling,
        "sexualRiskBehavior": sexual_risk,
        "tasksPlanned": tasks_planned,
        "tasksCompleted": tasks_completed
    }

    appetite_impulse_data = {
        "generalAppetite": general_appetite,
        "dietTracking": diet_tracking,
        "skipMeals": skip_meals,
        "compulsionEpisode": compulsion_episode,
        "compulsionIntensity": compulsion_intensity,
        "substanceUsage": substance_usage,
        "substanceUnits": substance_units,
        "caffeineDoses": caffeine_doses,
        "libido": libido
    }

    meds_context_data = {
        "medicationAdherence": medication_adherence,
        "medicationTiming": medication_timing,
        "medicationChangeRecent": medication_change_recent,
        "contextualStressors": contextual_stressors
    }

    return {
        "user_id": user_id,
        "checkin_date": checkin_date.strftime('%Y-%m-%d'), # Date type in DB
        "sleep_data": sleep_data,
        "mood_data": mood_data,
        "symptoms_data": symptoms_data,
        "risk_routine_data": risk_routine_data,
        "appetite_impulse_data": appetite_impulse_data,
        "meds_context_data": meds_context_data,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat()
    }


def generate_user_checkin_history(
    user_id: str,
    num_checkins: int = 30,
    start_date: Optional[datetime] = None,
    mood_pattern: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Generate a realistic history of check-ins for a user.
    """
    if start_date is None:
        start_date = datetime.now(timezone.utc) - timedelta(days=num_checkins)
    
    checkins = []
    current_mood = 'EUTHYMIC'
    mood_duration = 0
    
    for i in range(num_checkins):
        checkin_date = start_date + timedelta(days=i)
        
        # Determine mood state based on pattern
        if mood_pattern == 'stable':
            if mood_duration == 0:
                if random.random() < 0.15:
                    current_mood = random.choice(['DEPRESSED', 'MANIC', 'MIXED'])
                    mood_duration = random.randint(3, 10)
                else:
                    current_mood = 'EUTHYMIC'
                    mood_duration = random.randint(5, 20)
            else:
                mood_duration -= 1
                
        elif mood_pattern == 'cycling':
            cycle_day = i % 28
            if cycle_day < 7: current_mood = 'EUTHYMIC'
            elif cycle_day < 14: current_mood = 'MANIC'
            elif cycle_day < 21: current_mood = 'EUTHYMIC'
            else: current_mood = 'DEPRESSED'
        else:
            # Random
            if mood_duration == 0:
                current_mood = random.choice(['EUTHYMIC', 'DEPRESSED', 'MANIC', 'MIXED'])
                mood_duration = random.randint(3, 7)
            else:
                mood_duration -= 1
        
        checkin = generate_realistic_checkin(user_id, checkin_date, current_mood)
        checkins.append(checkin)
    
    return checkins


async def generate_and_populate_data(
    supabase: AsyncClient,
    num_users: int = 5,
    checkins_per_user: int = 30,
    mood_pattern: str = 'stable'
) -> Dict[str, Any]:
    """
    Generate synthetic data for multiple users and insert into database.
    """
    logger.info(f"Starting data generation: {num_users} users, {checkins_per_user} check-ins each")
    
    all_checkins = []
    user_ids = []
    
    try:
        for i in range(num_users):
            user_id = fake.uuid4()
            user_ids.append(user_id)
            
            # Generate check-in history for this user
            checkins = generate_user_checkin_history(
                user_id=user_id,
                num_checkins=checkins_per_user,
                mood_pattern=mood_pattern
            )
            
            all_checkins.extend(checkins)
            logger.debug(f"Generated {len(checkins)} check-ins for user {i+1}/{num_users}")
        
        # Insert all check-ins into database
        # Supabase/PostgREST handles JSONB serialization automatically from dicts
        logger.info(f"Inserting {len(all_checkins)} check-ins into database...")
        response = await supabase.table('check_ins').insert(all_checkins).execute()
        
        inserted_count = len(response.data) if response.data else 0
        logger.info(f"Successfully inserted {inserted_count} check-ins")
        
        return {
            "status": "success",
            "message": f"Generated and inserted {inserted_count} check-ins for {num_users} users",
            "statistics": {
                "users_created": num_users,
                "user_ids": user_ids,
                "checkins_per_user": checkins_per_user,
                "total_checkins": inserted_count,
                "mood_pattern": mood_pattern,
                "generated_at": datetime.now(timezone.utc).isoformat()
            }
        }
        
    except Exception as e:
        logger.exception(f"Error generating and populating data: {e}")
        raise
