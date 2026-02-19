"""
Farmer routes backed by user profiles (admin-only).
"""

from typing import Optional, List
import uuid

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import require_admin, get_db_session
from src.database.models import User, UserProfile, UserRole

router = APIRouter()


class FarmerCreate(BaseModel):
    user_id: uuid.UUID
    name: Optional[str] = None
    phone: Optional[str] = None
    region: Optional[str] = None
    language: Optional[str] = None
    location_lat: Optional[float] = None
    location_lon: Optional[float] = None


class FarmerUpdate(BaseModel):
    name: Optional[str] = None
    phone: Optional[str] = None
    region: Optional[str] = None
    language: Optional[str] = None
    location_lat: Optional[float] = None
    location_lon: Optional[float] = None


@router.get("/", response_model=List[dict])
async def list_farmers(
    user: dict = Depends(require_admin),
    db: AsyncSession = Depends(get_db_session),
):
    result = await db.execute(
        select(User, UserProfile)
        .join(UserProfile, UserProfile.user_id == User.id)
        .where(User.role == UserRole.FARMER)
        .order_by(User.created_at.desc())
    )
    rows = result.all()
    return [
        {
            "user_id": str(db_user.id),
            "email": db_user.email,
            "name": profile.name,
            "phone": profile.phone,
            "region": profile.region,
            "language": profile.language,
            "location_lat": profile.location_lat,
            "location_lon": profile.location_lon,
        }
        for db_user, profile in rows
    ]


@router.post("/", response_model=dict)
async def create_farmer(
    payload: FarmerCreate,
    user: dict = Depends(require_admin),
    db: AsyncSession = Depends(get_db_session),
):
    result = await db.execute(select(User).where(User.id == payload.user_id))
    db_user = result.scalar_one_or_none()
    if db_user is None:
        return {"error": "user not found"}

    result = await db.execute(select(UserProfile).where(UserProfile.user_id == payload.user_id))
    profile = result.scalar_one_or_none()
    if profile is None:
        profile = UserProfile(user_id=payload.user_id)
        db.add(profile)

    for field, value in payload.model_dump(exclude_unset=True).items():
        if field == "user_id":
            continue
        setattr(profile, field, value)

    await db.flush()
    return {"user_id": str(payload.user_id)}


@router.patch("/{farmer_id}")
async def update_farmer(
    farmer_id: uuid.UUID,
    payload: FarmerUpdate,
    user: dict = Depends(require_admin),
    db: AsyncSession = Depends(get_db_session),
):
    result = await db.execute(select(UserProfile).where(UserProfile.user_id == farmer_id))
    profile = result.scalar_one_or_none()
    if profile is None:
        return {"error": "farmer profile not found"}

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(profile, field, value)

    await db.flush()
    return {"status": "updated"}
