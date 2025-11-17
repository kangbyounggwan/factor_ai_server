"""
JWT Authentication Helper for Supabase

Extracts user_id from Supabase JWT tokens
"""
import jwt
import os
from typing import Optional
from fastapi import Header, HTTPException
import logging

logger = logging.getLogger("uvicorn.error")

# Supabase JWT Secret (optional - for verification)
JWT_SECRET = os.getenv("SUPABASE_JWT_SECRET")


def extract_user_id_from_token(authorization: Optional[str] = None) -> Optional[str]:
    """
    Extract user_id from Supabase JWT token

    Args:
        authorization: Authorization header value (Bearer <token>)

    Returns:
        str or None: User ID from token, or None if not authenticated
    """
    if not authorization:
        logger.warning("[Auth] No authorization header provided")
        return None

    try:
        # Extract token from "Bearer <token>"
        if not authorization.startswith("Bearer "):
            logger.warning("[Auth] Invalid authorization format (missing 'Bearer')")
            return None

        token = authorization.split(" ")[1]

        # Decode JWT token without verification (for now)
        # In production, you should verify with JWT_SECRET
        if JWT_SECRET:
            payload = jwt.decode(
                token,
                JWT_SECRET,
                algorithms=["HS256"],
                options={"verify_signature": True}
            )
            logger.info(f"[Auth] Token verified with secret")
        else:
            # Decode without verification (development only)
            payload = jwt.decode(
                token,
                options={"verify_signature": False}
            )
            logger.warning("[Auth] Token decoded without verification (JWT_SECRET not set)")

        # Supabase JWT has 'sub' field with user ID
        user_id = payload.get("sub")

        if user_id:
            logger.info(f"[Auth] Extracted user_id: {user_id[:8]}...")
            return user_id
        else:
            logger.warning("[Auth] No 'sub' field in JWT payload")
            return None

    except jwt.ExpiredSignatureError:
        logger.error("[Auth] Token has expired")
        return None
    except jwt.InvalidTokenError as e:
        logger.error(f"[Auth] Invalid token: {e}")
        return None
    except Exception as e:
        logger.error(f"[Auth] Unexpected error extracting user_id: {e}")
        return None


async def get_current_user_id(authorization: Optional[str] = Header(None)) -> Optional[str]:
    """
    FastAPI dependency to extract user_id from Authorization header

    Usage:
        @app.post("/endpoint")
        async def endpoint(user_id: Optional[str] = Depends(get_current_user_id)):
            ...

    Args:
        authorization: Authorization header (automatically injected by FastAPI)

    Returns:
        str or None: User ID
    """
    return extract_user_id_from_token(authorization)


async def require_auth(authorization: Optional[str] = Header(None)) -> str:
    """
    FastAPI dependency that requires authentication
    Raises 401 if not authenticated

    Usage:
        @app.post("/protected-endpoint")
        async def endpoint(user_id: str = Depends(require_auth)):
            # user_id is guaranteed to be present
            ...

    Args:
        authorization: Authorization header

    Returns:
        str: User ID (guaranteed)

    Raises:
        HTTPException: 401 if not authenticated
    """
    user_id = extract_user_id_from_token(authorization)

    if not user_id:
        raise HTTPException(
            status_code=401,
            detail="Authentication required"
        )

    return user_id


if __name__ == "__main__":
    # Test JWT extraction
    print("Testing JWT extraction...")

    # Example Supabase JWT (anon key - this won't have user_id)
    test_token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImVjbXJrandzamt0aHVyd2xqaHZwIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NTE1MjUxODMsImV4cCI6MjA2NzEwMTE4M30.IB1Bx5h4YjhegQ6jACZ8FH7kzF3rwEwz-TztJQcQyWc"

    user_id = extract_user_id_from_token(f"Bearer {test_token}")
    print(f"Extracted user_id: {user_id}")

    # Test with invalid token
    user_id = extract_user_id_from_token("Bearer invalid_token")
    print(f"Invalid token result: {user_id}")

    # Test with no auth
    user_id = extract_user_id_from_token(None)
    print(f"No auth result: {user_id}")
