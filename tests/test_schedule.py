"""Where: schedule tests. What: verify accepted grammar and next-run calculation. Why: catch scheduler regressions early."""

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from yotei.schedule import is_one_time, next_run_at, parse_schedule


def test_parse_weekdays_schedule() -> None:
    spec = parse_schedule("weekdays 09:30")
    assert spec.kind == "weekdays"
    assert spec.value == "09:30"


def test_parse_one_time_schedule() -> None:
    spec = parse_schedule("in 5m")
    assert spec.kind == "once_minutes"
    assert spec.value == "5"
    assert is_one_time(spec)


def test_parse_once_in_alias_and_intervals() -> None:
    assert parse_schedule("once in 2h").kind == "once_hours"
    assert parse_schedule("every 15m").kind == "interval_minutes"
    assert parse_schedule("every 3h").kind == "interval_hours"


def test_next_run_for_one_time_schedule() -> None:
    spec = parse_schedule("in 5m")
    reference = datetime(2026, 4, 21, 8, 0, tzinfo=ZoneInfo("UTC"))
    next_run = next_run_at(spec, reference, "UTC")
    assert next_run.isoformat() == "2026-04-21T08:05:00+00:00"


def test_next_run_for_daily_schedule() -> None:
    spec = parse_schedule("daily 09:30")
    reference = datetime(2026, 4, 21, 8, 0, tzinfo=ZoneInfo("UTC"))
    next_run = next_run_at(spec, reference, "UTC")
    assert next_run.isoformat() == "2026-04-21T09:30:00+00:00"


def test_next_run_for_weekdays_rolls_to_next_allowed_day() -> None:
    spec = parse_schedule("weekdays 09:30")
    reference = datetime(2026, 4, 24, 10, 0, tzinfo=ZoneInfo("UTC"))
    next_run = next_run_at(spec, reference, "UTC")
    assert next_run.isoformat() == "2026-04-27T09:30:00+00:00"


def test_next_run_for_custom_day_list() -> None:
    spec = parse_schedule("mon,wed 07:15")
    reference = datetime(2026, 4, 21, 8, 0, tzinfo=ZoneInfo("UTC"))
    next_run = next_run_at(spec, reference, "UTC")
    assert next_run.isoformat() == "2026-04-22T07:15:00+00:00"


def test_next_run_for_cron_expression() -> None:
    spec = parse_schedule('cron "*/20 9-10 21 4 2"')
    reference = datetime(2026, 4, 21, 9, 5, tzinfo=ZoneInfo("UTC"))
    next_run = next_run_at(spec, reference, "UTC")
    assert next_run.isoformat() == "2026-04-21T09:20:00+00:00"


def test_parse_invalid_schedule_raises() -> None:
    try:
        parse_schedule("tomorrow morning")
    except ValueError as exc:
        assert "Unsupported schedule" in str(exc)
    else:
        raise AssertionError("Expected ValueError for invalid schedule.")


@pytest.mark.parametrize("raw_text", ["in 0m", "in -1h", "every 0m", "daily 25:00", 'cron "* * *"'])
def test_invalid_schedule_details_raise(raw_text: str) -> None:
    with pytest.raises(ValueError):
        parse_schedule(raw_text)


def test_next_run_rejects_unknown_kind() -> None:
    with pytest.raises(ValueError, match="Unsupported schedule kind"):
        next_run_at(type("Spec", (), {"kind": "nonsense", "value": ""})(), datetime.now(tz=ZoneInfo("UTC")), "UTC")
