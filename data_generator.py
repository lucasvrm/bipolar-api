# data_generator.py
"""
Data generator module for creating synthetic realistic bipolar disorder check-in data.

This module provides functionality to generate synthetic patient data with realistic
patterns for bipolar disorder monitoring, including mood states, sleep patterns,
medication adherence, and other clinical markers.
"""
import numpy as np
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
    Generate a single realistic check-in with correlated features.
    
    Features are generated with realistic correlations:
    - Manic states: less sleep, higher energy, elevated mood
    - Depressed states: more sleep, lower energy, depressed mood
    - Euthymic states: balanced values
    - Mixed states: combination of manic and depressive features
    
    Args:
        user_id: The user ID for this check-in
        checkin_date: The date/time of the check-in
        mood_state: Optional mood state ('MANIC', 'DEPRESSED', 'EUTHYMIC', 'MIXED')
                   If not provided, randomly selected
    
    Returns:
        Dictionary with realistic check-in data
    """
    # Define mood state if not provided
    if mood_state is None:
        mood_state = random.choices(
            ['EUTHYMIC', 'DEPRESSED', 'MANIC', 'MIXED'],
            weights=[0.5, 0.25, 0.15, 0.10]  # Euthymic is most common
        )[0]
    
    # Base parameters for different mood states
    if mood_state == 'MANIC':
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
        impulse_episode = random.choice([0, 1])
        compulsion_episode = random.choice([0, 1])
        compulsion_intensity = random.randint(3, 5) if compulsion_episode else 0
    elif mood_state == 'DEPRESSED':
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
        impulse_episode = 0
        compulsion_episode = 0
        compulsion_intensity = 0
    elif mood_state == 'MIXED':
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
        impulse_episode = random.choice([0, 1])
        compulsion_episode = random.choice([0, 1])
        compulsion_intensity = random.randint(2, 4) if compulsion_episode else 0
    else:  # EUTHYMIC
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
        impulse_episode = 0
        compulsion_episode = 0
        compulsion_intensity = 0
    
    # Generate medication adherence (higher for euthymic patients)
    if mood_state == 'EUTHYMIC':
        medication_adherence = random.choice([1, 1, 1, 0])  # 75% adherent
    else:
        medication_adherence = random.choice([1, 1, 0, 0])  # 50% adherent
    
    # Medication timing (only relevant if adherent)
    medication_timing = random.randint(0, 1) if medication_adherence else 0
    
    # Tasks and motivation
    tasks_planned = random.randint(1, 10)
    if mood_state == 'MANIC':
        tasks_completed = min(tasks_planned, random.randint(tasks_planned, tasks_planned + 5))
        motivation = random.randint(8, 10)
    elif mood_state == 'DEPRESSED':
        tasks_completed = max(0, random.randint(0, tasks_planned // 2))
        motivation = random.randint(1, 4)
    else:
        tasks_completed = random.randint(tasks_planned // 2, tasks_planned)
        motivation = random.randint(4, 8)
    
    # Social and contextual factors
    social_connection = 10 - anxiety_stress // 2 + random.randint(-2, 2)
    social_connection = max(0, min(10, social_connection))
    
    contextual_stressors = random.randint(0, 1)
    social_rhythm_event = random.randint(0, 1)
    
    # Exercise
    exercise_duration = 0
    exercise_feeling = 0
    if energy_level >= 5:
        if random.random() < 0.4:  # 40% chance of exercise when energy is good
            exercise_duration = random.randint(15, 90)
            exercise_feeling = random.randint(5, 10)
    
    # Substance use (more likely in manic/mixed states)
    substance_usage = 0
    substance_units = 0
    if mood_state in ['MANIC', 'MIXED']:
        if random.random() < 0.3:  # 30% chance
            substance_usage = 1
            substance_units = random.randint(1, 5)
    
    # Sleep details
    sleep_hygiene = random.randint(4, 9) if sleep_quality > 5 else random.randint(2, 6)
    perceived_sleep_need = round(random.uniform(7.0, 9.0), 1)
    has_napped = random.choice([0, 1]) if energy_level < 5 else 0
    napping_duration = random.randint(15, 120) if has_napped else 0
    
    # Diet and appetite
    general_appetite = energy_level + random.randint(-2, 2)
    general_appetite = max(0, min(10, general_appetite))
    skip_meals = random.choice([0, 1]) if mood_state == 'DEPRESSED' else 0
    diet_tracking = random.randint(0, 1)
    
    # Cognitive factors
    memory_concentration = 10 - distractibility + random.randint(-1, 1)
    memory_concentration = max(0, min(10, memory_concentration))
    rumination_axis = depressed_mood // 2 + random.randint(0, 3)
    rumination_axis = max(0, min(10, rumination_axis))
    
    # Caffeine (inversely related to sleep quality usually)
    caffeine_doses = random.randint(0, 5) if sleep_quality < 6 else random.randint(0, 3)
    
    # Sexual risk behavior (more in manic states)
    sexual_risk = 1 if (mood_state == 'MANIC' and random.random() < 0.2) else 0
    
    # Recent medication changes
    medication_change_recent = random.choice([0, 1]) if random.random() < 0.1 else 0
    
    return {
        "user_id": user_id,
        "checkin_date": checkin_date.isoformat(),
        # Core features
        "hoursSlept": sleep_hours,
        "sleepQuality": sleep_quality,
        "energyLevel": energy_level,
        "depressedMood": depressed_mood,
        "anxietyStress": anxiety_stress,
        "activation": activation,
        "elevation": elevation,
        # Medication
        "medicationAdherence": medication_adherence,
        "medicationTiming": medication_timing,
        "medicationChangeRecent": medication_change_recent,
        # Sleep details
        "sleepHygiene": sleep_hygiene,
        "perceivedSleepNeed": perceived_sleep_need,
        "hasNapped": has_napped,
        "nappingDurationMin": napping_duration,
        # Cognitive and behavioral
        "thoughtSpeed": thought_speed,
        "distractibility": distractibility,
        "libido": libido,
        "motivationToStart": motivation,
        "memoryConcentration": memory_concentration,
        "ruminationAxis": rumination_axis,
        # Tasks
        "tasksPlanned": tasks_planned,
        "tasksCompleted": tasks_completed,
        # Social
        "socialConnection": social_connection,
        "contextualStressors": contextual_stressors,
        "socialRhythmEvent": social_rhythm_event,
        # Impulse/compulsion
        "compulsionEpisode": compulsion_episode,
        "compulsionIntensity": compulsion_intensity,
        "sexualRiskBehavior": sexual_risk,
        # Substances
        "caffeineDoses": caffeine_doses,
        "substanceUsage": substance_usage,
        "substanceUnits": substance_units,
        # Exercise
        "exerciseDurationMin": exercise_duration,
        "exerciseFeeling": exercise_feeling,
        # Diet
        "dietTracking": diet_tracking,
        "generalAppetite": general_appetite,
        "skipMeals": skip_meals,
    }


def generate_user_checkin_history(
    user_id: str,
    num_checkins: int = 30,
    start_date: Optional[datetime] = None,
    mood_pattern: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Generate a realistic history of check-ins for a user.
    
    Creates a series of check-ins with temporal consistency, where mood states
    tend to persist for realistic durations before transitioning.
    
    Args:
        user_id: The user ID for these check-ins
        num_checkins: Number of check-ins to generate
        start_date: Starting date for the history (defaults to 30 days ago)
        mood_pattern: Optional pattern ('stable', 'cycling', 'random')
                     'stable': mostly euthymic with occasional episodes
                     'cycling': regular cycling between states
                     'random': completely random (default)
    
    Returns:
        List of check-in dictionaries ordered by date
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
            # Mostly euthymic with occasional brief episodes
            if mood_duration == 0:
                # Start a new mood period
                if random.random() < 0.15:  # 15% chance of episode
                    current_mood = random.choice(['DEPRESSED', 'MANIC', 'MIXED'])
                    mood_duration = random.randint(3, 10)  # Episodes last 3-10 days
                else:
                    current_mood = 'EUTHYMIC'
                    mood_duration = random.randint(5, 20)  # Euthymic periods last longer
            else:
                mood_duration -= 1
                
        elif mood_pattern == 'cycling':
            # Regular cycling pattern
            cycle_day = i % 28  # 4-week cycle
            if cycle_day < 7:
                current_mood = 'EUTHYMIC'
            elif cycle_day < 14:
                current_mood = 'MANIC'
            elif cycle_day < 21:
                current_mood = 'EUTHYMIC'
            else:
                current_mood = 'DEPRESSED'
        else:
            # Random pattern - mood changes every 3-7 days
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
    
    This is the main function called by the admin endpoint.
    
    Args:
        supabase: Authenticated Supabase client
        num_users: Number of users to generate data for
        checkins_per_user: Number of check-ins per user
        mood_pattern: Mood pattern for all users ('stable', 'cycling', 'random')
    
    Returns:
        Dictionary with generation statistics
    """
    logger.info(f"Starting data generation: {num_users} users, {checkins_per_user} check-ins each")
    
    all_checkins = []
    user_ids = []
    
    try:
        # Generate data for each user
        for i in range(num_users):
            # Generate a realistic user ID (UUID format)
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
