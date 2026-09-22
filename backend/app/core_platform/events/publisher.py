"""Outbox publisher — claim PENDING entries, deliver, mark published/failed.

Delivery is intentionally pluggable: the default sink records success in-process
so Core can prove the claim/retry/mark cycle without requiring an external broker.
Domain modules may inject a custom ``deliver`` coroutine later.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from datetime import timedelta

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlalchemy import and_, or_

from app.models.base import utc_now
from app.models.events import DomainEvent, OutboxEntry, OutboxStatus

logger = logging.getLogger(__name__)

DEFAULT_MAX_ATTEMPTS = 8
BASE_BACKOFF_SECONDS = 30

DeliverFn = Callable[[DomainEvent, OutboxEntry], Awaitable[None]]


async def _default_deliver(event: DomainEvent, entry: OutboxEntry) -> None:
    """In-process sink — logs and succeeds. Replace for real bus/webhook delivery."""
    logger.info(
        "outbox.delivered event_id=%s type=%s aggregate=%s/%s",
        event.id,
        event.event_type,
        event.aggregate_type,
        event.aggregate_id,
    )


class OutboxPublisher:
    """Claim and process outbox rows safely for concurrent workers."""

    def __init__(
        self,
        session: AsyncSession,
        *,
        max_attempts: int = DEFAULT_MAX_ATTEMPTS,
        deliver: DeliverFn | None = None,
    ) -> None:
        self._session = session
        self._max_attempts = max_attempts
        self._deliver = deliver or _default_deliver

    async def claim_batch(
        self, *, limit: int = 20
    ) -> list[tuple[OutboxEntry, DomainEvent]]:
        """Select claimable rows with FOR UPDATE SKIP LOCKED, then load events.

        Avoids JOIN + FOR UPDATE (problematic under asyncpg) by locking
        ``outbox_entries`` alone, then fetching ``domain_events`` by id.
        """
        now = utc_now()
        stmt = (
            select(OutboxEntry)
            .where(
                OutboxEntry.deleted_at.is_(None),  # type: ignore[attr-defined]
                or_(
                    OutboxEntry.status == OutboxStatus.PENDING,
                    and_(
                        OutboxEntry.status == OutboxStatus.FAILED,
                        or_(
                            OutboxEntry.next_attempt_at.is_(None),  # type: ignore[union-attr]
                            OutboxEntry.next_attempt_at <= now,  # type: ignore[operator]
                        ),
                        OutboxEntry.attempts < self._max_attempts,
                    ),
                ),
            )
            .order_by(OutboxEntry.created_at.asc())  # type: ignore[attr-defined]
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        entries = list((await self._session.exec(stmt)).all())
        claimed: list[tuple[OutboxEntry, DomainEvent]] = []
        for entry in entries:
            event = await self._session.get(DomainEvent, entry.event_id)
            if event is None:
                logger.warning("outbox.missing_event entry_id=%s event_id=%s", entry.id, entry.event_id)
                continue
            entry.attempts = int(entry.attempts or 0) + 1
            entry.touch()
            self._session.add(entry)
            claimed.append((entry, event))
        if claimed:
            await self._session.flush()
        return claimed

    async def mark_published(self, entry: OutboxEntry) -> None:
        entry.status = OutboxStatus.PUBLISHED
        entry.last_error = None
        entry.next_attempt_at = None
        entry.touch()
        self._session.add(entry)

    async def mark_failed(self, entry: OutboxEntry, error: str) -> None:
        entry.status = OutboxStatus.FAILED
        entry.last_error = (error or "unknown")[:1024]
        if entry.attempts >= self._max_attempts:
            entry.next_attempt_at = None
        else:
            delay = BASE_BACKOFF_SECONDS * entry.attempts
            entry.next_attempt_at = utc_now() + timedelta(seconds=delay)
        entry.touch()
        self._session.add(entry)

    async def process_batch(self, *, limit: int = 20) -> dict[str, int]:
        """Claim, deliver, and finalize a batch. Returns counts."""
        claimed = await self.claim_batch(limit=limit)
        published = 0
        failed = 0
        for entry, event in claimed:
            try:
                await self._deliver(event, entry)
                await self.mark_published(entry)
                published += 1
            except Exception as exc:  # noqa: BLE001
                logger.exception("outbox.delivery_failed event_id=%s", entry.event_id)
                await self.mark_failed(entry, str(exc))
                failed += 1
        await self._session.commit()
        return {
            "claimed": len(claimed),
            "published": published,
            "failed": failed,
        }


async def run_once(session: AsyncSession, *, limit: int = 20) -> dict[str, int]:
    """Process one outbox batch (CLI / cron entrypoint)."""
    return await OutboxPublisher(session).process_batch(limit=limit)
