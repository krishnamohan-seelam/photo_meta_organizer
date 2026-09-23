"""Datetime convention for the whole application (ADR D3): naive local time.

EXIF timestamps carry no timezone, so every ``captured_at`` is a naive "wall clock"
value exactly as the camera wrote it. Anything that arrives with tzinfo (a ``Z``
suffix in an API request, an old record stored with an offset) is reduced to that same
convention by *dropping* the tzinfo without shifting the clock, so comparisons and
sorting never mix naive and aware values.
"""

from datetime import datetime
from typing import Optional


def to_naive(value: Optional[datetime]) -> Optional[datetime]:
    """Return ``value`` as a naive datetime (tzinfo dropped, wall clock unchanged)."""
    if value is None or value.tzinfo is None:
        return value
    return value.replace(tzinfo=None)
