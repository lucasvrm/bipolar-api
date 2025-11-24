-- Migration: Performance Indices for Quick Wins
-- Description: Adds database indices to optimize common query patterns for check_ins and predictions tables
-- Version: 011
-- Date: 2025-11-24

-- ============================================================================
-- PART 1: CHECK_INS TABLE INDICES
-- ============================================================================
-- Index on (user_id, checkin_date DESC) for efficient user-specific check-in retrieval
-- Common query pattern: "Get latest check-ins for a user"
-- Using CONCURRENTLY to avoid locking the table during index creation
-- Note: CONCURRENTLY with IF NOT EXISTS is supported in PostgreSQL 9.5+
-- ============================================================================

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_checkins_user_date 
  ON check_ins(user_id, checkin_date DESC);

COMMENT ON INDEX idx_checkins_user_date IS 
  'Optimizes queries filtering by user_id and ordering by checkin_date. Created for performance quick wins.';

-- ============================================================================
-- PART 2: PREDICTIONS TABLE INDICES
-- ============================================================================
-- Index on (user_id, prediction_type) for efficient user-specific prediction retrieval
-- Common query pattern: "Get predictions for a specific user and type"
-- Using CONCURRENTLY to avoid locking the table during index creation
-- Note: CONCURRENTLY with IF NOT EXISTS is supported in PostgreSQL 9.5+
-- ============================================================================

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_predictions_user_type 
  ON predictions(user_id, prediction_type);

COMMENT ON INDEX idx_predictions_user_type IS 
  'Optimizes queries filtering by user_id and prediction_type. Created for performance quick wins.';

-- ============================================================================
-- PART 3: VERIFICATION AND DOCUMENTATION
-- ============================================================================

DO $$
BEGIN
  RAISE NOTICE '✓ Migration 011 completed successfully';
  RAISE NOTICE '✓ Created index: idx_checkins_user_date on check_ins(user_id, checkin_date DESC)';
  RAISE NOTICE '✓ Created index: idx_predictions_user_type on predictions(user_id, prediction_type)';
  RAISE NOTICE 'ℹ Indices created with CONCURRENTLY for zero-downtime deployment';
  RAISE NOTICE 'ℹ Requires PostgreSQL 9.5+ for CONCURRENTLY IF NOT EXISTS support';
  RAISE NOTICE 'ℹ Expected impact: Faster queries on check_ins and predictions tables';
END $$;
