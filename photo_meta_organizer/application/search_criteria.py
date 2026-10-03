"""Turn search arguments typed by a person into query values (PMO-34).

Used by the CLI's ``search`` command. Every function raises ``ValueError`` with a
message fit to show the user, instead of quietly dropping a filter it cannot read
(a mistyped date used to search the whole library).

Dates are naive local time (ADR D3). A date without a time names a whole period:
``2024-03`` is the month and ``2024-03-20`` the day, so as an end bound it includes
the last moment of that period.
"""

import calendar
from dataclasses import dataclass
from datetime import datetime, timedelta

_MONTH = "%Y-%m"
_DAY = "%Y-%m-%d"


@dataclass(frozen=True)
class LocationFilter:
    latitude: float
    longitude: float
    radius_km: float


def _period(text: str) -> tuple[datetime, datetime | None]:
    """Start of ``text`` and, for a bare month or day, the last moment of that period."""
    try:
        if len(text) == 7:
            start = datetime.strptime(text, _MONTH)
            last_day = calendar.monthrange(start.year, start.month)[1]
            return start, start.replace(day=last_day) + timedelta(days=1, microseconds=-1)
        if len(text) == 10:
            start = datetime.strptime(text, _DAY)
            return start, start + timedelta(days=1, microseconds=-1)
        return datetime.fromisoformat(text).replace(tzinfo=None), None
    except ValueError:
        raise ValueError(
            f"Invalid date {text!r}: use YYYY-MM, YYYY-MM-DD or an ISO date-time"
        ) from None


def parse_date(text: str | None) -> datetime | None:
    """The start of the date ``text`` names, or ``None`` if it is empty."""
    if text is None or not text.strip():
        return None
    return _period(text.strip())[0]


def _end_of(text: str | None) -> datetime | None:
    if text is None or not text.strip():
        return None
    start, end = _period(text.strip())
    return end or start


def date_bounds(
    date: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
) -> tuple[datetime | None, datetime | None]:
    """Inclusive ``(start, end)`` bounds. ``date_from``/``date_to`` beat a single ``date``."""
    if (date_from and date_from.strip()) or (date_to and date_to.strip()):
        start, end = parse_date(date_from), _end_of(date_to)
    else:
        start, end = parse_date(date), _end_of(date)
    if start and end and start > end:
        raise ValueError(f"The start date ({start:%Y-%m-%d}) is after the end ({end:%Y-%m-%d})")
    return start, end


def parse_location(
    location: str | None = None,
    lat: float | None = None,
    lon: float | None = None,
    radius_km: float | None = None,
) -> LocationFilter | None:
    """A radius filter from ``--lat/--lon/--radius`` or else ``--location lat,lon,km``."""
    separate = (lat, lon, radius_km)
    if any(value is not None for value in separate):
        if any(value is None for value in separate):
            raise ValueError("--lat, --lon and --radius must be given together")
        found = LocationFilter(float(lat), float(lon), float(radius_km))  # type: ignore[arg-type]
    elif location is not None and location.strip():
        parts = [part.strip() for part in location.split(",")]
        try:
            if len(parts) != 3:
                raise ValueError
            found = LocationFilter(float(parts[0]), float(parts[1]), float(parts[2]))
        except ValueError:
            raise ValueError(
                f"Invalid location {location!r}: use lat,lon,radius_km (e.g. 35.68,139.69,10)"
            ) from None
    else:
        return None

    if not -90 <= found.latitude <= 90:
        raise ValueError(f"Latitude must be between -90 and 90, got {found.latitude}")
    if not -180 <= found.longitude <= 180:
        raise ValueError(f"Longitude must be between -180 and 180, got {found.longitude}")
    if found.radius_km <= 0:
        raise ValueError(f"Radius must be positive, got {found.radius_km}")
    return found


def parse_tags(text: str | None) -> list[str] | None:
    """Comma-separated tags; empty entries dropped. ``None`` when there are none."""
    if not text:
        return None
    tags = [tag.strip() for tag in text.split(",") if tag.strip()]
    return tags or None
