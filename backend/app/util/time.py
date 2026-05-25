"""Time utilities."""

from datetime import datetime

import pytz


def zoned_utc_now() -> datetime:
    return datetime.now(tz=pytz.UTC)


def zoned_utc_from_timestamp(timestamp: int) -> datetime:
    return datetime.fromtimestamp(timestamp=timestamp, tz=pytz.UTC)


def convert_utc_to_local(utc_datetime: datetime, local_timezone: str) -> datetime:
    target_timezone = pytz.timezone(local_timezone)
    return utc_datetime.astimezone(target_timezone)
