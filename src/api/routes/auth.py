"""
Auth routes (Supabase JWT-based).
"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_current_user, get_db_session
from src.api.services.users import get_or_create_user_profile, serialize_user_profile

router = APIRouter()


@router.get("/me")
async def me(
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    db_user, profile = await get_or_create_user_profile(
        db,
        user["user_id"],
        email=user.get("email"),
    )
    return serialize_user_profile(db_user, profile)
