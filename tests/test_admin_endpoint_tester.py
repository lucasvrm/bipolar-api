"""
Unit tests for the admin endpoint production testing script.

These tests ensure the testing script itself is reliable and functions correctly.
"""

import unittest
from unittest.mock import Mock, patch, MagicMock
import json
import os
import sys
import tempfile
from datetime import datetime, timezone

# Add tools directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'tools'))

from test_admin_endpoints_production import (
    AdminEndpointTester,
    EndpointTestResult,
    TestReport
)


class TestEndpointTestResult(unittest.TestCase):
    """Test the EndpointTestResult data class"""
    
    def test_creation_with_minimal_data(self):
        """Test creating result with minimal required data"""
        result = EndpointTestResult(
            endpoint="/api/admin/stats",
            method="GET",
            status_code=200,
            latency_ms=123.45,
            success=True
        )
        
        self.assertEqual(result.endpoint, "/api/admin/stats")
        self.assertEqual(result.method, "GET")
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.latency_ms, 123.45)
        self.assertTrue(result.success)
        self.assertIsNone(result.response_data)
        self.assertIsNone(result.error_message)
        self.assertIsNotNone(result.timestamp)
    
    def test_creation_with_full_data(self):
        """Test creating result with all optional data"""
        response_data = {"total_users": 100}
        
        result = EndpointTestResult(
            endpoint="/api/admin/users",
            method="GET",
            status_code=200,
            latency_ms=234.56,
            success=True,
            response_data=response_data,
            error_message=None
        )
        
        self.assertEqual(result.response_data, response_data)
        self.assertIsNone(result.error_message)
    
    def test_failed_result(self):
        """Test creating a failed result"""
        result = EndpointTestResult(
            endpoint="/api/admin/stats",
            method="GET",
            status_code=500,
            latency_ms=100.0,
            success=False,
            error_message="Internal Server Error"
        )
        
        self.assertFalse(result.success)
        self.assertEqual(result.error_message, "Internal Server Error")


class TestTestReport(unittest.TestCase):
    """Test the TestReport data class"""
    
    def test_creation(self):
        """Test creating a basic report"""
        report = TestReport(
            correlation_id="test-123",
            start_time_utc="2024-01-15T10:00:00Z",
            end_time_utc="2024-01-15T10:05:00Z"
        )
        
        self.assertEqual(report.correlation_id, "test-123")
        self.assertEqual(report.start_time_utc, "2024-01-15T10:00:00Z")
        self.assertEqual(report.end_time_utc, "2024-01-15T10:05:00Z")
        self.assertEqual(report.overall_status, "OK")
        self.assertEqual(len(report.endpoints_tested), 0)
        self.assertEqual(len(report.structural_issues), 0)
        self.assertEqual(len(report.inconsistencies), 0)
    
    def test_to_dict(self):
        """Test converting report to dictionary"""
        report = TestReport(
            correlation_id="test-456",
            start_time_utc="2024-01-15T10:00:00Z",
            end_time_utc="2024-01-15T10:05:00Z"
        )
        
        report_dict = report.to_dict()
        
        self.assertIsInstance(report_dict, dict)
        self.assertEqual(report_dict["correlation_id"], "test-456")
        self.assertIn("overall_status", report_dict)
        self.assertIn("latencies", report_dict)


class TestAdminEndpointTester(unittest.TestCase):
    """Test the AdminEndpointTester class"""
    
    def setUp(self):
        """Set up test fixtures"""
        self.test_token = "test-admin-token-123"
        self.tester = AdminEndpointTester(self.test_token)
    
    def test_initialization(self):
        """Test tester initialization"""
        self.assertEqual(self.tester.admin_token, self.test_token)
        self.assertIsNotNone(self.tester.correlation_id)
        self.assertIsNotNone(self.tester.start_timestamp)
        self.assertEqual(len(self.tester.results), 0)
        self.assertIsInstance(self.tester.report, TestReport)
    
    def test_get_headers_with_token(self):
        """Test header generation with valid token"""
        headers = self.tester._get_headers(use_token=True)
        
        self.assertIn("Authorization", headers)
        self.assertEqual(headers["Authorization"], f"Bearer {self.test_token}")
        self.assertEqual(headers["Content-Type"], "application/json")
        self.assertEqual(headers["Accept"], "application/json")
    
    def test_get_headers_without_token(self):
        """Test header generation without token"""
        headers = self.tester._get_headers(use_token=False)
        
        self.assertNotIn("Authorization", headers)
        self.assertEqual(headers["Content-Type"], "application/json")
    
    def test_get_headers_with_corrupted_token(self):
        """Test header generation with corrupted token"""
        headers = self.tester._get_headers(use_token=True, corrupt_token=True)
        
        self.assertIn("Authorization", headers)
        # Last character should be changed
        corrupted_token = headers["Authorization"].replace("Bearer ", "")
        self.assertNotEqual(corrupted_token, self.test_token)
        self.assertEqual(len(corrupted_token), len(self.test_token))
    
    @patch('test_admin_endpoints_production.requests.get')
    def test_make_request_success(self, mock_get):
        """Test successful GET request"""
        # Mock response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"total_users": 100}
        mock_get.return_value = mock_response
        
        result = self.tester._make_request("GET", "/api/admin/stats")
        
        self.assertTrue(result.success)
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.endpoint, "/api/admin/stats")
        self.assertEqual(result.method, "GET")
        self.assertIsNotNone(result.response_data)
        self.assertEqual(result.response_data["total_users"], 100)
        self.assertGreater(result.latency_ms, 0)
    
    @patch('test_admin_endpoints_production.requests.get')
    def test_make_request_failure(self, mock_get):
        """Test failed GET request"""
        # Mock response
        mock_response = Mock()
        mock_response.status_code = 500
        mock_response.json.return_value = {"detail": "Internal Server Error"}
        mock_get.return_value = mock_response
        
        result = self.tester._make_request("GET", "/api/admin/stats")
        
        self.assertFalse(result.success)
        self.assertEqual(result.status_code, 500)
        self.assertIsNotNone(result.error_message)
    
    @patch('test_admin_endpoints_production.requests.get')
    def test_make_request_timeout(self, mock_get):
        """Test request timeout handling"""
        import requests
        mock_get.side_effect = requests.exceptions.Timeout("Connection timeout")
        
        result = self.tester._make_request("GET", "/api/admin/stats")
        
        self.assertFalse(result.success)
        self.assertEqual(result.status_code, 0)
        self.assertEqual(result.error_message, "Request timeout")
        self.assertGreater(result.latency_ms, 0)
    
    @patch('test_admin_endpoints_production.requests.get')
    def test_authorization_positive(self, mock_get):
        """Test positive authorization test"""
        # Mock response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "total_users": 100,
            "total_checkins": 500,
            "real_patients_count": 80,
            "synthetic_patients_count": 20,
            "checkins_today": 10
        }
        mock_get.return_value = mock_response
        
        result = self.tester.test_authorization_positive()
        
        self.assertTrue(result.success)
        self.assertEqual(result.status_code, 200)
        self.assertEqual(len(self.tester.results), 1)
        self.assertEqual(len(self.tester.report.structural_issues), 0)
    
    @patch('test_admin_endpoints_production.requests.get')
    def test_authorization_positive_missing_fields(self, mock_get):
        """Test positive authorization with missing fields"""
        # Mock response with missing fields
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "total_users": 100
            # Missing other expected fields
        }
        mock_get.return_value = mock_response
        
        result = self.tester.test_authorization_positive()
        
        self.assertTrue(result.success)
        # Should have structural issues logged
        self.assertGreater(len(self.tester.report.structural_issues), 0)
    
    @patch('test_admin_endpoints_production.requests.get')
    def test_authorization_negative_success(self, mock_get):
        """Test negative authorization test (correctly rejected)"""
        # Mock response
        mock_response = Mock()
        mock_response.status_code = 401
        mock_response.json.return_value = {"detail": "Unauthorized"}
        mock_get.return_value = mock_response
        
        result = self.tester.test_authorization_negative()
        
        self.assertFalse(result.success)
        self.assertEqual(result.status_code, 401)
        self.assertEqual(self.tester.report.authorization_negative_result["status"], "PASS")
    
    @patch('test_admin_endpoints_production.requests.get')
    def test_authorization_negative_failure(self, mock_get):
        """Test negative authorization test (incorrectly accepted)"""
        # Mock response - SECURITY ISSUE
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"total_users": 100}
        mock_get.return_value = mock_response
        
        result = self.tester.test_authorization_negative()
        
        self.assertTrue(result.success)  # HTTP success
        self.assertEqual(result.status_code, 200)
        # But should be marked as security failure
        self.assertIn("FAIL", self.tester.report.authorization_negative_result["status"])
        self.assertEqual(self.tester.report.overall_status, "FAIL")
    
    @patch('test_admin_endpoints_production.requests.get')
    def test_list_users(self, mock_get):
        """Test list users endpoint"""
        # Mock response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "status": "success",
            "users": [
                {"id": "user-1", "email": "user1@example.com", "role": "patient", "created_at": "2024-01-01T00:00:00Z"},
                {"id": "user-2", "email": "user2@example.com", "role": "therapist", "created_at": "2024-01-02T00:00:00Z"}
            ],
            "total": 2
        }
        mock_get.return_value = mock_response
        
        result = self.tester.test_list_users(limit=50)
        
        self.assertTrue(result.success)
        self.assertEqual(result.status_code, 200)
        # Counts are now stored in response_data
        self.assertEqual(result.response_data['_user_count'], 2)
        self.assertEqual(result.response_data['_total_count'], 2)
    
    def test_cross_validation_consistent(self):
        """Test cross-validation with consistent data"""
        # Create mock results
        stats_result = EndpointTestResult(
            endpoint="/api/admin/stats",
            method="GET",
            status_code=200,
            latency_ms=100.0,
            success=True,
            response_data={"total_users": 100}
        )
        
        users_result = EndpointTestResult(
            endpoint="/api/admin/users",
            method="GET",
            status_code=200,
            latency_ms=100.0,
            success=True,
            response_data={"total": 100}
        )
        
        self.tester.test_cross_validation_stats_vs_users(stats_result, users_result)
        
        # Should have no inconsistencies
        self.assertEqual(len(self.tester.report.inconsistencies), 0)
    
    def test_cross_validation_inconsistent(self):
        """Test cross-validation with inconsistent data"""
        # Create mock results with inconsistent counts
        stats_result = EndpointTestResult(
            endpoint="/api/admin/stats",
            method="GET",
            status_code=200,
            latency_ms=100.0,
            success=True,
            response_data={"total_users": 100}
        )
        
        users_result = EndpointTestResult(
            endpoint="/api/admin/users",
            method="GET",
            status_code=200,
            latency_ms=100.0,
            success=True,
            response_data={"total": 95}  # Difference of 5, exceeds tolerance of 2
        )
        
        self.tester.test_cross_validation_stats_vs_users(stats_result, users_result)
        
        # Should have inconsistency logged
        self.assertGreater(len(self.tester.report.inconsistencies), 0)
    
    def test_calculate_latency_statistics(self):
        """Test latency statistics calculation"""
        # Add some mock results
        self.tester.results = [
            EndpointTestResult("/api/test1", "GET", 200, 100.0, True),
            EndpointTestResult("/api/test2", "GET", 200, 200.0, True),
            EndpointTestResult("/api/test3", "GET", 200, 300.0, True),
            EndpointTestResult("/api/test4", "GET", 500, 150.0, False),  # Failed - should be excluded
        ]
        
        self.tester.calculate_latency_statistics()
        
        # Check latency stats
        self.assertIn("meanMs", self.tester.report.latencies)
        self.assertIn("p95Ms", self.tester.report.latencies)
        self.assertIn("maxMs", self.tester.report.latencies)
        self.assertIn("minMs", self.tester.report.latencies)
        self.assertIn("stdDevMs", self.tester.report.latencies)
        
        # Mean of 100, 200, 300 should be 200
        self.assertEqual(self.tester.report.latencies["meanMs"], 200.0)
        self.assertEqual(self.tester.report.latencies["maxMs"], 300.0)
        self.assertEqual(self.tester.report.latencies["minMs"], 100.0)
        # Sample size should be 3 (failed request excluded)
        self.assertEqual(self.tester.report.latencies["sampleSize"], 3)
    
    def test_save_report(self):
        """Test saving report to JSON file"""
        # Create temp file
        temp_dir = tempfile.mkdtemp()
        temp_file = os.path.join(temp_dir, "test_report.json")
        
        try:
            # Add some data to report
            self.tester.report.overall_status = "OK"
            self.tester.report.end_time_utc = datetime.now(timezone.utc).isoformat()
            
            # Save report
            self.tester.save_report(temp_file)
            
            # Verify file exists
            self.assertTrue(os.path.exists(temp_file))
            
            # Load and verify JSON
            with open(temp_file, 'r') as f:
                data = json.load(f)
            
            self.assertEqual(data["overall_status"], "OK")
            self.assertIn("correlation_id", data)
            
        finally:
            # Cleanup
            if os.path.exists(temp_file):
                os.remove(temp_file)
            os.rmdir(temp_dir)
    
    def test_generate_roadmap(self):
        """Test generating ROADMAP markdown file"""
        # Create temp file
        temp_dir = tempfile.mkdtemp()
        temp_file = os.path.join(temp_dir, "test_roadmap.md")
        
        try:
            # Add some test data
            self.tester.results = [
                EndpointTestResult("/api/test1", "GET", 200, 100.0, True),
                EndpointTestResult("/api/test2", "GET", 401, 50.0, False)
            ]
            self.tester.report.overall_status = "WARN"
            self.tester.report.latencies = {
                "meanMs": 75.0,
                "p95Ms": 100.0,
                "maxMs": 100.0,
                "minMs": 50.0,
                "stdDevMs": 25.0,
                "sampleSize": 2
            }
            
            # Generate ROADMAP
            self.tester.generate_roadmap(temp_file)
            
            # Verify file exists
            self.assertTrue(os.path.exists(temp_file))
            
            # Verify content
            with open(temp_file, 'r') as f:
                content = f.read()
            
            self.assertIn("ROADMAP", content)
            self.assertIn(self.tester.correlation_id, content)
            self.assertIn("WARN", content)
            
        finally:
            # Cleanup
            if os.path.exists(temp_file):
                os.remove(temp_file)
            os.rmdir(temp_dir)


class TestMainFunction(unittest.TestCase):
    """Test the main function"""
    
    @patch.dict(os.environ, {}, clear=True)
    def test_main_without_token(self):
        """Test main function without BIPOLAR_ADMIN_TOKEN"""
        with self.assertRaises(SystemExit) as cm:
            from test_admin_endpoints_production import main
            main()
        
        self.assertEqual(cm.exception.code, 1)
    
    @patch.dict(os.environ, {"BIPOLAR_ADMIN_TOKEN": "test-token"})
    @patch('test_admin_endpoints_production.AdminEndpointTester')
    def test_main_with_token(self, mock_tester_class):
        """Test main function with valid token"""
        # Mock the tester instance
        mock_tester = Mock()
        mock_report = TestReport(
            correlation_id="test-123",
            start_time_utc="2024-01-15T10:00:00Z",
            end_time_utc="2024-01-15T10:05:00Z"
        )
        mock_report.overall_status = "OK"
        mock_tester.run_all_tests.return_value = mock_report
        mock_tester_class.return_value = mock_tester
        
        with self.assertRaises(SystemExit) as cm:
            from test_admin_endpoints_production import main
            main()
        
        # Should exit with 0 for OK status
        self.assertEqual(cm.exception.code, 0)


if __name__ == "__main__":
    unittest.main()
