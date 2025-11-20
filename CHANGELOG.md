# Changelog

All notable changes to the Bipolar AI Engine project will be documented in this file.

## [3.0.0] - 2025-11-20

### Added - Major Platform Expansion

#### New Architecture
- Modular directory structure with `analysis/`, `features/`, and `models/` directories
- Separated concerns into specialized modules for maintainability

#### Feature Engineering Module (`features/engineering.py`)
- `compute_basic_features()` - Extract direct patient features
- `compute_time_series_features()` - Calculate rolling statistics and trends
- `prepare_model_input()` - Unified feature preparation with proper type handling

#### Clinical Prediction Module (`analysis/clinical_prediction.py`)
- **NEW ENDPOINT**: `POST /predict/crisis/7d` - 7-day crisis prediction
- **NEW ENDPOINT**: `POST /predict/state/3d` - Multi-class state transition prediction (Stable/Depressive/Manic/Mixed)
- **NEW ENDPOINT**: `POST /predict/impulsive_behavior/2d` - 2-day impulsive behavior risk prediction
- Heuristic fallbacks for all predictions when models aren't trained
- Smart risk level categorization

#### Self-Knowledge Analysis Module (`analysis/self_knowledge.py`)
- **ENHANCED**: `POST /predict?include_shap=true` - Added optional SHAP analysis to original endpoint
- **NEW ENDPOINT**: `GET /patient/{id}/triggers` - Environmental triggers and stressor pattern analysis
- **NEW ENDPOINT**: `GET /patient/{id}/mood_clusters` - K-Means clustering of mood states
- NLP-based sentiment analysis of patient notes
- Automatic cluster labeling based on characteristics

#### Treatment Optimization Module (`analysis/treatment_optimization.py`)
- **NEW ENDPOINT**: `POST /predict/medication_adherence/3d` - Medication non-adherence risk prediction
- **NEW ENDPOINT**: `POST /analyze/medication_impact` - Causal analysis of medication changes
- **NEW ENDPOINT**: `GET /patient/{id}/habit_optimization` - Habit-mood correlation analysis
- Before/after statistical comparison for medication impact
- Personalized recommendations for each analysis

#### Engagement Analysis Module (`analysis/engagement.py`)
- **NEW ENDPOINT**: `GET /patient/{id}/churn_risk` - User churn risk prediction
- Engagement metrics calculation (consistency, completeness, trends)
- Survival analysis framework ready for Cox Proportional Hazards model
- Risk factor identification and recommendations

#### API Enhancements
- **NEW ENDPOINT**: `GET /api/info` - Comprehensive API documentation endpoint
- Enhanced health check with module status
- Version bumped to 3.0
- Improved error handling and type safety

#### Dependencies Added
- `shap` - For model explainability and root cause analysis
- `lifelines` - For survival analysis and churn prediction
- `nltk` - For natural language processing of patient notes
- `scipy` - For advanced statistical analyses

#### Documentation
- **NEW**: Comprehensive README.md with:
  - Complete API documentation for all endpoints
  - Request/response examples
  - Installation instructions
  - Usage examples in Python
  - Architecture overview
- **NEW**: This CHANGELOG.md

### Changed

#### Existing Endpoints
- `POST /predict` - Now supports optional `?include_shap=true` parameter for explainability
- Enhanced response includes `timeframe_days` field
- Better error messages and validation

#### Code Quality
- All functions include comprehensive docstrings
- Fixed numpy/pandas type conversions for proper JSON serialization
- Proper categorical feature handling for LightGBM compatibility
- Consistent error handling across all modules

### Technical Details

#### Type Safety Improvements
- All pandas/numpy types properly converted to Python native types
- Categorical features handled explicitly ('sex', 'diagnosis_state_ground_truth')
- JSON serialization verified for all endpoints

#### Model Management
- Centralized model loading in startup event
- Graceful fallbacks when models aren't available
- Clear indication in responses when using heuristics vs. trained models

### Testing
- All 8 core endpoints tested and passing
- SHAP analysis validated with categorical features
- Server startup validated
- No security vulnerabilities (CodeQL scan passed)

### Future Roadmap
- Train dedicated models for T+7 crisis, state transition, impulsive behavior
- Implement full propensity score matching for medication analysis
- Add multi-language support for NLP analysis
- Implement model retraining endpoints
- Add visualization dashboard

---

## [2.0.0] - Previous Version

### Existing Features
- `POST /predict` - 3-day binary crisis prediction
- LightGBM model with 65 features
- Basic feature auto-completion
- CORS configuration for frontend apps

---

**Note**: Version 3.0.0 represents a complete platform expansion, transforming the API from a simple crisis alert system to a comprehensive clinical insight and self-knowledge platform with 10 distinct predictive analyses.
