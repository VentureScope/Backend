from datetime import datetime, timedelta, timezone
from sqlalchemy import select, func, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.job import Job


class JobRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_trending(self, period_days: int = 30, limit: int = 10) -> list[dict]:
        cutoff = datetime.now(timezone.utc) - timedelta(days=period_days)
        stmt = (
            select(
                Job.normalized_title,
                func.count(Job.id).label("job_count"),
                func.count(func.distinct(Job.company_name)).label("company_count"),
            )
            .where(
                Job.posted_date >= cutoff,
                Job.normalized_title.isnot(None),
            )
            .group_by(Job.normalized_title)
            .order_by(func.count(Job.id).desc())
            .limit(limit)
        )
        result = await self.db.execute(stmt)
        rows = result.all()

        trends = []
        for row in rows:
            growth = await self._growth_pct(
                row.normalized_title, cutoff - timedelta(days=period_days), cutoff
            )
            trends.append(
                {
                    "name": row.normalized_title,
                    "job_count": row.job_count,
                    "company_count": row.company_count,
                    "growth_pct": growth,
                }
            )
        return trends

    async def _growth_pct(
        self, category: str, prev_start: datetime, prev_end: datetime
    ) -> float | None:
        current_start = prev_end
        current_end = datetime.now(timezone.utc)

        prev_count = await self._count_category(category, prev_start, prev_end)
        curr_count = await self._count_category(category, current_start, current_end)

        if prev_count and prev_count > 0:
            return round(((curr_count - prev_count) / prev_count) * 100, 1)
        return None

    async def _count_category(
        self, category: str, start: datetime, end: datetime
    ) -> int:
        stmt = select(func.count(Job.id)).where(
            Job.normalized_title == category,
            Job.posted_date >= start,
            Job.posted_date < end,
        )
        result = await self.db.execute(stmt)
        return result.scalar() or 0

    async def get_in_demand_skills(self, limit: int = 20, period_days: int = 90) -> list[dict]:
        cutoff = datetime.now(timezone.utc) - timedelta(days=period_days)
        stmt = text("""
            SELECT skill, COUNT(*) AS demand
            FROM jobs,
            jsonb_array_elements_text(skills) AS skill
            WHERE skills IS NOT NULL
              AND posted_date >= :cutoff
            GROUP BY skill
            ORDER BY demand DESC
            LIMIT :limit
        """)
        result = await self.db.execute(stmt, {"limit": limit, "cutoff": cutoff})
        return [{"skill": row.skill, "demand": row.demand} for row in result.all()]

    async def get_stats(self, period_days: int = 90) -> dict:
        cutoff = datetime.now(timezone.utc) - timedelta(days=period_days)
        total = await self.db.execute(
            select(func.count(Job.id)).where(Job.posted_date >= cutoff)
        )
        companies = await self.db.execute(
            select(func.count(func.distinct(Job.company_name))).where(Job.posted_date >= cutoff)
        )
        categories = await self.db.execute(
            select(func.count(func.distinct(Job.normalized_title))).where(
                Job.normalized_title.isnot(None),
                Job.posted_date >= cutoff,
            )
        )
        dates = await self.db.execute(
            select(func.min(Job.posted_date), func.max(Job.posted_date)).where(
                Job.posted_date >= cutoff
            )
        )
        min_date, max_date = dates.one()
        return {
            "total_jobs": total.scalar() or 0,
            "unique_companies": companies.scalar() or 0,
            "unique_categories": categories.scalar() or 0,
            "date_range": [min_date, max_date],
        }

    async def match_by_embedding(
        self, embedding: list[float], limit: int = 10
    ) -> list[dict]:
        stmt = (
            select(
                Job.id,
                Job.job_title,
                Job.company_name,
                Job.normalized_title,
                Job.city,
                Job.job_type,
                Job.embedding.cosine_distance(embedding).label("distance"),
            )
            .where(Job.embedding.isnot(None))
            .order_by(Job.embedding.cosine_distance(embedding))
            .limit(limit)
        )
        result = await self.db.execute(stmt)
        return [
            {
                "id": row.id,
                "job_title": row.job_title,
                "company_name": row.company_name,
                "normalized_title": row.normalized_title,
                "city": row.city,
                "job_type": row.job_type,
                "distance": float(row.distance),
            }
            for row in result.all()
        ]

    async def get_by_category(
        self, category: str, limit: int = 20, offset: int = 0
    ) -> list[Job]:
        stmt = (
            select(Job)
            .where(Job.normalized_title == category)
            .order_by(Job.posted_date.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())
