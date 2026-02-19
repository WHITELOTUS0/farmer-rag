"""
Seed or promote an admin user in the local database.
"""

import os
import sys
import uuid
from pathlib import Path

from sqlalchemy import select

project_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(project_root))

from src.config.settings import get_settings
from src.database.connection import get_sync_session
from src.database.models import User, UserProfile, UserRole


def main() -> int:
    settings = get_settings()
    admin_user_id = os.environ.get("ADMIN_USER_ID")
    admin_email = os.environ.get("ADMIN_EMAIL")
    admin_name = os.environ.get("ADMIN_NAME")

    if not admin_user_id:
        print("ADMIN_USER_ID is required")
        return 1

    try:
        admin_uuid = uuid.UUID(admin_user_id)
    except ValueError:
        print("ADMIN_USER_ID must be a valid UUID")
        return 1

    session = get_sync_session()
    try:
        result = session.execute(select(User).where(User.id == admin_uuid))
        db_user = result.scalar_one_or_none()
        if db_user is None:
            db_user = User(id=admin_uuid, email=admin_email, role=UserRole.ADMIN)
            session.add(db_user)
            session.flush()
        else:
            db_user.role = UserRole.ADMIN
            if admin_email:
                db_user.email = admin_email

        result = session.execute(select(UserProfile).where(UserProfile.user_id == admin_uuid))
        profile = result.scalar_one_or_none()
        if profile is None:
            profile = UserProfile(user_id=admin_uuid, name=admin_name)
            session.add(profile)
        elif admin_name:
            profile.name = admin_name

        session.commit()
        print(f"Admin user seeded: {db_user.id}")
        return 0
    finally:
        session.close()


if __name__ == "__main__":
    raise SystemExit(main())
