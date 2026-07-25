"""Interest Graph — record and aggregate user interest signals."""

import logging

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import UserInterestSignal

logger = logging.getLogger(__name__)


async def record_signals(
    db: AsyncSession,
    user_id: str,
    topics: list[str],
    source: str,
    weight: float,
    source_id: str | None = None,
) -> int:
    """Record interest signals for a user. Returns count of signals added.

    Args:
        user_id: ID of the user.
        topics: list of topic slugs (e.g. "ai-tools", "chatgpt").
        source: signal source — "parse" | "like" | "follow" | "script" | "instagram".
        weight: signal strength (parse=1.0, like=0.5, follow=0.7, script=1.2, instagram=0.8).
        source_id: optional related object ID (library_reel_id, profile_id, etc.).
    """
    count = 0
    for topic in topics:
        if not topic or not topic.strip():
            continue
        slug = topic.lower().strip()
        if len(slug) > 100:
            slug = slug[:100]
        db.add(UserInterestSignal(
            user_id=user_id,
            topic=slug,
            source=source,
            weight=weight,
            source_id=source_id,
        ))
        count += 1
    if count:
        logger.info(f"[interests] Recorded {count} signals for user {user_id[:8]}… source={source}")
    return count


async def get_interest_vector(
    db: AsyncSession,
    user_id: str,
    top_n: int = 30,
) -> dict[str, float]:
    """Build weighted, time-decayed interest vector from all signals.

    Formula: SUM(weight * exp(-0.023 * days_since_signal))
    Half-life ~30 days (a month-old signal = 50% weight).

    Returns: {"ai-tools": 4.2, "chatgpt": 3.1, ...} — top N topics by score.
    """
    result = await db.execute(
        text("""
            SELECT topic,
                   SUM(weight * EXP(-0.023 * EXTRACT(EPOCH FROM now() - created_at) / 86400))
                   AS score
            FROM user_interest_signals
            WHERE user_id = :uid
            GROUP BY topic
            HAVING SUM(weight * EXP(-0.023 * EXTRACT(EPOCH FROM now() - created_at) / 86400)) > 0.01
            ORDER BY score DESC
            LIMIT :n
        """),
        {"uid": user_id, "n": top_n},
    )
    return {row[0]: round(float(row[1]), 3) for row in result.all()}
