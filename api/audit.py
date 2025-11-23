"""
Audit logging utilities for admin operations.
"""
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from supabase import Client

logger = logging.getLogger("bipolar-api.audit")


async def log_audit_action(
    supabase: Client,
    action: str,
    details: Optional[Dict[str, Any]] = None,
    user_id: Optional[str] = None,
    performed_by: Optional[str] = None,
) -> bool:
    """
    Log an admin action to the audit_log table.
    
    Args:
        supabase: Supabase client (service role)
        action: Action type (e.g., 'user_create', 'synthetic_generate', 'cleanup')
        details: Additional details as JSON
        user_id: User ID affected by the action
        performed_by: Admin user ID who performed the action
        
    Returns:
        True if logged successfully, False otherwise
    """
    try:
        audit_entry = {
            "action": action,
            "details": details or {},
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        
        # Add optional fields
        if user_id:
            audit_entry["user_id"] = user_id
        if performed_by:
            audit_entry["performed_by"] = performed_by
        
        supabase.table("audit_log").insert(audit_entry).execute()
        logger.debug(f"[Audit] Logged action: {action}")
        return True
        
    except Exception as e:
        logger.warning(f"[Audit] Failed to log action {action}: {e}")
        return False


__all__ = ["log_audit_action"]
