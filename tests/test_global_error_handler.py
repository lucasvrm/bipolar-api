"""
Tests for global error handler in main.py.
"""
import pytest
import sys
import os
from unittest.mock import patch, MagicMock, AsyncMock

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from fastapi import Request, HTTPException
from fastapi.responses import JSONResponse
from main import global_exception_handler


@pytest.mark.asyncio
async def test_global_exception_handler_returns_safe_message():
    """Test that the global exception handler returns a safe message"""
    # Create a mock request
    request = MagicMock(spec=Request)
    request.method = "GET"
    request.url = "http://test.com/test"
    
    # Create a test exception
    exc = ValueError("This is a sensitive internal error message")
    
    # Call the exception handler
    response = await global_exception_handler(request, exc)
    
    # Should return a JSONResponse
    assert isinstance(response, JSONResponse)
    
    # Should return 500 status code
    assert response.status_code == 500
    
    # Get the response body
    import json
    body = json.loads(response.body.decode())
    
    # Should only contain safe message
    assert body["detail"] == "Internal Server Error"
    
    # Should NOT contain the original error message or type
    assert "ValueError" not in str(body)
    assert "sensitive internal error" not in str(body).lower()


@pytest.mark.asyncio
async def test_global_exception_handler_logs_full_traceback():
    """Test that the global exception handler logs the full traceback internally"""
    # Create a mock request
    request = MagicMock(spec=Request)
    request.method = "POST"
    request.url = "http://test.com/api/endpoint"
    
    # Create a test exception
    exc = RuntimeError("Internal server issue")
    
    # Mock the logger to verify it's called
    with patch("main.logger") as mock_logger:
        response = await global_exception_handler(request, exc)
        
        # Verify logger.exception was called
        mock_logger.exception.assert_called_once()
        
        # Verify it was called with exc_info=True to include traceback
        call_args = mock_logger.exception.call_args
        assert call_args[1].get("exc_info") == True
        
        # Verify the message includes request details
        assert "POST" in str(call_args[0])
        assert "http://test.com/api/endpoint" in str(call_args[0])


@pytest.mark.asyncio  
async def test_global_exception_handler_different_exception_types():
    """Test that different exception types all get the same safe message"""
    request = MagicMock(spec=Request)
    request.method = "GET"
    request.url = "http://test.com/test"
    
    exceptions = [
        ValueError("test"),
        RuntimeError("test"),
        KeyError("test"),
        AttributeError("test"),
        Exception("test")
    ]
    
    import json
    for exc in exceptions:
        response = await global_exception_handler(request, exc)
        body = json.loads(response.body.decode())
        
        # All should return the same safe message
        assert body["detail"] == "Internal Server Error"
        assert response.status_code == 500


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
