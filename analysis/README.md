# Analysis Modules - Legacy Code

## Status: Not Currently Used

The modules in this directory (`clinical_prediction.py`, `self_knowledge.py`, `treatment_optimization.py`, `engagement.py`) are **legacy code** from an earlier implementation and are **not currently being used** in the active API.

## Current Implementation

The current API implementation uses:
- **Models Registry**: `/models/registry.py` - Central model management
- **Feature Engineering**: `/feature_engineering.py` - Data preprocessing
- **API Endpoints**: `/api/*` - Direct model invocation

All predictions are handled directly in the API endpoints using the models registry pattern.

## Recommendations

### Option 1: Remove (Recommended)
These modules can be safely removed as they:
- Are not imported anywhere in the codebase
- Duplicate functionality available in the current API
- Add maintenance overhead
- Contain unused imports and outdated patterns

### Option 2: Refactor
If these modules provide value for future features:
1. Update them to use the centralized models registry
2. Remove unused imports
3. Add proper tests
4. Integrate with the current API architecture
5. Update documentation to reflect their purpose

### Option 3: Archive
Move to a separate `/legacy` or `/archive` directory for historical reference.

## Files in This Directory

- `clinical_prediction.py` - Crisis prediction and state transitions (228 lines)
- `engagement.py` - User engagement analysis (233 lines)
- `self_knowledge.py` - SHAP analysis and clustering (287 lines)
- `treatment_optimization.py` - Treatment optimization (310 lines)

Total: ~1,058 lines of unused code

## Migration Notes

If you need similar functionality:
- Crisis prediction: See `/api/predictions.py` - `run_prediction()` function
- State analysis: See `/api/clinical.py` - `predict_state()` endpoint
- SHAP explanations: Already integrated in prediction endpoints
- Clustering: See `/api/insights.py` - `get_day_profile()` endpoint

## Last Verified

Date: 2025-11-21
All checks confirmed no active imports or usage of these modules.
