"""
FastAPI dependencies (auth, config, request context).
"""

from typing import Optional, Dict, Any
import uuid

import jwt
from jwt import PyJWKClient
from fastapi import Depends, HTTPException, Header, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.config.settings import get_settings
from src.database.models import User, UserRole
from src.database.connection import get_db_session

from src.database.connection import get_db_session


def _get_jwks_client(jwks_url: str) -> PyJWKClient:
    return PyJWKClient(jwks_url)


def _verify_supabase_jwt(token: str) -> Dict[str, Any]:
    settings = get_settings()
    issuer = settings.supabase_jwt_issuer
    if issuer is None and settings.supabase_url:
        issuer = f"{settings.supabase_url}/auth/v1"

    audience = settings.supabase_jwt_audience
    try:
        header = jwt.get_unverified_header(token)
    except jwt.PyJWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid token header: {exc}",
        ) from exc

    alg = header.get("alg")
    if not alg:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token missing alg header",
        )

    if alg.startswith("RS") or alg.startswith("ES"):
        if not settings.supabase_jwks_url:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Supabase JWKS URL is not configured",
            )
        try:
            jwks_client = _get_jwks_client(settings.supabase_jwks_url)
            signing_key = jwks_client.get_signing_key_from_jwt(token).key
            return jwt.decode(
                token,
                signing_key,
                algorithms=[alg],
                audience=audience,
                issuer=issuer,
                options={"require": ["exp", "iat", "sub"]},
            )
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Invalid token: {exc}",
            ) from exc

    if alg.startswith("HS"):
        if not settings.supabase_jwt_secret:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Supabase JWT secret is not configured",
            )
        return jwt.decode(
            token,
            settings.supabase_jwt_secret,
            algorithms=[alg],
            audience=audience,
            issuer=issuer,
            options={"require": ["exp", "iat", "sub"]},
        )

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=f"Unsupported token algorithm: {alg}",
    )


def get_current_user(authorization: Optional[str] = Header(default=None)) -> dict:
    """
    Placeholder for Supabase JWT verification.
    """
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization header",
        )

    if not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Authorization header",
        )

    token = authorization.split(" ", 1)[1].strip()
    try:
        claims = _verify_supabase_jwt(token)
    except jwt.PyJWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid token: {exc}",
        ) from exc

    subject = claims.get("sub")
    if not subject:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token missing subject",
        )

    try:
        user_id = uuid.UUID(subject)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token subject is not a valid UUID",
        ) from exc

    email = claims.get("email")
    return {"user_id": user_id, "email": email, "claims": claims}


async def require_admin(
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    result = await db.execute(select(User).where(User.id == user["user_id"]))
    db_user = result.scalar_one_or_none()
    if db_user is None or db_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    user["role"] = db_user.role.value
    return user


__all__ = [
    "get_current_user",
    "require_admin",
    "get_db_session",
]
