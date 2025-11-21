"""
Tests for synthetic data management endpoints.

Tests verify the new admin endpoints for synthetic data cleaning,
exporting, and test flag toggling.
"""
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import HTTPException


class MockSupabaseResponse:
    """Mock response from Supabase"""
    def __init__(self, data, count=None):
        self.data = data
        self.count = count


class TestSyntheticDataSchemas:
    """Tests for synthetic data schemas and validation."""

    def test_clean_data_request_validation(self):
        """Test CleanDataRequest validation."""
        from api.schemas.synthetic_data import CleanDataRequest
        
        # Valid requests
        req1 = CleanDataRequest(action="delete_all")
        assert req1.action == "delete_all"
        
        req2 = CleanDataRequest(action="delete_last_n", quantity=10)
        assert req2.quantity == 10
        
        req3 = CleanDataRequest(action="delete_before_date", before_date="2024-01-01T00:00:00Z")
        assert req3.before_date == "2024-01-01T00:00:00Z"

    def test_clean_data_response_structure(self):
        """Test CleanDataResponse structure."""
        from api.schemas.synthetic_data import CleanDataResponse
        
        response = CleanDataResponse(
            status="success",
            message="Deleted 5 patients",
            deleted_count=5
        )
        
        assert response.status == "success"
        assert response.deleted_count == 5

    def test_enhanced_stats_response_structure(self):
        """Test EnhancedStatsResponse structure."""
        from api.schemas.synthetic_data import EnhancedStatsResponse
        
        response = EnhancedStatsResponse(
            total_users=100,
            total_checkins=1000,
            real_patients_count=80,
            synthetic_patients_count=20,
            checkins_today=10,
            checkins_last_7_days=70,
            checkins_last_7_days_previous=65,
            avg_checkins_per_active_patient=3.5,
            avg_adherence_last_30d=0.85,
            avg_current_mood=3.0,
            mood_distribution={"stable": 50, "depression": 20, "mania": 10},
            critical_alerts_last_30d=5,
            patients_with_recent_radar=10
        )
        
        assert response.total_users == 100
        assert response.real_patients_count == 80
        assert response.synthetic_patients_count == 20
        assert isinstance(response.mood_distribution, dict)


class TestToggleTestFlag:
    """Tests for PATCH /admin/patients/:id/toggle-test-flag endpoint."""

    @pytest.mark.asyncio
    async def test_toggle_flag_from_false_to_true(self):
        """Test toggling flag from false to true."""
        from api.admin import toggle_test_patient_flag
        
        patient_id = "user123"
        
        mock_client = MagicMock()
        
        # Mock for select query (get patient)
        async def mock_get_execute():
            return MockSupabaseResponse(data=[{"id": patient_id, "is_test_patient": False}])
        
        # Mock for update query
        async def mock_update_execute():
            return MockSupabaseResponse(data=[{"id": patient_id, "is_test_patient": True}])
        
        get_chain = MagicMock()
        get_chain.execute = mock_get_execute
        get_chain.eq = MagicMock(return_value=get_chain)
        
        update_chain = MagicMock()
        update_chain.execute = mock_update_execute
        update_chain.eq = MagicMock(return_value=update_chain)
        
        # Track which chain to return based on call
        call_count = [0]
        
        def table_side_effect(*args):
            # First call is select, second is update
            call_count[0] += 1
            if call_count[0] == 1:
                chain = MagicMock()
                chain.select = MagicMock(return_value=get_chain)
                return chain
            else:
                chain = MagicMock()
                chain.update = MagicMock(return_value=update_chain)
                return chain
        
        mock_client.table = MagicMock(side_effect=table_side_effect)
        
        result = await toggle_test_patient_flag(patient_id, mock_client)
        
        assert result.id == patient_id
        assert result.is_test_patient is True

    @pytest.mark.asyncio
    async def test_toggle_flag_patient_not_found(self):
        """Test toggling flag for non-existent patient."""
        from api.admin import toggle_test_patient_flag
        
        patient_id = "nonexistent"
        
        mock_client = MagicMock()
        
        async def mock_execute():
            return MockSupabaseResponse(data=[])
        
        mock_chain = MagicMock()
        mock_chain.execute = mock_execute
        mock_chain.select = MagicMock(return_value=mock_chain)
        mock_chain.eq = MagicMock(return_value=mock_chain)
        
        mock_client.table = MagicMock(return_value=mock_chain)
        
        with pytest.raises(HTTPException) as exc_info:
            await toggle_test_patient_flag(patient_id, mock_client)
        
        assert exc_info.value.status_code == 404


class TestEnhancedStats:
    """Tests for enhanced GET /admin/stats endpoint."""

    @pytest.mark.asyncio
    async def test_enhanced_stats_returns_all_fields(self):
        """Test that enhanced stats returns all required fields."""
        from api.admin import get_admin_stats
        
        mock_client = MagicMock()
        
        # Create different responses for different queries
        responses = {
            'profiles_count': MockSupabaseResponse(data=[], count=10),
            'checkins_count': MockSupabaseResponse(data=[], count=100),
            'profiles_data': MockSupabaseResponse(data=[
                {"id": "user1", "email": "test@example.com", "is_test_patient": True, "role": "patient"},
                {"id": "user2", "email": "real@gmail.com", "is_test_patient": False, "role": "patient"},
            ]),
            'checkins_data': MockSupabaseResponse(data=[]),
            'checkins_30d': MockSupabaseResponse(data=[
                {
                    "user_id": "user2",
                    "checkin_date": "2024-01-01T00:00:00Z",
                    "mood_data": {"depressedMood": 2, "elevatedMood": 5, "activation": 5},
                    "meds_context_data": {"medication_adherence": 0.9}
                }
            ]),
        }
        
        call_order = ['profiles_count', 'checkins_count', 'profiles_data', 
                      'checkins_data', 'checkins_data', 'checkins_data', 'checkins_30d']
        call_index = [0]
        
        async def mock_execute():
            response_key = call_order[call_index[0] % len(call_order)]
            call_index[0] += 1
            return responses[response_key]
        
        mock_chain = MagicMock()
        mock_chain.execute = mock_execute
        mock_chain.select = MagicMock(return_value=mock_chain)
        mock_chain.gte = MagicMock(return_value=mock_chain)
        mock_chain.lt = MagicMock(return_value=mock_chain)
        
        mock_client.table = MagicMock(return_value=mock_chain)
        
        result = await get_admin_stats(mock_client)
        
        # Verify all required fields are present
        assert hasattr(result, 'total_users')
        assert hasattr(result, 'total_checkins')
        assert hasattr(result, 'real_patients_count')
        assert hasattr(result, 'synthetic_patients_count')
        assert hasattr(result, 'checkins_today')
        assert hasattr(result, 'checkins_last_7_days')
        assert hasattr(result, 'checkins_last_7_days_previous')
        assert hasattr(result, 'avg_checkins_per_active_patient')
        assert hasattr(result, 'avg_adherence_last_30d')
        assert hasattr(result, 'avg_current_mood')
        assert hasattr(result, 'mood_distribution')
        assert hasattr(result, 'critical_alerts_last_30d')
        assert hasattr(result, 'patients_with_recent_radar')
        
        # Verify counts
        assert result.total_users == 10
        assert result.total_checkins == 100
        assert result.real_patients_count == 1
        assert result.synthetic_patients_count == 1
        assert isinstance(result.mood_distribution, dict)

