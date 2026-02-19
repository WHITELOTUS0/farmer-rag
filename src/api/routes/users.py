"""
User profile routes.
"""

from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_current_user, get_db_session
from src.api.services.users import get_or_create_user_profile, serialize_user_profile
from src.database.models import UserProfile

router = APIRouter()


class UserProfileUpdate(BaseModel):
    name: Optional[str] = None
    phone: Optional[str] = None
    region: Optional[str] = None
    language: Optional[str] = None
    location_lat: Optional[float] = None
    location_lon: Optional[float] = None


@router.get("/me")
async def get_me(
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    db_user, profile = await get_or_create_user_profile(
        db,
        user["user_id"],
        email=user.get("email"),
    )
    return serialize_user_profile(db_user, profile)


@router.patch("/me")
async def update_me(
    payload: UserProfileUpdate,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    _, profile = await get_or_create_user_profile(
        db,
        user["user_id"],
        email=user.get("email"),
    )

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(profile, field, value)

    await db.flush()
    return {"status": "updated"}
