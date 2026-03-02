"""
FastAPI dependencies (auth, config, request context).
"""

import logging
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

logger = logging.getLogger(__name__)


def _get_jwks_client(jwks_url: str) -> PyJWKClient:
    return PyJWKClient(jwks_url)


def _verify_supabase_jwt(token: str) -> Dict[str, Any]:
    settings = get_settings()
    issuer = settings.supabase_jwt_issuer
    if issuer is None and settings.supabase_url:
        issuer = f"{settings.supabase_url}/auth/v1"

    audience = settings.supabase_jwt_audience or None
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
            opts = {"require": ["exp", "iat", "sub"]}
            if audience is None:
                opts["verify_aud"] = False
            return jwt.decode(
                token,
                signing_key,
                algorithms=[alg],
                audience=audience,
                issuer=issuer,
                options=opts,
            )
        except Exception as exc:
            logger.warning("JWT verification failed (RS/ES): %s", exc)
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
        opts = {"require": ["exp", "iat", "sub"]}
        if audience is None:
            opts["verify_aud"] = False
        return jwt.decode(
            token,
            settings.supabase_jwt_secret,
            algorithms=[alg],
            audience=audience,
            issuer=issuer,
            options=opts,
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
        logger.debug("Auth failed: missing Authorization header")
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

    email = _extract_email_from_claims(claims)
    return {"user_id": user_id, "email": email, "claims": claims}


def _extract_email_from_claims(claims: Dict[str, Any]) -> Optional[str]:
    """Extract email from Supabase JWT claims (OAuth users may have it in user_metadata)."""
    email = claims.get("email")
    if email:
        return email
    for key in ("user_metadata", "raw_user_meta_data"):
        meta = claims.get(key)
        if isinstance(meta, dict) and meta.get("email"):
            return meta["email"]
    return None


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
