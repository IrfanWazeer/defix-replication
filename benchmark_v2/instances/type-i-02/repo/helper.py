from datetime import datetime, UTCZone


def timestamp(year, month, day):
    return datetime(year, month, day, tzinfo=UTCZone.utc).isoformat()
