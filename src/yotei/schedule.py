"""Where: schedule module. What: parse supported schedule strings and compute next run times. Why: keep scheduler behavior deterministic."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo


DAY_INDEX = {
    "mon": 0,
    "tue": 1,
    "wed": 2,
    "thu": 3,
    "fri": 4,
    "sat": 5,
    "sun": 6,
}


@dataclass(slots=True)
class ScheduleSpec:
    kind: str
    value: str


def parse_schedule(raw_text: str) -> ScheduleSpec:
    text = raw_text.strip().lower()
    if text.startswith("in ") and text.endswith("m"):
        minutes = int(text.removeprefix("in ").removesuffix("m"))
        if minutes <= 0:
            raise ValueError("One-time minute delay must be greater than zero.")
        return ScheduleSpec(kind="once_minutes", value=str(minutes))
    if text.startswith("in ") and text.endswith("h"):
        hours = int(text.removeprefix("in ").removesuffix("h"))
        if hours <= 0:
            raise ValueError("One-time hour delay must be greater than zero.")
        return ScheduleSpec(kind="once_hours", value=str(hours))
    if text.startswith("once in ") and text.endswith("m"):
        minutes = int(text.removeprefix("once in ").removesuffix("m"))
        if minutes <= 0:
            raise ValueError("One-time minute delay must be greater than zero.")
        return ScheduleSpec(kind="once_minutes", value=str(minutes))
    if text.startswith("once in ") and text.endswith("h"):
        hours = int(text.removeprefix("once in ").removesuffix("h"))
        if hours <= 0:
            raise ValueError("One-time hour delay must be greater than zero.")
        return ScheduleSpec(kind="once_hours", value=str(hours))
    if text.startswith("every ") and text.endswith("m"):
        minutes = int(text.removeprefix("every ").removesuffix("m"))
        if minutes <= 0:
            raise ValueError("Minute interval must be greater than zero.")
        return ScheduleSpec(kind="interval_minutes", value=str(minutes))
    if text.startswith("every ") and text.endswith("h"):
        hours = int(text.removeprefix("every ").removesuffix("h"))
        if hours <= 0:
            raise ValueError("Hour interval must be greater than zero.")
        return ScheduleSpec(kind="interval_hours", value=str(hours))
    if text.startswith("daily "):
        _validate_clock(text.split(" ", 1)[1])
        return ScheduleSpec(kind="daily", value=text.split(" ", 1)[1])
    if text.startswith("weekdays "):
        clock = text.split(" ", 1)[1]
        _validate_clock(clock)
        return ScheduleSpec(kind="weekdays", value=clock)
    if text.startswith('cron "') and text.endswith('"'):
        cron_body = text[6:-1].strip()
        if len(cron_body.split()) != 5:
            raise ValueError("Cron expressions must contain exactly five fields.")
        return ScheduleSpec(kind="cron", value=cron_body)

    parts = text.split(" ", 1)
    if len(parts) == 2 and all(day in DAY_INDEX for day in parts[0].split(",")):
        day_list, clock = parts
        days = day_list.split(",")
        if not days or any(day not in DAY_INDEX for day in days):
            raise ValueError("Custom day lists must use mon,tue,wed,thu,fri,sat,sun.")
        _validate_clock(clock)
        return ScheduleSpec(kind="day_list", value=f"{','.join(days)}|{clock}")

    raise ValueError(
        "Unsupported schedule. Use one of: in <int>m, in <int>h, every <int>m, every <int>h, "
        "daily HH:MM, weekdays HH:MM, <day-list> HH:MM, cron \"<5-field-expression>\"."
    )


def next_run_at(spec: ScheduleSpec, reference: datetime, timezone: str) -> datetime:
    tz = ZoneInfo(timezone)
    current = reference.astimezone(tz)
    if spec.kind == "once_minutes":
        return current + timedelta(minutes=int(spec.value))
    if spec.kind == "once_hours":
        return current + timedelta(hours=int(spec.value))
    if spec.kind == "interval_minutes":
        return current + timedelta(minutes=int(spec.value))
    if spec.kind == "interval_hours":
        return current + timedelta(hours=int(spec.value))
    if spec.kind == "daily":
        return _next_day_time(current, {0, 1, 2, 3, 4, 5, 6}, spec.value)
    if spec.kind == "weekdays":
        return _next_day_time(current, {0, 1, 2, 3, 4}, spec.value)
    if spec.kind == "day_list":
        days_part, clock = spec.value.split("|", 1)
        return _next_day_time(current, {DAY_INDEX[day] for day in days_part.split(",")}, clock)
    if spec.kind == "cron":
        return _next_cron_time(current, spec.value)
    raise ValueError(f"Unsupported schedule kind {spec.kind!r}.")


def is_one_time(spec: ScheduleSpec) -> bool:
    return spec.kind in {"once_minutes", "once_hours"}


def _validate_clock(clock: str) -> None:
    hour_text, minute_text = clock.split(":", 1)
    hour = int(hour_text)
    minute = int(minute_text)
    if hour not in range(24) or minute not in range(60):
        raise ValueError("Clock time must be HH:MM with 24-hour values.")


def _next_day_time(reference: datetime, allowed_days: set[int], clock: str) -> datetime:
    hour, minute = [int(part) for part in clock.split(":", 1)]
    for offset in range(0, 8):
        candidate_day = reference + timedelta(days=offset)
        if candidate_day.weekday() not in allowed_days:
            continue
        candidate = candidate_day.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if candidate > reference:
            return candidate
    raise AssertionError("Unable to find next scheduled day within one week.")


def _next_cron_time(reference: datetime, expression: str) -> datetime:
    minute_field, hour_field, day_field, month_field, weekday_field = expression.split()
    candidate = reference.replace(second=0, microsecond=0) + timedelta(minutes=1)
    for _ in range(0, 525600):
        if (
            _cron_matches(candidate.minute, minute_field, 0, 59)
            and _cron_matches(candidate.hour, hour_field, 0, 23)
            and _cron_matches(candidate.day, day_field, 1, 31)
            and _cron_matches(candidate.month, month_field, 1, 12)
            and _cron_matches(_cron_weekday(candidate.weekday()), weekday_field, 0, 6)
        ):
            return candidate
        candidate += timedelta(minutes=1)
    raise ValueError(f"Could not find next run time for cron expression {expression!r}.")


def _cron_weekday(weekday: int) -> int:
    return (weekday + 1) % 7


def _cron_matches(value: int, field: str, minimum: int, maximum: int) -> bool:
    allowed = set[int]()
    for part in field.split(","):
        if part == "*":
            allowed.update(range(minimum, maximum + 1))
            continue
        if "/" in part:
            base, step_text = part.split("/", 1)
            step = int(step_text)
            start = minimum if base == "*" else int(base)
            allowed.update(range(start, maximum + 1, step))
            continue
        if "-" in part:
            start_text, end_text = part.split("-", 1)
            allowed.update(range(int(start_text), int(end_text) + 1))
            continue
        allowed.add(int(part))
    return value in allowed
