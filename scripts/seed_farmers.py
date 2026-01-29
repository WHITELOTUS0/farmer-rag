#!/usr/bin/env python
"""
Seed the database with sample farmer data.

Usage:
    python scripts/seed_farmers.py
"""

import sys
import asyncio
from pathlib import Path
from datetime import datetime, timedelta

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


async def seed_farmers():
    """Seed database with sample farmers, farms, and crops."""
    from src.database.connection import init_db, get_async_session
    from src.database.repositories.farmer import FarmerRepository
    from src.database.models import CropType, GrowthStage

    print("Initializing database...")
    await init_db()

    async with get_async_session() as session:
        repo = FarmerRepository(session)

        # Sample farmers data
        farmers_data = [
            {
                "name": "Jean Baptiste",
                "phone": "+250788123456",
                "region": "Kigali",
                "district": "Gasabo",
                "location_lat": -1.9403,
                "location_lon": 29.8739,
                "farms": [
                    {
                        "name": "Kimironko Plot",
                        "size_hectares": 2.5,
                        "soil_type": "loam",
                        "crops": [
                            {"type": CropType.MAIZE, "stage": GrowthStage.VEGETATIVE, "days_ago": 45},
                            {"type": CropType.BEANS, "stage": GrowthStage.FLOWERING, "days_ago": 40},
                        ],
                    }
                ],
            },
            {
                "name": "Marie Claire",
                "phone": "+250788234567",
                "region": "Butare",
                "district": "Huye",
                "location_lat": -2.5967,
                "location_lon": 29.7394,
                "farms": [
                    {
                        "name": "Huye Farm",
                        "size_hectares": 1.5,
                        "soil_type": "clay",
                        "crops": [
                            {"type": CropType.TOMATOES, "stage": GrowthStage.FRUITING, "days_ago": 60},
                        ],
                    },
                    {
                        "name": "Hillside Plot",
                        "size_hectares": 0.8,
                        "soil_type": "sandy loam",
                        "crops": [
                            {"type": CropType.MAIZE, "stage": GrowthStage.PLANTING, "days_ago": 7},
                        ],
                    }
                ],
            },
            {
                "name": "Peter Ochieng",
                "phone": "+254712345678",
                "region": "Kisumu",
                "district": "Kisumu Central",
                "location_lat": -0.0917,
                "location_lon": 34.7680,
                "farms": [
                    {
                        "name": "Lake View Farm",
                        "size_hectares": 3.0,
                        "soil_type": "alluvial",
                        "crops": [
                            {"type": CropType.MAIZE, "stage": GrowthStage.MATURITY, "days_ago": 100},
                            {"type": CropType.BEANS, "stage": GrowthStage.VEGETATIVE, "days_ago": 30},
                        ],
                    }
                ],
            },
        ]

        print("\nSeeding farmers...")
        for farmer_data in farmers_data:
            # Create farmer
            farmer = await repo.create_farmer(
                name=farmer_data["name"],
                phone=farmer_data["phone"],
                region=farmer_data["region"],
                district=farmer_data["district"],
                location_lat=farmer_data["location_lat"],
                location_lon=farmer_data["location_lon"],
            )
            print(f"  Created farmer: {farmer.name}")

            # Create farms and crops
            for farm_data in farmer_data["farms"]:
                farm = await repo.create_farm(
                    farmer_id=farmer.id,
                    name=farm_data["name"],
                    size_hectares=farm_data["size_hectares"],
                    soil_type=farm_data["soil_type"],
                    location_lat=farmer_data["location_lat"],
                    location_lon=farmer_data["location_lon"],
                )
                print(f"    Created farm: {farm.name}")

                # Create crops
                for crop_data in farm_data["crops"]:
                    planting_date = datetime.now() - timedelta(days=crop_data["days_ago"])
                    crop = await repo.create_crop(
                        farm_id=farm.id,
                        crop_type=crop_data["type"],
                        planting_date=planting_date,
                    )
                    # Update growth stage
                    await repo.update_crop_growth_stage(crop.id, crop_data["stage"])
                    print(f"      Created crop: {crop_data['type'].value} at {crop_data['stage'].value}")

        await session.commit()
        print("\n✅ Database seeded successfully!")


def main():
    asyncio.run(seed_farmers())


if __name__ == "__main__":
    main()
