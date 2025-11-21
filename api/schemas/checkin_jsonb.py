"""
Pydantic models for check-in JSONB data structures.

These models ensure type safety and validation for the JSONB columns
in the check_ins table.
"""
from pydantic import BaseModel, Field
from typing import Optional


class SleepData(BaseModel):
    """Sleep-related data stored in the sleep_data JSONB column."""
    
    hoursSlept: float = Field(..., ge=0, le=24, description="Hours slept (0-24)")
    sleepQuality: int = Field(..., ge=0, le=10, description="Sleep quality rating (0-10)")
    perceivedSleepNeed: float = Field(..., ge=0, le=24, description="Perceived sleep need in hours (0-24)")
    sleepHygiene: int = Field(..., ge=0, le=10, description="Sleep hygiene rating (0-10)")
    hasNapped: int = Field(..., ge=0, le=1, description="Whether the person napped (0 or 1)")
    nappingDurationMin: int = Field(..., ge=0, description="Napping duration in minutes")


class MoodData(BaseModel):
    """Mood-related data stored in the mood_data JSONB column."""
    
    energyLevel: int = Field(..., ge=0, le=10, description="Energy level (0-10)")
    depressedMood: int = Field(..., ge=0, le=10, description="Depressed mood rating (0-10)")
    anxietyStress: int = Field(..., ge=0, le=10, description="Anxiety/stress level (0-10)")
    elevation: int = Field(..., ge=0, le=10, description="Mood elevation (0-10)")
    activation: int = Field(..., ge=0, le=10, description="Activation level (0-10)")
    motivationToStart: int = Field(..., ge=0, le=10, description="Motivation to start tasks (0-10)")


class SymptomsData(BaseModel):
    """Cognitive symptoms data stored in the symptoms_data JSONB column."""
    
    thoughtSpeed: int = Field(..., ge=0, le=10, description="Thought speed (0-10)")
    distractibility: int = Field(..., ge=0, le=10, description="Distractibility level (0-10)")
    memoryConcentration: int = Field(..., ge=0, le=10, description="Memory/concentration (0-10)")
    ruminationAxis: int = Field(..., ge=0, le=10, description="Rumination level (0-10)")


class RiskRoutineData(BaseModel):
    """Risk and routine data stored in the risk_routine_data JSONB column."""
    
    socialConnection: int = Field(..., ge=0, le=10, description="Social connection level (0-10)")
    socialRhythmEvent: int = Field(..., ge=0, le=1, description="Social rhythm event occurred (0 or 1)")
    exerciseDurationMin: int = Field(..., ge=0, description="Exercise duration in minutes")
    exerciseFeeling: int = Field(..., ge=0, le=10, description="Exercise feeling rating (0-10)")
    sexualRiskBehavior: int = Field(..., ge=0, le=1, description="Sexual risk behavior (0 or 1)")
    tasksPlanned: int = Field(..., ge=0, description="Number of tasks planned")
    tasksCompleted: int = Field(..., ge=0, description="Number of tasks completed")


class AppetiteImpulseData(BaseModel):
    """Appetite and impulse control data stored in the appetite_impulse_data JSONB column."""
    
    generalAppetite: int = Field(..., ge=0, le=10, description="General appetite level (0-10)")
    dietTracking: int = Field(..., ge=0, le=1, description="Diet tracking (0 or 1)")
    skipMeals: int = Field(..., ge=0, le=1, description="Skipped meals (0 or 1)")
    compulsionEpisode: int = Field(..., ge=0, le=1, description="Compulsion episode (0 or 1)")
    compulsionIntensity: int = Field(..., ge=0, le=10, description="Compulsion intensity (0-10)")
    substanceUsage: int = Field(..., ge=0, le=1, description="Substance usage (0 or 1)")
    substanceUnits: int = Field(..., ge=0, description="Number of substance units")
    caffeineDoses: int = Field(..., ge=0, description="Number of caffeine doses")
    libido: int = Field(..., ge=0, le=10, description="Libido level (0-10)")


class MedsContextData(BaseModel):
    """Medication and context data stored in the meds_context_data JSONB column."""
    
    medicationAdherence: int = Field(..., ge=0, le=1, description="Medication adherence (0 or 1)")
    medicationTiming: int = Field(..., ge=0, le=1, description="Medication timing (0 or 1)")
    medicationChangeRecent: int = Field(..., ge=0, le=1, description="Recent medication change (0 or 1)")
    contextualStressors: int = Field(..., ge=0, le=1, description="Contextual stressors present (0 or 1)")
