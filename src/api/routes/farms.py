"""
Farm CRUD endpoints (user-scoped).
"""

import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_current_user, get_db_session
from src.database.models import Farm

router = APIRouter()


class FarmCreate(BaseModel):
    name: str
    size_hectares: Optional[float] = None
    soil_type: Optional[str] = None
    location_lat: Optional[float] = None
    location_lon: Optional[float] = None
    irrigation_type: Optional[str] = None
    notes: Optional[str] = None


class FarmUpdate(BaseModel):
    name: Optional[str] = None
    size_hectares: Optional[float] = None
    soil_type: Optional[str] = None
    location_lat: Optional[float] = None
    location_lon: Optional[float] = None
    irrigation_type: Optional[str] = None
    notes: Optional[str] = None


@router.get("/", response_model=List[dict])
async def list_farms(
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    result = await db.execute(
        select(Farm)
        .where(Farm.user_id == user["user_id"])
        .order_by(Farm.created_at.desc())
    )
    farms = result.scalars().all()
    return [
        {
            "id": str(farm.id),
            "name": farm.name,
            "size_hectares": farm.size_hectares,
            "soil_type": farm.soil_type,
            "location_lat": farm.location_lat,
            "location_lon": farm.location_lon,
            "irrigation_type": farm.irrigation_type,
            "notes": farm.notes,
        }
        for farm in farms
    ]


@router.post("/", response_model=dict)
async def create_farm(
    payload: FarmCreate,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    farm = Farm(
        user_id=user["user_id"],
        name=payload.name,
        size_hectares=payload.size_hectares,
        soil_type=payload.soil_type,
        location_lat=payload.location_lat,
        location_lon=payload.location_lon,
        irrigation_type=payload.irrigation_type,
        notes=payload.notes,
    )
    db.add(farm)
    await db.flush()
    return {"id": str(farm.id)}


@router.patch("/{farm_id}", response_model=dict)
async def update_farm(
    farm_id: uuid.UUID,
    payload: FarmUpdate,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    result = await db.execute(
        select(Farm).where(Farm.id == farm_id, Farm.user_id == user["user_id"])
    )
    farm = result.scalar_one_or_none()
    if farm is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Farm not found")

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(farm, field, value)

    await db.flush()
    return {"status": "updated"}


@router.delete("/{farm_id}", response_model=dict)
async def delete_farm(
    farm_id: uuid.UUID,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    result = await db.execute(
        select(Farm).where(Farm.id == farm_id, Farm.user_id == user["user_id"])
    )
    farm = result.scalar_one_or_none()
    if farm is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Farm not found")

    await db.delete(farm)
    await db.flush()
    return {"status": "deleted"}
