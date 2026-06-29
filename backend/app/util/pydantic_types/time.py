"""Pydantic types for time."""

from datetime import datetime, time
from email.utils import parsedate_to_datetime
from typing import Annotated

from pydantic import AfterValidator, AwareDatetime, BeforeValidator, Field


def zone_required_time_validator(value: time) -> time:
    if value.tzinfo is None:
        raise ValueError("Time must have a timezone")
    return value


def zone_disallowed_time_validator(value: time) -> time:
    if value.tzinfo is not None:
        raise ValueError("Time must not have a timezone")
    return value


def validate_rfc2822(rfc2822_str: str) -> datetime:
    try:
        return parsedate_to_datetime(rfc2822_str)
    except Exception:
        raise ValueError("Invalid RFC2822 timestamp")


ZoneRequiredDateTime = AwareDatetime
ZoneRequiredTime = Annotated[
    time,
    Field(description="Time object with required timezone info"),
    AfterValidator(zone_required_time_validator),
]
LocalTime = Annotated[
    time,
    Field(description="Time object without timezone info"),
    AfterValidator(zone_disallowed_time_validator),
]
RFC2822Timestamp = Annotated[ZoneRequiredDateTime, BeforeValidator(validate_rfc2822)]
