"""record_activity contracts (P1)."""

from app.core_platform.shared import activity


def test_record_activity_module_exports():
    assert callable(activity.record_activity)
