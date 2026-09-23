"""Great-circle distance, shared by every repository's location-radius search."""

import math


def haversine_distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Distance between two lat/lon points in kilometers (Haversine formula)."""
    r = 6371.0  # Earth's radius in kilometers
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    )
    return r * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
