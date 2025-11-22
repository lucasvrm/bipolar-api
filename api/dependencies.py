# api/dependencies.py
import os
import logging
from typing import Optional, Set, AsyncGenerator
from fastapi import HTTPException, Header, Depends
from supabase import acreate_client, AsyncClient, Client
from supabase.lib.client_options import AsyncClientOptions

logger = logging.getLogger("bipolar-api.dependencies")

# Re-export acreate_client to support test mocking
# Tests need to patch api.dependencies.acreate_client for dependency injection
__all__ = ['acreate_client', 'AsyncClient', 'Client', 'get_supabase_client', 
           'get_supabase_anon_auth_client', 'get_supabase_service_role_client',
           'get_supabase_service', 'verify_admin_authorization', 'get_admin_emails']

# Cache admin emails as a set for O(1) lookup
_admin_emails_cache: Optional[Set[str]] = None

# Service key validation constants
# Service role keys are JWT tokens ~200+ characters
# Anon keys are typically ~150 characters
MIN_SERVICE_KEY_LENGTH = 180  # Conservative threshold to detect wrong key type
MIN_ANON_KEY_LENGTH = 100  # Anon keys are typically ~150 characters


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
    DEPRECATED: Use get_supabase_service_role_client() for admin operations.
    
    Dependency function assíncrona para criar e retornar um cliente Supabase.
    Isso garante que as variáveis de ambiente sejam lidas apenas quando
    a função é chamada, não na inicialização do módulo.
    
    NOTE: This function does NOT set explicit Authorization headers and should
    NOT be used for admin operations that bypass RLS. Use get_supabase_service_role_client()
    instead for admin-level operations.
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


async def get_supabase_anon_auth_client() -> AsyncClient:
    """
    Create Supabase client with ANON KEY for user JWT validation.
    
    This client is EXCLUSIVELY for validating user JWT tokens via auth.get_user(token).
    It uses the ANON (public) key, which is the correct key type for the /auth/v1/user endpoint.
    
    IMPORTANT: This client should ONLY be used for:
    - User authentication verification (auth.get_user(token))
    - Validating JWT tokens from users
    
    DO NOT use this client for:
    - Admin operations that bypass RLS (use get_supabase_service_role_client instead)
    - Database operations requiring elevated privileges
    
    The Supabase auth endpoint /auth/v1/user expects:
    - apikey header: ANON KEY (public key)
    - Authorization header: Bearer <user_jwt_token> (passed to get_user)
    
    Returns:
        AsyncClient: Supabase client with ANON key for auth validation
        
    Raises:
        HTTPException: If SUPABASE_URL or SUPABASE_ANON_KEY are not configured
        
    Example:
        @router.get("/endpoint")
        async def endpoint(supabase_anon: AsyncClient = Depends(get_supabase_anon_auth_client)):
            # Validate user JWT
            user_response = await supabase_anon.auth.get_user(jwt_token)
    """
    logger.debug("Creating Supabase ANON client for auth validation...")
    
    url: str = os.environ.get("SUPABASE_URL")
    anon_key: str = os.environ.get("SUPABASE_ANON_KEY")

    # Log key length for debugging (only length, not the key itself)
    anon_key_length = len(anon_key) if anon_key else 0
    logger.info(f"ANON Key validation - Length: {anon_key_length} chars")
    
    if not url or not anon_key:
        error_msg = "Variáveis de ambiente SUPABASE_URL ou SUPABASE_ANON_KEY não configuradas no servidor."
        logger.error(error_msg)
        logger.error(f"SUPABASE_URL configured: {bool(url)}")
        logger.error(f"SUPABASE_ANON_KEY configured: {bool(anon_key)}")
        raise HTTPException(status_code=500, detail=error_msg)

    # Validate ANON key length (less strict than SERVICE key)
    if anon_key_length < MIN_ANON_KEY_LENGTH:
        error_msg = (
            f"SUPABASE_ANON_KEY inválida! "
            f"Comprimento: {anon_key_length} caracteres (esperado 100+). "
        )
        logger.error(error_msg)
        raise HTTPException(status_code=500, detail="Configuração SUPABASE_ANON_KEY inválida")
    
    logger.debug(f"Supabase URL configured: {url[:30]}...")
    logger.info(f"ANON client will be used exclusively for user JWT validation via auth.get_user()")
    
    # Create client with ANON key
    # The apikey header will be set to the ANON key automatically
    # When calling auth.get_user(token), the user's JWT will be passed as parameter
    supabase_options = AsyncClientOptions(
        persist_session=False,
        headers={
            "apikey": anon_key
        }
    )
    
    client = await acreate_client(url, anon_key, options=supabase_options)
    
    logger.info(f"Supabase ANON client created successfully for auth validation: {type(client).__name__}")
    logger.info("ANON client will call /auth/v1/user with apikey=ANON_KEY")
    
    return client


async def get_supabase_service_role_client() -> AsyncClient:
    """
    NEW DEDICATED FUNCTION: Create Supabase client with explicit service role authentication.
    
    This function creates an AsyncClient with EXPLICIT headers to ensure service role
    privileges that bypass Row Level Security (RLS) policies. This is the ONLY correct
    way to authenticate admin operations.
    
    IMPORTANT: This client should ONLY be used for:
    - Admin endpoint operations that bypass RLS
    - Data generation/cleanup operations
    - Database operations requiring elevated privileges
    
    DO NOT use this client for:
    - User JWT validation (use get_supabase_anon_auth_client instead)
    - The /auth/v1/user endpoint expects ANON KEY, not SERVICE KEY
    
    Key differences from get_supabase_client():
    1. Sets explicit Authorization header with Bearer token
    2. Sets explicit apikey header  
    3. Validates service key format and length
    4. Logs diagnostic information (first 5 chars, length)
    
    Returns:
        AsyncClient: Supabase client with service role privileges
        
    Raises:
        HTTPException: If environment variables are not configured
        RuntimeError: If service key validation fails (wrong key type, invalid JWT)
        
    Usage:
        Use this for ALL admin operations that need to bypass RLS:
        - Admin endpoint operations (NOT user auth validation)
        - Data generation/cleanup
        
    Example:
        @router.get("/admin/endpoint")
        async def endpoint(supabase: AsyncClient = Depends(get_supabase_service_role_client)):
            # Use supabase client with admin privileges for data operations
            pass
    """
    logger.debug("Creating Supabase SERVICE ROLE client with explicit headers...")
    
    url: str = os.environ.get("SUPABASE_URL")
    key: str = os.environ.get("SUPABASE_SERVICE_KEY")

    # Log key length for debugging (only length logged, not the key itself for security)
    key_length = len(key) if key else 0
    logger.info(f"Service Role Key validation - Length: {key_length} chars")
    
    # Log first 5 characters for diagnostic purposes (only in debug mode)
    # This helps confirm the correct key type is being used (service keys start with 'eyJ')
    # In production, rely on length validation instead
    if key and logger.isEnabledFor(logging.DEBUG):
        logger.debug(f"Service Role Key - First 5 chars: '{key[:5]}...'")
    
    if not url or not key:
        error_msg = "Variáveis de ambiente do Supabase não configuradas no servidor."
        logger.error(error_msg)
        logger.error(f"SUPABASE_URL configured: {bool(url)}")
        logger.error(f"SUPABASE_SERVICE_KEY configured: {bool(key)}")
        raise HTTPException(status_code=500, detail=error_msg)

    # Validate service key length using module constant
    if key_length < MIN_SERVICE_KEY_LENGTH:
        error_msg = (
            f"CRITICAL: SUPABASE_SERVICE_KEY appears to be invalid! "
            f"Length: {key_length} chars (expected 200+). "
            f"This is likely an ANON key instead of SERVICE_ROLE key. "
            f"Check your environment variables!"
        )
        logger.critical(error_msg)
        raise RuntimeError(error_msg)
    
    logger.debug(f"Supabase service URL configured: {url[:30]}...")
    
    # Validate key format (JWT tokens should start with 'eyJ')
    if not key.startswith('eyJ'):
        error_msg = "SUPABASE_SERVICE_KEY is not a valid JWT token - should start with 'eyJ'"
        logger.critical(error_msg)
        raise RuntimeError(error_msg)
    
    # CRITICAL: Set explicit headers to force service role authentication
    # This is the HARD FIX that ensures admin privileges
    # Supabase requires BOTH headers set to the same service key:
    # - 'apikey': Used for API authentication
    # - 'Authorization': Used for bypassing RLS policies
    headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}"
    }
    
    logger.info("Service Role Client - Explicit authorization headers configured")
    
    # Create client with service role key and custom options with EXPLICIT headers
    supabase_options = AsyncClientOptions(
        persist_session=False,
        headers=headers
    )
    
    client = await acreate_client(url, key, options=supabase_options)
    
    logger.info(f"Supabase SERVICE ROLE client created successfully: {type(client).__name__}")
    logger.info("Service role client GUARANTEED to bypass RLS with explicit Authorization headers")
    
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
        RuntimeError: If service key validation fails
        
    Usage:
        @router.post("/endpoint")
        async def endpoint(supabase: AsyncClient = Depends(get_supabase_service)):
            # Use supabase client with admin privileges
            pass
    """
    logger.debug("Creating Supabase service client (AsyncGenerator)...")
    
    url: str = os.environ.get("SUPABASE_URL")
    key: str = os.environ.get("SUPABASE_SERVICE_KEY")

    # Log key length for debugging (only length logged, not the key itself for security)
    key_length = len(key) if key else 0
    logger.info(f"Service Key validation - Length: {key_length} chars")
    
    # Log first 5 characters for diagnostic purposes (only in debug mode)
    # This helps confirm the correct key type is being used (service keys start with 'eyJ')
    if key and logger.isEnabledFor(logging.DEBUG):
        logger.debug(f"Service Key - First 5 chars: '{key[:5]}...'")
    
    if not url or not key:
        error_msg = "Variáveis de ambiente do Supabase não configuradas no servidor."
        logger.error(error_msg)
        logger.error(f"SUPABASE_URL configured: {bool(url)}")
        logger.error(f"SUPABASE_SERVICE_KEY configured: {bool(key)}")
        raise HTTPException(status_code=500, detail=error_msg)

    # Validate service key length using module constant
    if key_length < MIN_SERVICE_KEY_LENGTH:
        error_msg = (
            f"CRITICAL: SUPABASE_SERVICE_KEY appears to be invalid! "
            f"Length: {key_length} chars (expected 200+). "
            f"This is likely an ANON key instead of SERVICE_ROLE key. "
            f"Check your environment variables!"
        )
        logger.critical(error_msg)
        raise RuntimeError(error_msg)
    
    logger.debug(f"Supabase service URL configured: {url[:30]}...")
    
    # Validate key format (JWT tokens should start with 'eyJ')
    if not key.startswith('eyJ'):
        error_msg = "SUPABASE_SERVICE_KEY is not a valid JWT token - should start with 'eyJ'"
        logger.critical(error_msg)
        raise RuntimeError(error_msg)
    
    client = None
    try:
        # Create client with service role key and custom options
        # Supabase requires BOTH headers set to the same service key:
        # - 'apikey': Used for API authentication
        # - 'Authorization': Used for bypassing RLS policies
        supabase_options = AsyncClientOptions(
            persist_session=False,
            headers={
                "apikey": key,
                "Authorization": f"Bearer {key}"
            }
        )
        client = await acreate_client(url, key, options=supabase_options)
        
        logger.debug(f"Supabase service client created successfully: {type(client).__name__}")
        logger.info("Service client configured with explicit authorization headers")
        
        yield client
        
    finally:
        # Cleanup: close any resources if needed
        if client:
            logger.debug("Cleaning up Supabase service client")
            # AsyncClient doesn't require explicit cleanup in current version
            # but this ensures we handle it if the library changes


async def verify_admin_authorization(
    authorization: Optional[str] = Header(None),
    supabase_anon: AsyncClient = Depends(get_supabase_anon_auth_client)
) -> bool:
    """
    Verify that the request has admin authorization via JWT token.
    
    CRITICAL FIX: Now uses get_supabase_anon_auth_client() for user JWT validation.
    The /auth/v1/user endpoint requires ANON KEY (apikey header) + user JWT (Bearer token),
    NOT the SERVICE ROLE KEY.
    
    Uses Role-Based Access Control (RBAC) to check if the user has admin privileges.
    Admin status is determined by:
    1. User's email being in the ADMIN_EMAILS environment variable, OR
    2. User's user_metadata containing role='admin'
    
    Args:
        authorization: Authorization header with Bearer token
        supabase_anon: Supabase ANON client for auth validation (injected dependency)
    
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
        # This call goes to /auth/v1/user with:
        # - apikey header: ANON KEY (from supabase_anon client)
        # - Authorization: Bearer <user_jwt_token> (from get_user parameter)
        user_response = await supabase_anon.auth.get_user(token)
        
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
