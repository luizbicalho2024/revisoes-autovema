from datetime import datetime, timezone

from src.maintenance import evaluate_match


def test_high_confidence_when_date_and_km_match():
    revision = {
        "due_km": 10000,
        "due_date": datetime(2026, 8, 1, tzinfo=timezone.utc),
    }
    order = {
        "os_km": 10100,
        "service_date": datetime(2026, 8, 5, tzinfo=timezone.utc),
    }
    result = evaluate_match(
        revision,
        order,
        {
            "km_tolerance": 1500,
            "days_tolerance": 45,
            "require_owner_match": True,
        },
    )
    assert result is not None
    assert result["confidence"] == "alta"


def test_medium_confidence_with_only_km_rule():
    revision = {
        "due_km": 20000,
        "due_date": None,
    }
    order = {
        "os_km": 19800,
        "service_date": datetime(2026, 8, 5, tzinfo=timezone.utc),
    }
    result = evaluate_match(
        revision,
        order,
        {
            "km_tolerance": 1500,
            "days_tolerance": 45,
            "require_owner_match": True,
        },
    )
    assert result is not None
    assert result["confidence"] == "media"


def test_no_match_outside_tolerance():
    revision = {
        "due_km": 10000,
        "due_date": datetime(2026, 8, 1, tzinfo=timezone.utc),
    }
    order = {
        "os_km": 25000,
        "service_date": datetime(2026, 12, 1, tzinfo=timezone.utc),
    }
    result = evaluate_match(
        revision,
        order,
        {
            "km_tolerance": 1500,
            "days_tolerance": 45,
            "require_owner_match": True,
        },
    )
    assert result is None
