"""
Repository for Farmer, Farm, and Crop database operations.

Provides a clean data access layer with async support for all
farmer-related CRUD operations.
"""

import uuid
from typing import Optional, List
from datetime import datetime

from sqlalchemy import select, update, delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.database.models import Farmer, Farm, Crop, CropType, GrowthStage


class FarmerRepository:
    """Repository for farmer-related database operations."""

    def __init__(self, session: AsyncSession):
        """
        Initialize the repository with a database session.

        Args:
            session: SQLAlchemy async session
        """
        self.session = session

    # ==================== Farmer Operations ====================

    async def create_farmer(
        self,
        name: str,
        phone: Optional[str] = None,
        email: Optional[str] = None,
        location_lat: Optional[float] = None,
        location_lon: Optional[float] = None,
        region: Optional[str] = None,
        district: Optional[str] = None,
        preferred_language: str = "en",
    ) -> Farmer:
        """
        Create a new farmer profile.

        Args:
            name: Farmer's full name
            phone: Phone number for SMS/WhatsApp
            email: Email address (optional)
            location_lat: Latitude of farmer's location
            location_lon: Longitude of farmer's location
            region: Geographic region (e.g., "Kigali")
            district: District within region
            preferred_language: Language code (default: "en")

        Returns:
            Farmer: Created farmer instance
        """
        farmer = Farmer(
            name=name,
            phone=phone,
            email=email,
            location_lat=location_lat,
            location_lon=location_lon,
            region=region,
            district=district,
            preferred_language=preferred_language,
        )
        self.session.add(farmer)
        await self.session.flush()
        return farmer

    async def get_farmer_by_id(
        self,
        farmer_id: uuid.UUID,
        include_farms: bool = False,
        include_crops: bool = False,
    ) -> Optional[Farmer]:
        """
        Get a farmer by their ID.

        Args:
            farmer_id: UUID of the farmer
            include_farms: Whether to eager-load farms
            include_crops: Whether to eager-load crops (requires include_farms)

        Returns:
            Farmer or None if not found
        """
        query = select(Farmer).where(Farmer.id == farmer_id)

        if include_farms:
            if include_crops:
                query = query.options(
                    selectinload(Farmer.farms).selectinload(Farm.crops)
                )
            else:
                query = query.options(selectinload(Farmer.farms))

        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def get_all_farmers(
        self,
        active_only: bool = True,
        limit: int = 100,
        offset: int = 0,
    ) -> List[Farmer]:
        """
        Get all farmers with pagination.

        Args:
            active_only: Filter to only active farmers
            limit: Maximum number of farmers to return
            offset: Number of farmers to skip

        Returns:
            List of Farmer instances
        """
        query = select(Farmer).limit(limit).offset(offset)

        if active_only:
            query = query.where(Farmer.is_active == True)

        query = query.order_by(Farmer.created_at.desc())
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def update_farmer(
        self,
        farmer_id: uuid.UUID,
        **kwargs,
    ) -> Optional[Farmer]:
        """
        Update a farmer's information.

        Args:
            farmer_id: UUID of the farmer to update
            **kwargs: Fields to update

        Returns:
            Updated Farmer or None if not found
        """
        # Remove None values to avoid overwriting with null
        update_data = {k: v for k, v in kwargs.items() if v is not None}

        if not update_data:
            return await self.get_farmer_by_id(farmer_id)

        stmt = (
            update(Farmer)
            .where(Farmer.id == farmer_id)
            .values(**update_data)
            .returning(Farmer)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def delete_farmer(self, farmer_id: uuid.UUID) -> bool:
        """
        Delete a farmer (soft delete by setting is_active=False).

        Args:
            farmer_id: UUID of the farmer to delete

        Returns:
            True if farmer was deleted, False if not found
        """
        stmt = (
            update(Farmer)
            .where(Farmer.id == farmer_id)
            .values(is_active=False)
        )
        result = await self.session.execute(stmt)
        return result.rowcount > 0

    async def get_farmers_by_region(self, region: str) -> List[Farmer]:
        """
        Get all active farmers in a specific region.

        Args:
            region: Region name to filter by

        Returns:
            List of Farmer instances in the region
        """
        query = (
            select(Farmer)
            .where(Farmer.region == region, Farmer.is_active == True)
            .order_by(Farmer.name)
        )
        result = await self.session.execute(query)
        return list(result.scalars().all())

    # ==================== Farm Operations ====================

    async def create_farm(
        self,
        farmer_id: uuid.UUID,
        name: str,
        size_hectares: Optional[float] = None,
        soil_type: Optional[str] = None,
        location_lat: Optional[float] = None,
        location_lon: Optional[float] = None,
        irrigation_type: Optional[str] = None,
        notes: Optional[str] = None,
    ) -> Farm:
        """
        Create a new farm for a farmer.

        Args:
            farmer_id: UUID of the farmer who owns this farm
            name: Name/identifier for the farm
            size_hectares: Size of the farm in hectares
            soil_type: Type of soil (e.g., "clay", "loam", "sandy")
            location_lat: Latitude of the farm
            location_lon: Longitude of the farm
            irrigation_type: Type of irrigation if any
            notes: Additional notes

        Returns:
            Farm: Created farm instance
        """
        farm = Farm(
            farmer_id=farmer_id,
            name=name,
            size_hectares=size_hectares,
            soil_type=soil_type,
            location_lat=location_lat,
            location_lon=location_lon,
            irrigation_type=irrigation_type,
            notes=notes,
        )
        self.session.add(farm)
        await self.session.flush()
        return farm

    async def get_farms_by_farmer(self, farmer_id: uuid.UUID) -> List[Farm]:
        """
        Get all farms for a specific farmer.

        Args:
            farmer_id: UUID of the farmer

        Returns:
            List of Farm instances
        """
        query = (
            select(Farm)
            .where(Farm.farmer_id == farmer_id)
            .options(selectinload(Farm.crops))
            .order_by(Farm.name)
        )
        result = await self.session.execute(query)
        return list(result.scalars().all())

    # ==================== Crop Operations ====================

    async def create_crop(
        self,
        farm_id: uuid.UUID,
        crop_type: CropType,
        variety: Optional[str] = None,
        planting_date: Optional[datetime] = None,
        area_hectares: Optional[float] = None,
        expected_yield_kg: Optional[float] = None,
        notes: Optional[str] = None,
    ) -> Crop:
        """
        Create a new crop planting record.

        Args:
            farm_id: UUID of the farm
            crop_type: Type of crop (maize, beans, tomatoes)
            variety: Specific variety of the crop
            planting_date: When the crop was planted
            area_hectares: Area planted
            expected_yield_kg: Expected yield in kg
            notes: Additional notes

        Returns:
            Crop: Created crop instance
        """
        crop = Crop(
            farm_id=farm_id,
            crop_type=crop_type,
            variety=variety,
            planting_date=planting_date,
            area_hectares=area_hectares,
            expected_yield_kg=expected_yield_kg,
            notes=notes,
            current_growth_stage=GrowthStage.PLANTING,
        )
        self.session.add(crop)
        await self.session.flush()
        return crop

    async def update_crop_growth_stage(
        self,
        crop_id: uuid.UUID,
        new_stage: GrowthStage,
    ) -> Optional[Crop]:
        """
        Update the growth stage of a crop.

        Args:
            crop_id: UUID of the crop
            new_stage: New growth stage

        Returns:
            Updated Crop or None if not found
        """
        stmt = (
            update(Crop)
            .where(Crop.id == crop_id)
            .values(current_growth_stage=new_stage)
            .returning(Crop)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_active_crops_by_farmer(
        self,
        farmer_id: uuid.UUID,
        crop_type: Optional[CropType] = None,
    ) -> List[Crop]:
        """
        Get all active crops for a farmer across all their farms.

        Args:
            farmer_id: UUID of the farmer
            crop_type: Optional filter by crop type

        Returns:
            List of active Crop instances
        """
        query = (
            select(Crop)
            .join(Farm)
            .where(Farm.farmer_id == farmer_id, Crop.is_active == True)
        )

        if crop_type:
            query = query.where(Crop.crop_type == crop_type)

        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_farmer_context(self, farmer_id: uuid.UUID) -> Optional[dict]:
        """
        Get complete context for a farmer including farms and crops.

        This is used by the agent to understand the farmer's current situation.

        Args:
            farmer_id: UUID of the farmer

        Returns:
            Dictionary with farmer details, farms, and crops, or None if not found
        """
        farmer = await self.get_farmer_by_id(
            farmer_id,
            include_farms=True,
            include_crops=True,
        )

        if not farmer:
            return None

        # Build context dictionary
        context = {
            "farmer": {
                "id": str(farmer.id),
                "name": farmer.name,
                "region": farmer.region,
                "district": farmer.district,
                "location": {
                    "lat": farmer.location_lat,
                    "lon": farmer.location_lon,
                } if farmer.location_lat and farmer.location_lon else None,
            },
            "farms": [],
        }

        for farm in farmer.farms:
            farm_data = {
                "id": str(farm.id),
                "name": farm.name,
                "size_hectares": farm.size_hectares,
                "soil_type": farm.soil_type,
                "location": {
                    "lat": farm.location_lat,
                    "lon": farm.location_lon,
                } if farm.location_lat and farm.location_lon else None,
                "crops": [],
            }

            for crop in farm.crops:
                if crop.is_active:
                    crop_data = {
                        "id": str(crop.id),
                        "type": crop.crop_type.value,
                        "variety": crop.variety,
                        "growth_stage": crop.current_growth_stage.value,
                        "planting_date": crop.planting_date.isoformat() if crop.planting_date else None,
                        "area_hectares": crop.area_hectares,
                    }
                    farm_data["crops"].append(crop_data)

            context["farms"].append(farm_data)

        return context
