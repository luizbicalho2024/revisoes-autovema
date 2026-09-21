from datetime import datetime, timedelta, timezone

from src.maintenance import _as_utc as maintenance_as_utc
from src.service_importer import _as_utc as importer_as_utc


def test_importer_naive_becomes_utc_aware():
    value = datetime(2026, 9, 21, 12, 30)
    result = importer_as_utc(value)
    assert result is not None
    assert result.tzinfo is not None
    assert result.utcoffset() == timedelta(0)


def test_importer_aware_is_converted_to_utc():
    value = datetime(
        2026,
        9,
        21,
        12,
        30,
        tzinfo=timezone(timedelta(hours=-4)),
    )
    result = importer_as_utc(value)
    assert result is not None
    assert result.utcoffset() == timedelta(0)
    assert result.hour == 16


def test_maintenance_naive_becomes_utc_aware():
    value = datetime(2026, 9, 21, 8, 0)
    result = maintenance_as_utc(value)
    assert result is not None
    assert result.tzinfo is not None
    assert result.utcoffset() == timedelta(0)
