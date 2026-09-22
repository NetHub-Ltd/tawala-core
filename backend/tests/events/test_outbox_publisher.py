"""Outbox publisher claim / publish / retry (T4).

Important: after session.commit(), ORM instances are expired (expire_on_commit).
Always capture scalar ids (UUID) before commit/process and use those in filters —
never touch attributes on expired instances (causes MissingGreenlet under async).
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from sqlmodel import select

from app.core_platform.events.publisher import OutboxPublisher
from app.core_platform.events.service import EventService
from app.models.events import OutboxEntry, OutboxStatus


async def _drain_outbox(session, pub: OutboxPublisher, *, max_rounds: int = 20) -> dict[str, int]:
    """Process until no claimable rows (shared DB may hold leftovers from other tests)."""
    totals = {"claimed": 0, "published": 0, "failed": 0}
    for _ in range(max_rounds):
        stats = await pub.process_batch(limit=50)
        totals["claimed"] += stats["claimed"]
        totals["published"] += stats["published"]
        totals["failed"] += stats["failed"]
        if stats["claimed"] == 0:
            break
    return totals


@pytest.mark.asyncio
async def test_publisher_marks_published(db_session):
    biz = uuid4()
    event = await EventService(db_session).emit(
        event_type="test.created",
        aggregate_type="test",
        aggregate_id=uuid4(),
        payload={"ok": True},
        business_id=biz,
        commit=True,
    )
    event_id = event.id  # capture before further commits expire the instance

    pub = OutboxPublisher(db_session)
    stats = await _drain_outbox(db_session, pub)
    assert stats["claimed"] >= 1
    assert stats["published"] >= 1

    entry = (
        await db_session.exec(select(OutboxEntry).where(OutboxEntry.event_id == event_id))
    ).first()
    assert entry is not None
    assert entry.status == OutboxStatus.PUBLISHED
    assert entry.attempts >= 1


@pytest.mark.asyncio
async def test_publisher_retry_on_failure(db_session):
    event = await EventService(db_session).emit(
        event_type="test.fail",
        aggregate_type="test",
        aggregate_id=uuid4(),
        payload={},
        commit=True,
    )
    event_id = event.id

    async def boom(_event, _entry):
        raise RuntimeError("delivery down")

    pub = OutboxPublisher(db_session, deliver=boom, max_attempts=3)
    for _ in range(20):
        stats = await pub.process_batch(limit=50)
        entry = (
            await db_session.exec(
                select(OutboxEntry).where(OutboxEntry.event_id == event_id)
            )
        ).first()
        assert entry is not None
        if entry.status == OutboxStatus.FAILED and entry.attempts >= 1:
            break
        if stats["claimed"] == 0:
            break

    entry = (
        await db_session.exec(select(OutboxEntry).where(OutboxEntry.event_id == event_id))
    ).first()
    assert entry is not None
    assert entry.status == OutboxStatus.FAILED
    assert entry.attempts >= 1
    assert entry.last_error is not None
    assert "delivery down" in (entry.last_error or "")
    assert entry.next_attempt_at is not None


@pytest.mark.asyncio
async def test_published_not_reclaimed(db_session):
    event = await EventService(db_session).emit(
        event_type="test.once",
        aggregate_type="test",
        aggregate_id=uuid4(),
        payload={},
        commit=True,
    )
    event_id = event.id

    pub = OutboxPublisher(db_session)
    await _drain_outbox(db_session, pub)
    stats = await pub.process_batch(limit=50)
    assert stats["claimed"] == 0

    entry = (
        await db_session.exec(select(OutboxEntry).where(OutboxEntry.event_id == event_id))
    ).first()
    assert entry is not None
    assert entry.status == OutboxStatus.PUBLISHED
