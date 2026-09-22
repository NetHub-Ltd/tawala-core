"""Audit and event unit contracts (M9)."""

from uuid import uuid4

from app.models.audit import AuditOutcome, AuditRecord
from app.models.events import DomainEvent, OutboxEntry, OutboxStatus


def test_audit_record_fields():
    r = AuditRecord(
        action="security.membership.revoke",
        resource_type="membership",
        resource_id=uuid4(),
        outcome=AuditOutcome.SUCCESS,
        occurred_at=__import__("datetime").datetime.now(
            __import__("datetime").UTC
        ),
    )
    assert r.action == "security.membership.revoke"
    assert r.outcome == AuditOutcome.SUCCESS


def test_outbox_defaults_pending():
    e = OutboxEntry(event_id=uuid4())
    assert e.status == OutboxStatus.PENDING
    assert e.attempts == 0


def test_domain_event_payload():
    ev = DomainEvent(
        event_type="membership.revoked",
        occurred_at=__import__("datetime").datetime.now(
            __import__("datetime").UTC
        ),
        aggregate_type="membership",
        aggregate_id=uuid4(),
        payload={"ok": True},
    )
    assert ev.payload["ok"] is True
    assert ev.version == 1
