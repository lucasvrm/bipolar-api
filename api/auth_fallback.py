"""
HTTP Fallback Authentication Module

This module provides a TEMPORARY fallback mechanism for Supabase authentication
when the async Python client encounters intermittent failures.

TEMPORARY: This is a workaround for known issues with the async Supabase client.
It should be removed once the client library demonstrates stable behavior.

Author: Copilot Agent
Date: 2025-11-22
"""

import os
import json
import logging
import urllib.request
import urllib.error
from typing import Dict, Any

logger = logging.getLogger("bipolar-api.auth_fallback")


def supabase_get_user_http(token: str) -> Dict[str, Any]:
    """
    Verify user token via direct HTTP call to Supabase auth endpoint.
    
    This is a TEMPORARY fallback for when the Supabase Python client fails.
    It makes a direct HTTP request to the /auth/v1/user endpoint.
    
    Args:
        token: JWT token to verify
        
    Returns:
        Dict containing user data from Supabase auth service
        
    Raises:
        RuntimeError: If configuration is incomplete or HTTP request fails
        
    Example response:
        {
            "id": "uuid-here",
            "email": "user@example.com",
            "aud": "authenticated",
            ...
        }
    """
    # Validate environment configuration
    url = os.getenv("SUPABASE_URL")
    anon_key = os.getenv("SUPABASE_ANON_KEY")
    
    if not url or not anon_key:
        logger.error("Fallback HTTP auth: Missing SUPABASE_URL or SUPABASE_ANON_KEY")
        raise RuntimeError("Ambiente incompleto para fallback HTTP")
    
    # Build auth endpoint URL
    endpoint = url.rstrip("/") + "/auth/v1/user"
    
    # Prepare HTTP request with required headers
    # IMPORTANT: Use ANON key in apikey header, not SERVICE key
    req = urllib.request.Request(
        endpoint,
        headers={
            "apikey": anon_key,
            "Authorization": f"Bearer {token}",
        }
    )
    
    logger.debug(
        "Fallback HTTP auth.get_user: endpoint=%s, token_length=%d",
        endpoint,
        len(token)
    )
    
    try:
        # Make HTTP request with 10 second timeout
        with urllib.request.urlopen(req, timeout=10) as resp:
            response_data = resp.read().decode()
            user_data = json.loads(response_data)
            
            logger.info(
                "Fallback HTTP auth successful: user_id=%s",
                user_data.get("id", "unknown")
            )
            
            return user_data
            
    except urllib.error.HTTPError as e:
        # Read error response body for debugging
        try:
            error_body = e.read().decode()
        except Exception:
            error_body = "(unable to read error body)"
        
        logger.warning(
            "Fallback HTTP auth failed: status=%d, body=%s",
            e.code,
            error_body
        )
        
        # Re-raise with informative message
        raise RuntimeError(f"Auth HTTP error {e.code}: {error_body}")
        
    except urllib.error.URLError as e:
        # Network/DNS error
        logger.error("Fallback HTTP auth network error: %s", e.reason)
        raise RuntimeError(f"Auth network error: {e.reason}")
        
    except Exception as e:
        # Unexpected error
        logger.exception("Fallback HTTP auth unexpected error")
        raise RuntimeError(f"Auth unexpected error: {str(e)}")


def should_use_fallback(error: Exception) -> bool:
    """
    Determine if an error from the Supabase client warrants using HTTP fallback.
    
    We use fallback for known library issues, not for legitimate auth failures.
    
    Args:
        error: Exception raised by Supabase client
        
    Returns:
        True if fallback should be attempted, False otherwise
    """
    error_str = str(error).lower()
    
    # Known patterns that indicate library/configuration issues
    fallback_patterns = [
        "invalid api key",
        "bad_jwt",  # Malformed by library, not user
        "connection reset",
        "connection refused",
        "timeout",
    ]
    
    for pattern in fallback_patterns:
        if pattern in error_str:
            logger.debug(
                "Error matches fallback pattern '%s': %s",
                pattern,
                error_str[:100]  # Log only first 100 chars
            )
            return True
    
    return False
