# api/dependencies.py
import os
import logging
from typing import Optional, Set, AsyncGenerator
from fastapi import HTTPException, Header, Depends
from supabase import acreate_client, AsyncClient, Client
from supabase.lib.client_options import AsyncClientOptions

logger = logging.getLogger("bipolar-api.dependencies")

# Cache admin emails as a set for O(1) lookup
_admin_emails_cache: Optional[Set[str]] = None


def get_admin_emails() -> Set[str]:
    """
    Get the set of admin emails from environment variable.
    Caches the result for performance.
    
    Returns:
        Set of admin email addresses
    """
    global _admin_emails_cache
    
    if _admin_emails_cache is None:
        admin_emails_str = os.getenv("ADMIN_EMAILS", "")
        _admin_emails_cache = {email.strip() for email in admin_emails_str.split(",") if email.strip()}
        logger.info(f"Initialized admin emails cache with {len(_admin_emails_cache)} emails")
    
    return _admin_emails_cache

async def get_supabase_client() -> AsyncClient:
    """
    Dependency function assíncrona para criar e retornar um cliente Supabase.
    Isso garante que as variáveis de ambiente sejam lidas apenas quando
    a função é chamada, não na inicialização do módulo.
    
    The client is created using SUPABASE_SERVICE_KEY which provides admin-level
    privileges, bypassing Row Level Security (RLS) policies. This is necessary
    for admin operations like creating users and managing data across all users.
    """
    logger.debug("Creating Supabase client...")
    
    url: str = os.environ.get("SUPABASE_URL")
    key: str = os.environ.get("SUPABASE_SERVICE_KEY")

    if not url or not key:
        error_msg = "Variáveis de ambiente do Supabase não configuradas no servidor."
        logger.error(error_msg)
        logger.error(f"SUPABASE_URL configured: {bool(url)}")
        logger.error(f"SUPABASE_SERVICE_KEY configured: {bool(key)}")
        raise HTTPException(status_code=500, detail=error_msg)

    logger.debug(f"Supabase URL configured: {url[:30]}...")
    logger.debug(f"Service key length: {len(key)} characters")
    
    # Use AsyncClientOptions object instead of dict
    supabase_options = AsyncClientOptions(persist_session=False)
    client = await acreate_client(url, key, options=supabase_options)
    
    logger.debug(f"Supabase client created successfully: {type(client).__name__}")
    
    return client


async def get_supabase_service() -> AsyncGenerator[AsyncClient, None]:
    """
    Dependency function to create and yield a Supabase service client.
    
    This function returns an AsyncGenerator that yields a Supabase client with
    admin-level privileges using SUPABASE_SERVICE_KEY. This bypasses Row Level 
    Security (RLS) policies and is necessary for admin operations like creating 
    users and managing synthetic data across all users.
    
    The service client uses custom headers to ensure the API key is properly set,
    which is essential for bypassing RLS in all database operations.
    
    Yields:
        AsyncClient: Supabase client with service role privileges
        
    Raises:
        HTTPException: If environment variables are not configured
        
    Usage:
        @router.post("/endpoint")
        async def endpoint(supabase: AsyncClient = Depends(get_supabase_service)):
            # Use supabase client with admin privileges
            pass
    """
    logger.debug("Creating Supabase service client (AsyncGenerator)...")
    
    url: str = os.environ.get("SUPABASE_URL")
    key: str = os.environ.get("SUPABASE_SERVICE_KEY")

    if not url or not key:
        error_msg = "Variáveis de ambiente do Supabase não configuradas no servidor."
        logger.error(error_msg)
        logger.error(f"SUPABASE_URL configured: {bool(url)}")
        logger.error(f"SUPABASE_SERVICE_KEY configured: {bool(key)}")
        raise HTTPException(status_code=500, detail=error_msg)

    logger.debug(f"Supabase service URL configured: {url[:30]}...")
    logger.debug(f"Service key length: {len(key)} characters")
    
    # Validate key format (JWT tokens should start with 'eyJ')
    if not key.startswith('eyJ'):
        logger.warning("SUPABASE_SERVICE_KEY may not be a valid JWT token - should start with 'eyJ'")
    
    client = None
    try:
        # Create client with service role key and custom options
        # The global headers ensure the API key is set for all requests
        supabase_options = AsyncClientOptions(
            persist_session=False,
            headers={
                "apikey": key,
                "Authorization": f"Bearer {key}"
            }
        )
        client = await acreate_client(url, key, options=supabase_options)
        
        logger.debug(f"Supabase service client created successfully: {type(client).__name__}")
        
        yield client
        
    finally:
        # Cleanup: close any resources if needed
        if client:
            logger.debug("Cleaning up Supabase service client")
            # AsyncClient doesn't require explicit cleanup in current version
            # but this ensures we handle it if the library changes


async def verify_admin_authorization(
    authorization: Optional[str] = Header(None),
    supabase: AsyncClient = Depends(get_supabase_client)
) -> bool:
    """
    Verify that the request has admin authorization via JWT token.
    
    Uses Role-Based Access Control (RBAC) to check if the user has admin privileges.
    Admin status is determined by:
    1. User's email being in the ADMIN_EMAILS environment variable, OR
    2. User's user_metadata containing role='admin'
    
    Args:
        authorization: Authorization header with Bearer token
        supabase: Supabase client (injected dependency)
    
    Returns:
        True if authorized as admin
    
    Raises:
        HTTPException: 401 if unauthorized, 403 if not admin
    """
    if not authorization:
        logger.warning("No authorization header provided for admin endpoint")
        raise HTTPException(
            status_code=401,
            detail="Admin authorization required. Provide a valid JWT token."
        )
    
    # Extract token from Bearer header
    if not authorization.startswith("Bearer "):
        logger.error("Invalid authorization header format")
        raise HTTPException(
            status_code=401,
            detail="Invalid authorization header. Must be 'Bearer <token>'"
        )
    
    token = authorization[7:]  # Remove "Bearer " prefix
    
    try:
        # Validate the JWT token and get user info
        user_response = await supabase.auth.get_user(token)
        
        if not user_response or not user_response.user:
            logger.error("Invalid JWT token - user not found")
            raise HTTPException(
                status_code=401,
                detail="Invalid authorization token"
            )
        
        user = user_response.user
        user_email = user.email
        user_metadata = user.user_metadata or {}
        
        logger.info(f"JWT token validated for user: {user_email}")
        
        # Check if user is admin
        # Method 1: Check against ADMIN_EMAILS environment variable (cached as set for O(1) lookup)
        admin_emails = get_admin_emails()
        
        if user_email and user_email in admin_emails:
            logger.info(f"Admin access granted - email in ADMIN_EMAILS: {user_email}")
            return True
        
        # Method 2: Check user_metadata for role='admin'
        if user_metadata.get("role") == "admin":
            logger.info(f"Admin access granted - user_metadata.role='admin' for {user_email}")
            return True
        
        # User is authenticated but not an admin
        logger.warning(f"Access denied - user {user_email} is not an admin")
        raise HTTPException(
            status_code=403,
            detail="Forbidden. Admin privileges required."
        )
        
    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    except Exception as e:
        logger.exception(f"Error validating admin authorization: {e}")
        raise HTTPException(
            status_code=401,
            detail="Error validating authorization token"
        )
