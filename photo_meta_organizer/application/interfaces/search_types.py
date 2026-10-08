"""Search query, paged result, and facet types shared by the repository port.

These replace the ad hoc ``SearchPhotosQuery``/``PaginatedResult`` pair that used
to live in the search use case: filtering, sorting, and paging now happen inside
the repository implementation (``query()``), not in application-layer Python.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Generic, Iterator, List, Optional, TypeVar

from photo_meta_organizer.domain.datetimes import to_naive

T = TypeVar("T")


@dataclass(frozen=True)
class BoundingBox:
    """A map viewport. ``west > east`` means it crosses the 180° meridian."""

    south: float
    west: float
    north: float
    east: float

    def contains(self, latitude: float, longitude: float) -> bool:
        if not self.south <= latitude <= self.north:
            return False
        if self.west <= self.east:
            return self.west <= longitude <= self.east
        return longitude >= self.west or longitude <= self.east


@dataclass
class SearchQuery:
    """Filters, sort, and paging for :meth:`ImageMetadataRepository.query`.

    ``tags`` is AND semantics (ADR D2): a record must carry every listed tag.
    ``date_start``/``date_end`` are normalised to naive local time (ADR D3).
    ``camera_make`` is a case-insensitive substring (CLI search); ``camera_makes`` is
    "any of these makes", matched exactly (the UI's camera checkboxes, PMO-27).
    ``has_capture_date=False`` selects photos with an unknown date (PMO-24),
    ``has_location`` geotagged (or not) photos, ``within`` photos inside a map area, ``collection`` a named collection's
    members.
    """

    search_term: Optional[str] = None
    date_start: Optional[datetime] = None
    date_end: Optional[datetime] = None
    camera_make: Optional[str] = None
    camera_model: Optional[str] = None
    camera_makes: Optional[List[str]] = None
    has_capture_date: Optional[bool] = None
    has_location: Optional[bool] = None
    within: Optional[BoundingBox] = None
    collection: Optional[str] = None
    location_lat: Optional[float] = None
    location_lon: Optional[float] = None
    radius_km: Optional[float] = None
    tags: Optional[List[str]] = None
    rating: Optional[int] = None
    flagged: Optional[bool] = None
    sort_by: str = "captured_at"  # captured_at, size_bytes, camera_model, file_name
    sort_order: str = "asc"  # asc, desc
    page: int = 1
    page_size: int = 50

    def __post_init__(self) -> None:
        self.date_start = to_naive(self.date_start)
        self.date_end = to_naive(self.date_end)


@dataclass
class Page(Generic[T]):
    """One page of results plus enough metadata to render pagination controls."""

    items: List[T]
    total_count: int
    page: int
    page_size: int
    total_pages: int

    def __iter__(self) -> Iterator[T]:
        return iter(self.items)

    def __len__(self) -> int:
        return len(self.items)


@dataclass(frozen=True)
class FacetCount:
    """One value of a facet and how many records carry it."""

    name: str
    count: int


@dataclass(frozen=True)
class GpsBounds:
    """The bounding box of every geotagged record."""

    min_lat: float
    max_lat: float
    min_lon: float
    max_lon: float


@dataclass(frozen=True)
class GeoCluster:
    """Geotagged photos that fall in one map grid cell.

    ``latitude``/``longitude`` is the mean position of the members and
    ``representative_hash`` the most recently captured one (for the marker's thumbnail).
    """

    latitude: float
    longitude: float
    count: int
    representative_hash: str


@dataclass(frozen=True)
class LibraryStats:
    """Whole-library totals for the sidebar and the analytics view (PMO-27)."""

    total_count: int = 0
    flagged_count: int = 0
    geotagged_count: int = 0
    undated_count: int = 0
    total_bytes: int = 0
    avg_megapixels: float = 0.0


@dataclass(frozen=True)
class Facets:
    """Aggregate counts used to populate filter UIs."""

    cameras: List[FacetCount] = field(default_factory=list)
    tags: List[FacetCount] = field(default_factory=list)
    years: List[FacetCount] = field(default_factory=list)
    gps_bounds: Optional[GpsBounds] = None
    isos: List[FacetCount] = field(default_factory=list)
    stats: LibraryStats = field(default_factory=LibraryStats)
