"""
Repository for Advisory database operations.

Handles storing and retrieving advisory history, which is crucial
for tracking groundedness scores and farmer interactions.
"""

import uuid
from typing import Optional, List
from datetime import datetime, timedelta

from sqlalchemy import select, update, func
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models import Advisory


class AdvisoryRepository:
    """Repository for advisory-related database operations."""

    def __init__(self, session: AsyncSession):
        """
        Initialize the repository with a database session.

        Args:
            session: SQLAlchemy async session
        """
        self.session = session

    async def create_advisory(
        self,
        user_id: uuid.UUID,
        query: str,
        response: str,
        groundedness_score: float,
        model_used: str,
        sources: Optional[dict] = None,
        tools_used: Optional[dict] = None,
        claims_verified: Optional[dict] = None,
        processing_time_ms: Optional[int] = None,
    ) -> Advisory:
        """
        Create a new advisory record.

        Args:
            user_id: UUID of the user who received the advisory
            query: The user's original question
            response: The generated advisory response
            groundedness_score: Verification score (0-1)
            model_used: Name of the LLM model used
            sources: Retrieved source documents and their relevance
            tools_used: Tools invoked during processing
            claims_verified: Verification results for each claim
            processing_time_ms: Time taken to generate response

        Returns:
            Advisory: Created advisory instance
        """
        advisory = Advisory(
            user_id=user_id,
            query=query,
            response=response,
            groundedness_score=groundedness_score,
            model_used=model_used,
            sources=sources,
            tools_used=tools_used,
            claims_verified=claims_verified,
            processing_time_ms=processing_time_ms,
        )
        self.session.add(advisory)
        await self.session.flush()
        return advisory

    async def get_advisory_by_id(
        self,
        advisory_id: uuid.UUID,
    ) -> Optional[Advisory]:
        """
        Get an advisory by its ID.

        Args:
            advisory_id: UUID of the advisory

        Returns:
            Advisory or None if not found
        """
        query = select(Advisory).where(Advisory.id == advisory_id)
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def get_user_advisories(
        self,
        user_id: uuid.UUID,
        limit: int = 50,
        offset: int = 0,
    ) -> List[Advisory]:
        """
        Get all advisories for a specific user.

        Args:
            user_id: UUID of the user
            limit: Maximum number of advisories to return
            offset: Number of advisories to skip

        Returns:
            List of Advisory instances, ordered by most recent first
        """
        query = (
            select(Advisory)
            .where(Advisory.user_id == user_id)
            .order_by(Advisory.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_recent_advisories(
        self,
        user_id: uuid.UUID,
        hours: int = 24,
    ) -> List[Advisory]:
        """
        Get advisories from the last N hours for a user.

        Useful for providing context about recent interactions.

        Args:
            user_id: UUID of the user
            hours: Number of hours to look back

        Returns:
            List of recent Advisory instances
        """
        cutoff = datetime.utcnow() - timedelta(hours=hours)
        query = (
            select(Advisory)
            .where(
                Advisory.user_id == user_id,
                Advisory.created_at >= cutoff,
            )
            .order_by(Advisory.created_at.desc())
        )
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def mark_acknowledged(
        self,
        advisory_id: uuid.UUID,
        feedback: Optional[str] = None,
    ) -> Optional[Advisory]:
        """
        Mark an advisory as acknowledged by the farmer.

        Args:
            advisory_id: UUID of the advisory
            feedback: Optional feedback from the farmer

        Returns:
            Updated Advisory or None if not found
        """
        stmt = (
            update(Advisory)
            .where(Advisory.id == advisory_id)
            .values(
                acknowledged=True,
                acknowledged_at=datetime.utcnow(),
                farmer_feedback=feedback,
            )
            .returning(Advisory)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_average_groundedness_score(
        self,
        farmer_id: Optional[uuid.UUID] = None,
        days: int = 30,
    ) -> float:
        """
        Calculate average groundedness score over a period.

        Args:
            farmer_id: Optional - filter by farmer, or system-wide if None
            days: Number of days to look back

        Returns:
            Average groundedness score (0-1)
        """
        cutoff = datetime.utcnow() - timedelta(days=days)
        query = select(func.avg(Advisory.groundedness_score)).where(
            Advisory.created_at >= cutoff
        )

        if farmer_id:
            query = query.where(Advisory.user_id == farmer_id)

        result = await self.session.execute(query)
        avg_score = result.scalar()
        return float(avg_score) if avg_score else 0.0

    async def get_advisory_stats(
        self,
        days: int = 30,
    ) -> dict:
        """
        Get advisory statistics for the admin dashboard.

        Args:
            days: Number of days to analyze

        Returns:
            Dictionary with various statistics
        """
        cutoff = datetime.utcnow() - timedelta(days=days)

        # Total advisories
        total_query = select(func.count(Advisory.id)).where(
            Advisory.created_at >= cutoff
        )
        total_result = await self.session.execute(total_query)
        total_count = total_result.scalar() or 0

        # Average groundedness score
        avg_score = await self.get_average_groundedness_score(days=days)

        # Acknowledgment rate
        ack_query = select(func.count(Advisory.id)).where(
            Advisory.created_at >= cutoff,
            Advisory.acknowledged == True,
        )
        ack_result = await self.session.execute(ack_query)
        ack_count = ack_result.scalar() or 0
        ack_rate = (ack_count / total_count * 100) if total_count > 0 else 0

        # Low score advisories (below threshold)
        low_score_query = select(func.count(Advisory.id)).where(
            Advisory.created_at >= cutoff,
            Advisory.groundedness_score < 0.8,
        )
        low_score_result = await self.session.execute(low_score_query)
        low_score_count = low_score_result.scalar() or 0

        return {
            "total_advisories": total_count,
            "average_groundedness_score": round(avg_score, 3),
            "acknowledgment_rate": round(ack_rate, 1),
            "low_score_count": low_score_count,
            "period_days": days,
        }
