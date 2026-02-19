"""
User service helpers.
"""

from typing import Optional, Tuple, Dict, Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models import User, UserProfile, UserRole


async def get_or_create_user_profile(
    db: AsyncSession,
    user_id,
    email: Optional[str] = None,
) -> Tuple[User, UserProfile]:
    result = await db.execute(select(User).where(User.id == user_id))
    db_user = result.scalar_one_or_none()
    if db_user is None:
        db_user = User(id=user_id, email=email, role=UserRole.FARMER)
        db.add(db_user)
        await db.flush()
    elif email and db_user.email != email:
        db_user.email = email

    result = await db.execute(select(UserProfile).where(UserProfile.user_id == user_id))
    profile = result.scalar_one_or_none()
    if profile is None:
        profile = UserProfile(user_id=user_id)
        db.add(profile)
        await db.flush()

    return db_user, profile


def serialize_user_profile(db_user: User, profile: UserProfile) -> Dict[str, Any]:
    return {
        "user": {
            "id": str(db_user.id),
            "email": db_user.email,
            "role": db_user.role.value if isinstance(db_user.role, UserRole) else str(db_user.role),
        },
        "profile": {
            "id": str(profile.id),
            "name": profile.name,
            "phone": profile.phone,
            "region": profile.region,
            "language": profile.language,
            "location_lat": profile.location_lat,
            "location_lon": profile.location_lon,
        },
    }
