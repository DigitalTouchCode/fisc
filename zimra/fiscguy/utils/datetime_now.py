from datetime import datetime
from zoneinfo import ZoneInfo


def datetime_now():
    timestamp = (
        datetime.now(ZoneInfo("Africa/Harare"))
        .replace(microsecond=0)
        .strftime("%Y-%m-%dT%H:%M:%S")
    )

    return timestamp


def date_today():
    return datetime.now(ZoneInfo("Africa/Harare")).date().isoformat()
