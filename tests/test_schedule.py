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
    assert parse_schedule("once in 10m").kind == "once_minutes"
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


def test_single_digit_hour_clock_remains_supported_for_existing_tasks() -> None:
    spec = parse_schedule("daily 9:00")
    assert spec.kind == "daily"
    assert spec.value == "9:00"


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


@pytest.mark.parametrize("raw_text", ["daily 09", "daily aa:00", "daily 9:0", "weekdays 24:00"])
def test_invalid_clock_forms_raise_clear_error(raw_text: str) -> None:
    with pytest.raises(ValueError, match="Clock time must be H:MM or HH:MM"):
        parse_schedule(raw_text)


@pytest.mark.parametrize("raw_text", ["mon,,wed 09:00", "mon,mo 09:00", "mon,wed, 09:00"])
def test_malformed_day_lists_raise_clear_error(raw_text: str) -> None:
    with pytest.raises(ValueError, match="Custom day lists"):
        parse_schedule(raw_text)


@pytest.mark.parametrize(
    "raw_text",
    [
        'cron "*/15 9-17 * * 1-5"',
        'cron "*/60 0 */40 * *"',
        'cron "0,30 9/2 * * 1,3,5"',
        'cron "0 9-17/2 * * 1-5"',
    ],
)
def test_supported_cron_field_forms_parse(raw_text: str) -> None:
    assert parse_schedule(raw_text).kind == "cron"


@pytest.mark.parametrize(
    "raw_text, message",
    [
        ('cron "0 9 * * mon"', "numeric five-field"),
        ('cron "0 9 ? * *"', "numeric five-field"),
        ('cron "0 9 L * *"', "numeric five-field"),
        ('cron "0 9 31 12 5#2"', "numeric five-field"),
        ('cron "0 9 20-5 * *"', "must not wrap"),
        ('cron "60 9 * * *"', "between 0 and 59"),
        ('cron "0 */0 * * *"', "greater than zero"),
    ],
)
def test_unsupported_cron_forms_raise_clear_error(raw_text: str, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        parse_schedule(raw_text)


def test_next_run_rejects_unknown_kind() -> None:
    with pytest.raises(ValueError, match="Unsupported schedule kind"):
        next_run_at(type("Spec", (), {"kind": "nonsense", "value": ""})(), datetime.now(tz=ZoneInfo("UTC")), "UTC")
