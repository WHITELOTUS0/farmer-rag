"""
Crop CRUD endpoints (user-scoped).
"""

import uuid
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_current_user, get_db_session
from src.database.models import Crop, CropType, Farm, GrowthStage

router = APIRouter()


class CropCreate(BaseModel):
    farm_id: uuid.UUID
    crop_type: str
    variety: Optional[str] = None
    planting_date: Optional[datetime] = None
    current_growth_stage: Optional[str] = None
    expected_harvest_date: Optional[datetime] = None
    actual_harvest_date: Optional[datetime] = None
    expected_yield_kg: Optional[float] = None
    actual_yield_kg: Optional[float] = None
    area_hectares: Optional[float] = None
    is_active: Optional[bool] = True
    notes: Optional[str] = None


class CropUpdate(BaseModel):
    crop_type: Optional[str] = None
    variety: Optional[str] = None
    planting_date: Optional[datetime] = None
    current_growth_stage: Optional[str] = None
    expected_harvest_date: Optional[datetime] = None
    actual_harvest_date: Optional[datetime] = None
    expected_yield_kg: Optional[float] = None
    actual_yield_kg: Optional[float] = None
    area_hectares: Optional[float] = None
    is_active: Optional[bool] = None
    notes: Optional[str] = None


def _parse_crop_type(value: str) -> CropType:
    try:
        return CropType(value.lower())
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid crop_type. Use maize, beans, or tomatoes.",
        ) from exc


def _parse_growth_stage(value: Optional[str]) -> Optional[GrowthStage]:
    if value is None:
        return None
    try:
        return GrowthStage(value.lower())
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid growth_stage value.",
        ) from exc


@router.get("/", response_model=List[dict])
async def list_crops(
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    result = await db.execute(
        select(Crop)
        .join(Farm, Farm.id == Crop.farm_id)
        .where(Farm.user_id == user["user_id"])
        .order_by(Crop.created_at.desc())
    )
    crops = result.scalars().all()
    return [
        {
            "id": str(crop.id),
            "farm_id": str(crop.farm_id),
            "crop_type": crop.crop_type.value,
            "variety": crop.variety,
            "planting_date": crop.planting_date,
            "current_growth_stage": crop.current_growth_stage.value,
            "expected_harvest_date": crop.expected_harvest_date,
            "actual_harvest_date": crop.actual_harvest_date,
            "expected_yield_kg": crop.expected_yield_kg,
            "actual_yield_kg": crop.actual_yield_kg,
            "area_hectares": crop.area_hectares,
            "is_active": crop.is_active,
            "notes": crop.notes,
        }
        for crop in crops
    ]


@router.post("/", response_model=dict)
async def create_crop(
    payload: CropCreate,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    result = await db.execute(
        select(Farm).where(Farm.id == payload.farm_id, Farm.user_id == user["user_id"])
    )
    farm = result.scalar_one_or_none()
    if farm is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Farm not found")

    crop = Crop(
        farm_id=payload.farm_id,
        crop_type=_parse_crop_type(payload.crop_type),
        variety=payload.variety,
        planting_date=payload.planting_date,
        current_growth_stage=_parse_growth_stage(payload.current_growth_stage) or GrowthStage.PLANTING,
        expected_harvest_date=payload.expected_harvest_date,
        actual_harvest_date=payload.actual_harvest_date,
        expected_yield_kg=payload.expected_yield_kg,
        actual_yield_kg=payload.actual_yield_kg,
        area_hectares=payload.area_hectares,
        is_active=payload.is_active if payload.is_active is not None else True,
        notes=payload.notes,
    )
    db.add(crop)
    await db.flush()
    return {"id": str(crop.id)}


@router.patch("/{crop_id}", response_model=dict)
async def update_crop(
    crop_id: uuid.UUID,
    payload: CropUpdate,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    result = await db.execute(
        select(Crop)
        .join(Farm, Farm.id == Crop.farm_id)
        .where(Crop.id == crop_id, Farm.user_id == user["user_id"])
    )
    crop = result.scalar_one_or_none()
    if crop is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Crop not found")

    data = payload.model_dump(exclude_unset=True)
    if "crop_type" in data:
        data["crop_type"] = _parse_crop_type(data["crop_type"])
    if "current_growth_stage" in data:
        data["current_growth_stage"] = _parse_growth_stage(data["current_growth_stage"])

    for field, value in data.items():
        setattr(crop, field, value)

    await db.flush()
    return {"status": "updated"}


@router.delete("/{crop_id}", response_model=dict)
async def delete_crop(
    crop_id: uuid.UUID,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    result = await db.execute(
        select(Crop)
        .join(Farm, Farm.id == Crop.farm_id)
        .where(Crop.id == crop_id, Farm.user_id == user["user_id"])
    )
    crop = result.scalar_one_or_none()
    if crop is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Crop not found")

    await db.delete(crop)
    await db.flush()
    return {"status": "deleted"}
